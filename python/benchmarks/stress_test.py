import asyncio
import random
import time
import statistics
from httpx import AsyncClient, ASGITransport
from python.api.main import app
from python.database.connection import close_db_pool
from python.services.redis_service import close_redis

NODES = [
    "node-us-east-1a", "node-us-east-1b", "node-us-east-1c",
    "node-eu-west-1a", "node-eu-west-1b", "node-eu-west-1c",
    "node-azure-eastus-01", "node-azure-eastus-02", "node-azure-eastus-03",
    "node-azure-weur-01", "node-azure-weur-02", "node-azure-weur-03"
]

TOTAL_REQUESTS = 1500
CONCURRENCY = 20

async def worker(client: AsyncClient, queue: asyncio.Queue, latencies: list):
    while not queue.empty():
        payload = await queue.get()
        t0 = time.perf_counter()
        resp = await client.post("/api/v1/telemetry", json=payload)
        t1 = time.perf_counter()
        if resp.status_code == 201:
            latencies.append((t1 - t0) * 1000.0)
        queue.task_done()

async def run_stress_test():
    print("=================================================================")
    print("  CloudSentinel Distributed End-to-End Ingest Stress Test        ")
    print(f"  Target: {TOTAL_REQUESTS} requests | Concurrency: {CONCURRENCY} workers")
    print("=================================================================\n")

    queue = asyncio.Queue()
    for _ in range(TOTAL_REQUESTS):
        node_id = random.choice(NODES)
        # 90% normal, 10% degraded/spiking
        is_spike = random.random() < 0.10
        payload = {
            "node_id": node_id,
            "cpu_pct": round(random.uniform(85.0, 99.0) if is_spike else random.uniform(20.0, 65.0), 1),
            "mem_pct": round(random.uniform(88.0, 98.0) if is_spike else random.uniform(30.0, 70.0), 1),
            "disk_pct": round(random.uniform(40.0, 80.0), 1),
            "p99_latency_ms": round(random.uniform(120.0, 350.0) if is_spike else random.uniform(12.0, 45.0), 1),
            "error_rate_pct": round(random.uniform(3.0, 10.0) if is_spike else random.uniform(0.0, 0.5), 2)
        }
        await queue.put(payload)

    latencies = []
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        start_time = time.perf_counter()
        tasks = [asyncio.create_task(worker(client, queue, latencies)) for _ in range(CONCURRENCY)]
        await queue.join()
        for t in tasks:
            t.cancel()
        total_time = time.perf_counter() - start_time

    await close_db_pool()
    await close_redis()

    latencies.sort()
    throughput = len(latencies) / total_time
    p50 = statistics.median(latencies)
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]

    print(f">> Completed:            {len(latencies)} / {TOTAL_REQUESTS} requests")
    print(f">> Total Wall Time:      {total_time:.2f} seconds")
    print(f">> Sustained Throughput: {throughput:,.1f} requests/sec")
    print(f">> Latency p50:          {p50:.2f} ms")
    print(f">> Latency p95:          {p95:.2f} ms")
    print(f">> Latency p99:          {p99:.2f} ms")
    print("=================================================================")

if __name__ == "__main__":
    asyncio.run(run_stress_test())
