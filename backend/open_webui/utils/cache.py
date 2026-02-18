import base64
import json
import logging

log = logging.getLogger(__name__)

CACHE_PREFIX = "open-webui:cache:"


async def redis_cache_get(redis, key: str) -> bytes | None:
    """Get binary value from Redis cache. Returns None if unavailable."""
    if redis is None:
        return None
    try:
        full_key = f"{CACHE_PREFIX}{key}"
        value = await redis.get(full_key)
        if value is not None:
            return base64.b64decode(value)
        return None
    except Exception as e:
        log.debug(f"Redis cache get failed for {key}: {e}")
        return None


async def redis_cache_set(redis, key: str, value: bytes, ttl: int = None):
    """Set binary value in Redis cache. No-ops if Redis unavailable."""
    if redis is None:
        return
    try:
        full_key = f"{CACHE_PREFIX}{key}"
        encoded = base64.b64encode(value).decode("ascii")
        if ttl:
            await redis.set(full_key, encoded, ex=ttl)
        else:
            await redis.set(full_key, encoded)
    except Exception as e:
        log.debug(f"Redis cache set failed for {key}: {e}")


async def redis_cache_get_json(redis, key: str) -> dict | None:
    """Get JSON value from Redis cache. Returns None if unavailable."""
    if redis is None:
        return None
    try:
        full_key = f"{CACHE_PREFIX}{key}"
        value = await redis.get(full_key)
        if value is not None:
            return json.loads(value)
        return None
    except Exception as e:
        log.debug(f"Redis cache get_json failed for {key}: {e}")
        return None


async def redis_cache_set_json(redis, key: str, value: dict, ttl: int = None):
    """Set JSON value in Redis cache. No-ops if Redis unavailable."""
    if redis is None:
        return
    try:
        full_key = f"{CACHE_PREFIX}{key}"
        encoded = json.dumps(value)
        if ttl:
            await redis.set(full_key, encoded, ex=ttl)
        else:
            await redis.set(full_key, encoded)
    except Exception as e:
        log.debug(f"Redis cache set_json failed for {key}: {e}")


def redis_cache_get_json_sync(redis, key: str) -> dict | None:
    """Sync version: Get JSON value from Redis cache. Returns None if unavailable."""
    if redis is None:
        return None
    try:
        full_key = f"{CACHE_PREFIX}{key}"
        value = redis.get(full_key)
        if value is not None:
            return json.loads(value)
        return None
    except Exception as e:
        log.debug(f"Redis sync cache get_json failed for {key}: {e}")
        return None


def redis_cache_set_json_sync(redis, key: str, value: dict, ttl: int = None):
    """Sync version: Set JSON value in Redis cache. No-ops if Redis unavailable."""
    if redis is None:
        return
    try:
        full_key = f"{CACHE_PREFIX}{key}"
        encoded = json.dumps(value)
        if ttl:
            redis.set(full_key, encoded, ex=ttl)
        else:
            redis.set(full_key, encoded)
    except Exception as e:
        log.debug(f"Redis sync cache set_json failed for {key}: {e}")
