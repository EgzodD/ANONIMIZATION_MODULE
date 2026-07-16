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
    person_model_dir: str = ""           # путь к дообученной ruBERT-модели PERSON; пусто = стоковая Natasha

    class Config:
        env_file = ".env"


settings = Settings()
