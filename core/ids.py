"""Stable vacancy identifier and deduplication-key helpers."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core.models import JobRecord


TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "li_fat_id",
    "lipi",
    "refid",
    "trk",
    "trackingid",
}


def normalize_text(value: str) -> str:
    """Normalize text for comparison without changing the stored value."""
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def normalize_url(value: str) -> str:
    """Return a stable URL representation suitable for identity checks."""
    raw_url = str(value or "").strip()
    if not raw_url:
        return ""

    parts = urlsplit(raw_url)
    if not parts.scheme or not parts.netloc:
        return normalize_text(raw_url)

    query_items = []
    for key, query_value in parse_qsl(parts.query, keep_blank_values=True):
        if key.casefold().startswith("utm_"):
            continue
        if key.casefold() in TRACKING_QUERY_KEYS:
            continue
        query_items.append((key, query_value))

    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")

    return urlunsplit(
        (
            parts.scheme.casefold(),
            parts.netloc.casefold(),
            path,
            urlencode(sorted(query_items)),
            "",
        )
    )


def build_deduplication_key(record: JobRecord) -> str:
    """Build the primary identity key for a vacancy."""
    source = normalize_text(record.source)
    normalized_url = normalize_url(record.url)
    if normalized_url:
        return f"{source}|url|{normalized_url}"

    fallback = "|".join(
        (
            normalize_text(record.company),
            normalize_text(record.title),
            normalize_text(record.city_region),
        )
    )
    return f"{source}|fallback|{fallback}"


def _source_slug(source: str) -> str:
    slug = re.sub(r"[^\w]+", "_", normalize_text(source), flags=re.UNICODE)
    return slug.strip("_") or "job"


def build_job_id(record: JobRecord) -> str:
    """Build a stable, readable identifier from the deduplication key."""
    key = build_deduplication_key(record)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"{_source_slug(record.source)}_{digest}"
