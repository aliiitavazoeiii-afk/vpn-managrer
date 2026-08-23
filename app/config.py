import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "VPN Control Center")
    secret_key: str = os.getenv("APP_SECRET_KEY", "change-me-now")
    admin_username: str = os.getenv("ADMIN_USERNAME", "admin")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "change-me-now")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./vpn_control.db")
    poll_seconds: int = int(os.getenv("POLL_SECONDS", "300"))
    timezone: str = os.getenv("APP_TIMEZONE", "Asia/Tehran")
    seed_file: str = os.getenv("SEED_FILE", "/app/seed/users.json")

settings = Settings()
