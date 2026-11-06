from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://wa:wa@localhost:5432/wa"
    redis_url: str = "redis://localhost:6379/0"

    # Security
    secret_key: str  # signs login tokens (JWT)
    encryption_key: str  # Fernet key used to encrypt stored Meta access tokens
    access_token_expire_minutes: int = 60 * 24 * 7

    # First admin user, created on startup if it doesn't exist
    admin_email: str | None = None
    admin_password: str | None = None
    admin_org_name: str = "My Business"
    allow_signup: bool = False  # turn on in phase 2 (SaaS)

    # Meta / WhatsApp
    meta_app_secret: str = ""  # used to verify webhook signatures
    webhook_verify_token: str = ""  # any random string, also entered in Meta's dashboard
    graph_api_version: str = "v24.0"
    whatsapp_mock: bool = False  # fake sending + fake webhooks, for development without Meta

    # Sending
    send_rate_per_second: float = 20
    send_concurrency: int = 8
    max_upload_rows: int = 100_000
    max_upload_mb: int = 20

    frontend_origin: str = "http://localhost:3000"


settings = Settings()
