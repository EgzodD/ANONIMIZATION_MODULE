import os

# Тесты и CI гоняются на чекауте без дообученной модели PERSON (114 МБ, models/ в
# .gitignore). В проде app.main в этом случае намеренно падает — чтобы дырявый
# сервис не запустился молча. Здесь разрешаем запуск явно.
# Тесты, которым модель реально нужна, помечены маркером requires_model.
os.environ.setdefault("ALLOW_NO_PERSON_MODEL", "true")

import pytest  # noqa: E402 — только после установки env выше
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.person_transformer_recognizer import person_model_available  # noqa: E402


def pytest_collection_modifyitems(config, items):
    """Скипать тесты с requires_model, если дообученной модели PERSON нет.

    Без модели PERSON ищется только запасным spaCy — метрики recall ФИО и
    поведение на пограничных кейсах (склейки) недостоверны, поэтому такие тесты
    должны СКИПАТЬСЯ, а не падать. С моделью — гоняются как обычно.
    """
    if person_model_available():
        return
    skip = pytest.mark.skip(reason="нет дообученной модели PERSON (requires_model)")
    for item in items:
        if "requires_model" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def client():
    return TestClient(app)
