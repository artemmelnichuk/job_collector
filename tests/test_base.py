from __future__ import annotations

import unittest

from collectors.base import get_with_retry, per_query_share, setting


class FakeResponse:
    def __init__(self, ok: bool, status: int = 200) -> None:
        self.ok = ok
        self.status = status


class FakeRequest:
    def __init__(self, outcomes: list) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    async def get(self, url: str, timeout: int):
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeContext:
    def __init__(self, outcomes: list) -> None:
        self.request = FakeRequest(outcomes)


class SettingTests(unittest.TestCase):
    def test_reads_nested_value_and_falls_back_to_default(self) -> None:
        self.assertEqual(setting({"request": {"timeout_seconds": 30}}, "request", "timeout_seconds"), 30)
        self.assertEqual(setting({}, "request", "timeout_seconds", default=60), 60)
        self.assertEqual(setting({"request": "not a dict"}, "request", "timeout_seconds", default=60), 60)


class GetWithRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_first_ok_response_without_retrying(self) -> None:
        context = FakeContext([FakeResponse(ok=True)])
        response = await get_with_retry(context, "https://example.com", timeout_ms=1000, retry_attempts=2, delay_min_seconds=0, delay_max_seconds=0)
        self.assertTrue(response.ok)
        self.assertEqual(context.request.calls, 1)

    async def test_retries_a_non_ok_response_then_succeeds(self) -> None:
        context = FakeContext([FakeResponse(ok=False, status=502), FakeResponse(ok=True)])
        response = await get_with_retry(context, "https://example.com", timeout_ms=1000, retry_attempts=2, delay_min_seconds=0, delay_max_seconds=0)
        self.assertTrue(response.ok)
        self.assertEqual(context.request.calls, 2)

    async def test_retries_a_raised_exception_then_succeeds(self) -> None:
        context = FakeContext([TimeoutError("boom"), FakeResponse(ok=True)])
        response = await get_with_retry(context, "https://example.com", timeout_ms=1000, retry_attempts=2, delay_min_seconds=0, delay_max_seconds=0)
        self.assertTrue(response.ok)
        self.assertEqual(context.request.calls, 2)

    async def test_raises_the_last_error_once_attempts_are_exhausted(self) -> None:
        context = FakeContext([FakeResponse(ok=False, status=500), FakeResponse(ok=False, status=500)])
        with self.assertRaises(RuntimeError):
            await get_with_retry(context, "https://example.com", timeout_ms=1000, retry_attempts=1, delay_min_seconds=0, delay_max_seconds=0)
        self.assertEqual(context.request.calls, 2)

    async def test_zero_retry_attempts_makes_exactly_one_call(self) -> None:
        context = FakeContext([FakeResponse(ok=False, status=500)])
        with self.assertRaises(RuntimeError):
            await get_with_retry(context, "https://example.com", timeout_ms=1000, retry_attempts=0, delay_min_seconds=0, delay_max_seconds=0)
        self.assertEqual(context.request.calls, 1)


class PerQueryShareTests(unittest.TestCase):
    def test_splits_limit_evenly_across_queries(self) -> None:
        self.assertEqual(per_query_share(50, 10), 5)
        self.assertEqual(per_query_share(10, 3), 3)

    def test_never_returns_zero_for_a_positive_limit(self) -> None:
        # Regression: floor division could starve a query to 0 when there are
        # more queries than the limit, letting it collect nothing at all.
        self.assertEqual(per_query_share(3, 10), 1)

    def test_no_queries_returns_the_full_limit(self) -> None:
        self.assertEqual(per_query_share(50, 0), 50)


if __name__ == "__main__":
    unittest.main()
