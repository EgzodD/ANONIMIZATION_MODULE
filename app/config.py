from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@db:5432/conversations_db"
    api_key: str = ""                    # пустая строка = аутентификация отключена
    chatwoot_webhook_secret: str = ""    # пустая строка = проверка подписи отключена

    class Config:
        env_file = ".env"


settings = Settings()
