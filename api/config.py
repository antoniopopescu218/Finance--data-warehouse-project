from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "dwh"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
