import logging
from urllib.parse import urlsplit

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConfigurationError, OperationFailure, PyMongoError, ServerSelectionTimeoutError
from app.core.config import settings

logger = logging.getLogger("dorecord.database")


class DatabaseConfigurationError(RuntimeError):
    """The configured MongoDB URI is missing or structurally invalid."""


class DatabaseUnavailableError(RuntimeError):
    """MongoDB could not be reached for a database-dependent request."""

def _safe_mongodb_host(uri: str) -> str:
    try:
        return urlsplit(uri).hostname or "<missing>"
    except ValueError:
        return "<invalid>"


primary_url = (settings.MONGO_URL or "").strip()
client = None
db = None
_database_is_healthy = False
_last_connection_error = None


def _connection_reason(error: BaseException) -> str:
    message = str(error).lower()
    if "query name does not exist" in message or "getaddrinfo" in message or "dns" in message:
        return "MongoDB DNS/SRV hostname cannot be resolved"
    if isinstance(error, ConfigurationError):
        return "invalid MongoDB URI or SRV configuration"
    if isinstance(error, OperationFailure) or "authentication failed" in message:
        return "MongoDB authentication failed"
    if isinstance(error, ServerSelectionTimeoutError):
        return "MongoDB server selection timed out; check Atlas network access"
    return "MongoDB server is unavailable"


def _log_connection_failure(error: BaseException) -> None:
    global _last_connection_error, _database_is_healthy
    _database_is_healthy = False
    _last_connection_error = _connection_reason(error)
    logger.error(
        "MongoDB ping failed: type=%s host=%s database=%s reason=%s",
        type(error).__name__,
        _safe_mongodb_host(primary_url),
        settings.DATABASE_NAME,
        _last_connection_error,
    )


def _create_client():
    if not primary_url:
        raise DatabaseConfigurationError("MONGO_URL is not set")
    try:
        parsed = urlsplit(primary_url)
    except ValueError as error:
        raise DatabaseConfigurationError("MONGO_URL is not a valid URI") from error
    if parsed.scheme not in {"mongodb", "mongodb+srv"} or not parsed.hostname:
        raise DatabaseConfigurationError("MONGO_URL must be a valid mongodb:// or mongodb+srv:// URI")
    return AsyncIOMotorClient(
        primary_url,
        connectTimeoutMS=settings.MONGO_CONNECT_TIMEOUT_MS,
        serverSelectionTimeoutMS=settings.MONGO_SERVER_SELECTION_TIMEOUT_MS,
    )


def _initialize_client() -> None:
    global client, db, _last_connection_error
    if client is not None:
        return
    try:
        client = _create_client()
        db = client[settings.DATABASE_NAME]
        _last_connection_error = None
        logger.info(
            "MongoDB configuration loaded; scheme=%s host=%s database=%s",
            urlsplit(primary_url).scheme,
            _safe_mongodb_host(primary_url),
            settings.DATABASE_NAME,
        )
    except (DatabaseConfigurationError, ConfigurationError) as error:
        _last_connection_error = str(error)
        logger.error(
            "MongoDB configuration error: type=%s host=%s database=%s reason=%s",
            type(error).__name__,
            _safe_mongodb_host(primary_url),
            settings.DATABASE_NAME,
            _last_connection_error,
        )


def database_available() -> bool:
    return _database_is_healthy


async def verify_database_connection() -> bool:
    _initialize_client()
    if client is None or db is None:
        return False
    try:
        await client.admin.command("ping")
    except (PyMongoError, OSError, RuntimeError) as error:
        _log_connection_failure(error)
        return False
    global _database_is_healthy, _last_connection_error
    _database_is_healthy = True
    _last_connection_error = None
    logger.info(
        "MongoDB ping successful: host=%s database=%s",
        _safe_mongodb_host(primary_url),
        settings.DATABASE_NAME,
    )
    return True


async def ensure_database_available() -> None:
    if not await verify_database_connection():
        raise DatabaseUnavailableError(_last_connection_error or "MongoDB is unavailable")


async def close_database() -> None:
    global client, db, _database_is_healthy
    if client is not None:
        client.close()
    client = None
    db = None
    _database_is_healthy = False


class _UnavailableCollection:
    def __init__(self, name: str):
        self.name = name

    def __getattr__(self, attribute):
        raise DatabaseUnavailableError(
            _last_connection_error or f"MongoDB collection '{self.name}' is unavailable"
        )


_initialize_client()

# Collections
def _collection(name: str):
    return db[name] if db is not None else _UnavailableCollection(name)


users_collection = _collection("users")
roles_collection = _collection("roles")
permissions_collection = _collection("permissions")
articles_collection = _collection("articles")
web_stories_collection = _collection("web_stories")
story_events_collection = _collection("web_story_events")
categories_collection = _collection("categories")
tags_collection = _collection("tags")
media_collection = _collection("media")
notifications_collection = _collection("notifications")
activity_logs_collection = _collection("activity_logs")
sessions_collection = _collection("sessions")
password_resets_collection = _collection("password_resets")
settings_collection = _collection("settings")
writer_applications_collection = _collection("writer_applications")
activation_tokens_collection = _collection("activation_tokens")
