from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@db:5432/conversations_db"

    class Config:
        env_file = ".env"


settings = Settings()
