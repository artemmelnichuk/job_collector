# Job Collector

Независимый проект для сбора вакансий в направлениях data analytics,
crypto, trading, market data, risk, fraud и quant research.

Старый проект `job_market_collector` не является зависимостью этого проекта
и не изменяется при его разработке.

## Текущий статус

Рабочая collector-версия готова. Pipeline собирает вакансии, удаляет дубли,
сохраняет raw и processed-файлы и умеет проверять доступность уже сохранённых
вакансий.

Добавлен первый rule-based проход анализа вакансий, классификации и извлечения
skills. Полноценная оценка соответствия профилю кандидата пока является
следующим этапом.

## Структура

```text
config/       Конфигурация запросов, компаний и параметров запуска.
collectors/   Адаптеры источников вакансий.
core/         Общие модели и сервисы pipeline.
scripts/      Точки запуска CLI.
data/raw/     Результаты отдельных запусков.
data/processed/ Накопительный очищенный датасет.
logs/         Логи запусков.
```

## Установка

Работа выполняется из корня проекта:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Проверка конфигурации

```powershell
.venv\Scripts\python.exe -B scripts\collector.py --dry-run
```

## Сбор вакансий

Собрать до 50 вакансий на источник:

```powershell
.venv\Scripts\python.exe -B scripts\collector.py --source all --limit 50
```

Собрать только Company Careers:

```powershell
.venv\Scripts\python.exe -B scripts\collector.py `
  --source company_careers `
  --limit 50 `
  --headless
```

Запустить один запрос:

```powershell
.venv\Scripts\python.exe -B scripts\collector.py `
  --source company_careers `
  --query "Trading Analyst" `
  --limit 20 `
  --headless
```

Доступные источники:

- `linkedin` — LinkedIn;
- `wttj` — Welcome to the Jungle;
- `company_careers` — публичные Greenhouse и Lever boards компаний;
- `all` — все источники.

## Проверка закрытых вакансий

Повторно проверить сохранённые URL:

```powershell
.venv\Scripts\python.exe -B scripts\collector.py `
  --check-availability `
  --check-limit 500 `
  --headless
```

Результат записывается в поле `availability_status`:

- `active` — вакансия доступна;
- `closed` — вакансия закрыта или удалена;
- `unknown` — статус определить не удалось.

Для Company Careers статус проверяется через Greenhouse/Lever API.

## Результаты

- `data/raw/` — отдельные raw XLSX и CSV каждого запуска;
- `data/processed/crypto_jobs_clean_v1.xlsx` — накопительный processed-файл;
- `data/processed/crypto_jobs_clean_v1.csv` — CSV-версия processed-файла.

В processed XLSX используются листы:

- `jobs_master` — полная каноническая таблица со всеми полями;
- `jobs_view` — компактная таблица для ежедневного просмотра;
- `jobs_text` — длинные описания вакансий и ссылки.
- `manual_review` — отдельная таблица для ручной проверки соответствия вакансий
  личным условиям кандидата. Жёлтые поля нужно заполнять вручную.

В raw XLSX используется лист `raw_jobs`. CSV-файлы остаются полными и не
содержат сокращённого view-представления.

Перед сохранением processed-файла выполняется дедупликация и merge с ранее
собранными вакансиями.

## Первый анализ вакансий

После сбора можно запустить первый rule-based анализ:

```powershell
.venv\Scripts\python.exe -B scripts\analyzer.py
```

Он добавляет в processed-файл:

- `role_family` и `role_subcategory` — предварительную классификацию роли;
- `seniority` и диапазон лет опыта;
- `skills_all` — найденные навыки;
- `required_skills` и `preferred_skills` — предварительное разделение требований.

Это первый автоматический проход по тексту вакансий. Перед принятием решений
результаты нужно выборочно проверить вручную.

## Тесты

```powershell
.venv\Scripts\python.exe -B -m unittest discover -s tests
```

## Ограничения

Публичная тематическая страница WTTJ может не применять переданный поисковый
запрос. Поэтому WTTJ надёжен как источник вакансий Data Analyst, но не всегда
даёт точную фильтрацию для Crypto, Trading, Risk и Quant.
