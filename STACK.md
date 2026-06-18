# Tech Stack

## Backend
- **Python** 3.12
- **FastAPI** 0.115.6 — веб-фреймворк, REST API
- **Uvicorn** 0.34.0 — ASGI-сервер

## NLP / Анонимизация
- **Microsoft Presidio Analyzer** 2.2.355 — движок анализа и обнаружения ПДн
- **Microsoft Presidio Anonymizer** 2.2.355 — движок анонимизации и деанонимизации
- **spaCy** 3.8.4 — NLP-библиотека
- **ru_core_news_lg** — русская NLP-модель spaCy (NER, морфология)

## База данных
- **PostgreSQL** 16 — хранение данных Chatwoot
- **SQLAlchemy** 2.0.36 — ORM
- **psycopg2-binary** 2.9.10 — PostgreSQL-драйвер

## Валидация / Конфигурация
- **Pydantic** 2.10.4 — валидация данных и схемы
- **pydantic-settings** 2.7.1 — настройки через env-переменные
- **python-dotenv** 1.0.1 — загрузка .env файлов

## Тестирование
- **pytest** 8.3.4 — фреймворк тестирования
- **pytest-asyncio** 0.25.0 — поддержка async-тестов
- **httpx** 0.28.1 — HTTP-клиент для тестов API

## Инфраструктура
- **Docker** — контейнеризация
- **Docker Compose** — оркестрация сервисов (app + db)
