from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "CMS Backend"
    MONGO_URI: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "cms_db"

    redis_host: str = "localhost"
    redis_port: int = 6379


class Settings(BaseSettings):
    # Security
    SECRET_KEY: str

    ADMIN_USERNAME: str
    ADMIN_PASSWORD: str

    # MongoDB
    MONGO_URL: str
    DATABASE_NAME: str

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    class Config:
        env_file = ".env"
        extra = "forbid"   # explicit & safe


settings = Settings()


