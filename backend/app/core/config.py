from pydantic_settings import BaseSettings
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env" if (PROJECT_ROOT / ".env").exists() else BACKEND_ROOT / ".env"
load_dotenv(ENV_FILE, override=True)

class Settings(BaseSettings):
    PROJECT_NAME: str = "DO Record Media CMS"
    SECRET_KEY: str = "dorecord_super_secret_jwt_key_2026_safe_hash_production_99a8b7c6d5e4f3a2b1"
    ALGORITHM: str = "HS256"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 # 7 days
    
    # MongoDB settings
    MONGO_URL: str = ""
    DATABASE_NAME: str = "cms_db"
    MONGO_CONNECT_TIMEOUT_MS: int = 5000
    MONGO_SERVER_SELECTION_TIMEOUT_MS: int = 5000
    
    # Admin seed defaults
    ADMIN_USERNAME: str = "admin"
    ADMIN_EMAIL: str = "admin@dorecord.com"
    ADMIN_PASSWORD: str = "Admin@123456"
    
    # Redis (optional)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    VERIFY_DATABASE_ON_STARTUP: bool = True

    class Config:
        env_file = str(ENV_FILE)
        extra = "ignore"

settings = Settings()



