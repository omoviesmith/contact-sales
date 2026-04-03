from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "contact-sales-core"
    log_level: str = "INFO"
    database_url: str
    redis_url: str
    queue_name: str = "contact_sales:default"
    worker_poll_seconds: int = 3
    capsolver_api_key: str | None = None
    capsolver_poll_seconds: int = 3
    capsolver_max_polls: int = 20
    serper_api_key: str | None = None
    serper_search_url: str = "https://google.serper.dev/search"
    serper_timeout_seconds: int = 15
    enrichment_timeout_seconds: int = 20


settings = Settings()
