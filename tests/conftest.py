import os

# Тесты и CI гоняются на чекауте без дообученной модели PERSON (114 МБ, models/ в
# .gitignore). В проде app.main в этом случае намеренно падает — чтобы дырявый
# сервис не запустился молча. Здесь разрешаем запуск явно.
# Тесты, которым модель реально нужна, помечены маркером requires_model.
os.environ.setdefault("ALLOW_NO_PERSON_MODEL", "true")

import pytest  # noqa: E402 — только после установки env выше
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)
