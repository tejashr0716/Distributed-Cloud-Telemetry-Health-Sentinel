import asyncio
import json
import os
import redis.asyncio as redis
from typing import Optional, List, Dict, Any

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "3"))

redis_client: Optional[redis.Redis] = None

async def init_redis() -> redis.Redis:
    global redis_client
    if redis_client is not None:
        try:
            await redis_client.aclose()
        except Exception:
            pass
        redis_client = None

    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True
    )
    return redis_client

async def get_redis() -> redis.Redis:
    global redis_client
    if redis_client is None:
        await init_redis()
    return redis_client

async def close_redis():
    global redis_client
    if redis_client is not None:
        try:
            await redis_client.aclose()
        except Exception:
            pass
        redis_client = None

async def set_node_heartbeat(node_id: str, ttl_seconds: int = 30) -> bool:
    client = await get_redis()
    key = f"cloudsentinel:node:{node_id}:hb"
    await client.set(key, "ONLINE", ex=ttl_seconds)
    return True

async def is_node_online(node_id: str) -> bool:
    client = await get_redis()
    key = f"cloudsentinel:node:{node_id}:hb"
    exists = await client.exists(key)
    return bool(exists)

async def record_metric_history(node_id: str, metric_name: str, value: float, max_len: int = 100):
    client = await get_redis()
    key = f"cloudsentinel:metrics:{node_id}:{metric_name}"
    await client.lpush(key, str(value))
    await client.ltrim(key, 0, max_len - 1)

async def get_metric_history(node_id: str, metric_name: str, limit: int = 50) -> List[float]:
    client = await get_redis()
    key = f"cloudsentinel:metrics:{node_id}:{metric_name}"
    raw_vals = await client.lrange(key, 0, limit - 1)
    return [float(x) for x in raw_vals if x]

async def publish_telemetry(event: Dict[str, Any]):
    client = await get_redis()
    await client.publish("cloudsentinel:telemetry", json.dumps(event))

async def cache_region_summary(region_id: str, data: Dict[str, Any]):
    client = await get_redis()
    key = f"cloudsentinel:region:{region_id}:summary"
    await client.set(key, json.dumps(data), ex=60)
