import os
from dotenv import load_dotenv
load_dotenv()

class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./rakshapay.db")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-secret-change-in-prod-abc123")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    VONAGE_APPLICATION_ID: str = os.getenv("VONAGE_APPLICATION_ID", "")
    VONAGE_PRIVATE_KEY_PATH: str = os.getenv("VONAGE_PRIVATE_KEY_PATH", "./vonage_private.key")
    VONAGE_ENVIRONMENT: str = os.getenv("VONAGE_ENVIRONMENT", "sandbox")
    APP_ENV: str = os.getenv("APP_ENV", "development")

    @property
    def is_dev(self): return self.APP_ENV == "development"

settings = Settings()
