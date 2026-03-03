from motor.motor_asyncio import AsyncIOMotorClient

from app.config import get_settings

_client: AsyncIOMotorClient | None = None


def get_db():
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(get_settings().MONGODB_URI)
    return _client.get_default_database()


async def ensure_indexes():
    db = get_db()
    await db.workflows.create_index("domain", unique=True)


async def close_db():
    global _client
    if _client:
        _client.close()
        _client = None
