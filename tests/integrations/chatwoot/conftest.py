"""
Фикстура для тестов интеграции с Chatwoot. Форсирует CHATWOOT_ENABLED=true и
пересобирает FastAPI-app (app.main), чтобы Chatwoot-роуты (/anonymize/conversation,
/anonymize/batch, /webhook) были зарегистрированы.

БЕЗ поднятия реального Postgres: DATABASE_URL указывает на заведомо
недоступный адрес. Достаточно, что fail-fast проверка при старте (пустой
DATABASE_URL) не срабатывает, а эндпоинты, которым реально нужна БД, получают
предсказуемую ошибку вместо 404 (см. test_chatwoot_api.py).

Переопределяет фикстуру `client` из корневого tests/conftest.py — только для
тестов в этой директории (ближайший conftest.py побеждает). Тесты вне
tests/integrations/chatwoot по-прежнему получают клиент с CHATWOOT_ENABLED=false.
"""

import importlib

import pytest
from fastapi.testclient import TestClient

from app.config import settings
import app.main as app_main_module
import app.integrations.chatwoot.database as chatwoot_db_module


@pytest.fixture
def client():
    orig_enabled = settings.chatwoot_enabled
    orig_db_url = settings.database_url

    settings.chatwoot_enabled = True
    settings.database_url = "postgresql://u:p@localhost:5432/nonexistent"
    # Сбрасываем кэш лениво создаваемого engine — иначе можно унаследовать
    # engine, созданный в другом тесте с другими настройками.
    chatwoot_db_module._engine = None
    chatwoot_db_module._SessionLocal = None

    try:
        importlib.reload(app_main_module)
        # raise_server_exceptions=False: тестам на недоступность БД нужен
        # настоящий HTTP-ответ (500), а не проброс исключения в тест-раннер.
        test_client = TestClient(app_main_module.app, raise_server_exceptions=False)
        yield test_client
    finally:
        settings.chatwoot_enabled = orig_enabled
        settings.database_url = orig_db_url
        chatwoot_db_module._engine = None
        chatwoot_db_module._SessionLocal = None
        importlib.reload(app_main_module)
