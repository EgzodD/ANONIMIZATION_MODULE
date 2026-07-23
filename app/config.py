import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Сервис по умолчанию работает standalone, без Chatwoot. Интеграция
    # включается явно через CHATWOOT_ENABLED=true (см. app/integrations/chatwoot).
    chatwoot_enabled: bool = False

    # Пусто = БД не сконфигурирована. Обязательна только при chatwoot_enabled=true
    # (проверяется fail-fast при старте — см. app/integrations/chatwoot/database.py).
    database_url: str = ""
    api_key: str = ""                    # пустая строка = аутентификация отключена
    chatwoot_webhook_secret: str = ""    # пустая строка = проверка подписи отключена; используется только при chatwoot_enabled=true

    # Путь к дообученной ruBERT-модели PERSON. Обязателен: без модели ФИО не
    # распознаются вообще, поэтому сервис откажется стартовать (см. app/main.py).
    person_model_dir: str = ""

    # Аварийный флаг: разрешить запуск БЕЗ модели PERSON. Только для тестов и CI,
    # где модели нет в чекауте. В проде включать нельзя — ФИО будут утекать.
    allow_no_person_model: bool = False

    class Config:
        # Абсолютный путь к .env в корне проекта: относительный (".env")
        # резолвится от папки ЗАПУСКА процесса, из-за чего настройки (в т.ч.
        # PERSON_MODEL_DIR) молча терялись при запуске скриптов не из корня.
        env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")


settings = Settings()
