import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from python.database.connection import init_db_pool, close_db_pool, get_db_pool
from python.services.cpp_bridge import CloudSentinelEngine
from python.services.redis_service import (
    init_redis, close_redis, set_node_heartbeat, is_node_online,
    record_metric_history, get_metric_history, publish_telemetry, cache_region_summary
)
from python.services.rabbitmq_service import init_rabbitmq, close_rabbitmq, publish_incident_alert

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("cloudsentinel.api")

engine: Optional[CloudSentinelEngine] = None

def get_engine() -> CloudSentinelEngine:
    global engine
    if engine is None:
        engine = CloudSentinelEngine()
    return engine

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing CloudSentinel Services...")
    await init_db_pool()
    await init_redis()
    await init_rabbitmq()
    get_engine()
    logger.info("CloudSentinel C++ Engine and distributed services ready.")
    yield
    logger.info("Shutting down CloudSentinel Services...")
    await close_rabbitmq()
    await close_redis()
    await close_db_pool()

app = FastAPI(
    title="CloudSentinel Multi-Region Telemetry Gateway",
    version="1.0.0",
    description="High-Throughput Multi-Region Cloud Telemetry & Health Sentinel Engine",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TelemetryPayload(BaseModel):
    node_id: str
    cpu_pct: float = Field(..., ge=0.0, le=100.0)
    mem_pct: float = Field(..., ge=0.0, le=100.0)
    disk_pct: float = Field(..., ge=0.0, le=100.0)
    p99_latency_ms: float = Field(..., ge=0.0)
    error_rate_pct: float = Field(..., ge=0.0, le=100.0)

class BatchTelemetryPayload(BaseModel):
    items: List[TelemetryPayload]

@app.get("/health")
async def health_check():
    return {
        "status": "HEALTHY",
        "service": "CloudSentinel Telemetry Gateway",
        "engine": "C++ SIMD Vectorized Core Loaded",
        "active_websockets": len(ws_manager.active_connections)
    }

@app.get("/api/v1/regions")
async def get_regions():
    db = await get_db_pool()
    eng = get_engine()
    async with db.acquire() as conn:
        regions = await conn.fetch("SELECT * FROM regions ORDER BY region_id ASC;")
        output = []
        for r in regions:
            nodes = await conn.fetch("SELECT * FROM nodes WHERE region_id = $1;", r["region_id"])
            node_scores = []
            online_count = 0
            for n in nodes:
                is_on = await is_node_online(n["node_id"])
                if is_on:
                    online_count += 1
                latest = await conn.fetchrow(
                    "SELECT health_score FROM telemetry_logs WHERE node_id = $1 ORDER BY recorded_at DESC LIMIT 1;",
                    n["node_id"]
                )
                if latest:
                    node_scores.append(latest["health_score"])
                else:
                    node_scores.append(100.0 if is_on else 0.0)

            quorum_score = eng.quorum_health(node_scores, min_quorum=max(1, len(nodes) // 2)) if node_scores else 100.0

            region_status = "HEALTHY" if quorum_score >= 75.0 else ("DEGRADED" if quorum_score >= 45.0 else "CRITICAL")
            await conn.execute("UPDATE regions SET status = $1 WHERE region_id = $2;", region_status, r["region_id"])

            output.append({
                "region_id": r["region_id"],
                "provider": r["provider"],
                "location": r["location"],
                "status": region_status,
                "latency_sla_ms": r["latency_sla_ms"],
                "quorum_health_score": quorum_score,
                "total_nodes": len(nodes),
                "online_nodes": online_count
            })
        return output

@app.get("/api/v1/nodes")
async def get_nodes(region_id: Optional[str] = None):
    db = await get_db_pool()
    async with db.acquire() as conn:
        query = "SELECT * FROM nodes"
        params = []
        if region_id:
            query += " WHERE region_id = $1"
            params.append(region_id)
        query += " ORDER BY node_id ASC;"

        nodes = await conn.fetch(query, *params)
        output = []
        for n in nodes:
            online = await is_node_online(n["node_id"])
            latest = await conn.fetchrow(
                "SELECT * FROM telemetry_logs WHERE node_id = $1 ORDER BY recorded_at DESC LIMIT 1;",
                n["node_id"]
            )
            output.append({
                "node_id": n["node_id"],
                "region_id": n["region_id"],
                "hostname": n["hostname"],
                "instance_type": n["instance_type"],
                "ip_address": n["ip_address"],
                "is_online": online,
                "status": n["status"] if online else "OFFLINE",
                "last_heartbeat_at": n["last_heartbeat_at"].isoformat() if n["last_heartbeat_at"] else None,
                "latest_telemetry": {
                    "cpu_pct": latest["cpu_pct"],
                    "mem_pct": latest["mem_pct"],
                    "disk_pct": latest["disk_pct"],
                    "p99_latency_ms": latest["p99_latency_ms"],
                    "error_rate_pct": latest["error_rate_pct"],
                    "health_score": latest["health_score"],
                    "status": latest["status"],
                    "recorded_at": latest["recorded_at"].isoformat()
                } if latest else None
            })
        return output

@app.post("/api/v1/telemetry", status_code=status.HTTP_201_CREATED)
async def ingest_telemetry(payload: TelemetryPayload):
    db = await get_db_pool()
    eng = get_engine()
    async with db.acquire() as conn:
        node = await conn.fetchrow("SELECT n.*, r.latency_sla_ms FROM nodes n JOIN regions r ON n.region_id = r.region_id WHERE n.node_id = $1;", payload.node_id)
        if not node:
            raise HTTPException(status_code=404, detail=f"Node '{payload.node_id}' not found.")

        sla = node["latency_sla_ms"]

        # 1. C++ High Performance Health Evaluation
        eval_result = eng.evaluate_node(
            cpu=payload.cpu_pct,
            mem=payload.mem_pct,
            disk=payload.disk_pct,
            latency=payload.p99_latency_ms,
            error_rate=payload.error_rate_pct,
            sla=sla
        )

        # 2. Historical Outlier & Anomaly Detection via C++
        history = await get_metric_history(payload.node_id, "latency", limit=30)
        anomaly_info = eng.detect_anomaly(history, payload.p99_latency_ms) if len(history) >= 5 else {"is_anomaly": False, "z_score": 0.0}

        # 3. Insert Telemetry Log
        row = await conn.fetchrow(
            """
            INSERT INTO telemetry_logs (node_id, cpu_pct, mem_pct, disk_pct, p99_latency_ms, error_rate_pct, health_score, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING log_id, recorded_at;
            """,
            payload.node_id, payload.cpu_pct, payload.mem_pct, payload.disk_pct,
            payload.p99_latency_ms, payload.error_rate_pct, eval_result["health_score"],
            eval_result["status_label"]
        )

        # 4. Update Node State & Heartbeat in Redis
        node_status = "ONLINE" if eval_result["health_score"] >= 65.0 else ("DEGRADED" if eval_result["health_score"] >= 35.0 else "CRITICAL")
        await conn.execute("UPDATE nodes SET status = $1, last_heartbeat_at = NOW() WHERE node_id = $2;", node_status, payload.node_id)
        await set_node_heartbeat(payload.node_id, ttl_seconds=45)
        await record_metric_history(payload.node_id, "latency", payload.p99_latency_ms)
        await record_metric_history(payload.node_id, "cpu", payload.cpu_pct)

        # 5. Incident Alert Escalation
        alert_created = False
        if eval_result["health_score"] < 65.0 or anomaly_info.get("is_anomaly", False):
            severity = "CRITICAL" if eval_result["health_score"] < 35.0 else "WARNING"
            metric_trigger = "Latency SLA" if payload.p99_latency_ms > sla else ("Error Rate" if payload.error_rate_pct > 2.0 else "Resource Pressure")
            alert_row = await conn.fetchrow(
                """
                INSERT INTO incident_alerts (node_id, severity, metric_name, trigger_value, message, status)
                VALUES ($1, $2, $3, $4, $5, 'ACTIVE')
                RETURNING alert_id, created_at;
                """,
                payload.node_id, severity, metric_trigger, payload.p99_latency_ms, eval_result["alert_reason"]
            )
            alert_created = True
            # Publish to RabbitMQ
            routing_key = f"cloudsentinel.alert.{severity.lower()}"
            await publish_incident_alert(routing_key, {
                "alert_id": alert_row["alert_id"],
                "node_id": payload.node_id,
                "severity": severity,
                "reason": eval_result["alert_reason"],
                "health_score": eval_result["health_score"],
                "created_at": alert_row["created_at"].isoformat()
            })

        event_data = {
            "type": "TELEMETRY_INGEST",
            "log_id": row["log_id"],
            "node_id": payload.node_id,
            "region_id": node["region_id"],
            "metrics": payload.model_dump(),
            "evaluation": eval_result,
            "anomaly": anomaly_info,
            "alert_created": alert_created,
            "timestamp": row["recorded_at"].isoformat()
        }

        # Redis PubSub & WebSocket broadcast
        await publish_telemetry(event_data)
        asyncio.create_task(ws_manager.broadcast(event_data))

        return event_data

@app.post("/api/v1/telemetry/batch", status_code=status.HTTP_201_CREATED)
async def ingest_batch_telemetry(payload: BatchTelemetryPayload):
    if not payload.items:
        return {"ingested": 0, "results": []}

    db = await get_db_pool()
    eng = get_engine()
    async with db.acquire() as conn:
        items_dict = [item.model_dump() for item in payload.items]
        evaluations = eng.batch_evaluate(items_dict)

        records_to_insert = []
        for item, ev in zip(payload.items, evaluations):
            records_to_insert.append((
                item.node_id, item.cpu_pct, item.mem_pct, item.disk_pct,
                item.p99_latency_ms, item.error_rate_pct, ev["health_score"], ev["status_label"]
            ))
            await set_node_heartbeat(item.node_id, ttl_seconds=45)

        await conn.executemany(
            """
            INSERT INTO telemetry_logs (node_id, cpu_pct, mem_pct, disk_pct, p99_latency_ms, error_rate_pct, health_score, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8);
            """,
            records_to_insert
        )

        return {
            "ingested": len(records_to_insert),
            "evaluations": evaluations
        }

@app.get("/api/v1/alerts")
async def get_alerts(status_filter: str = "ACTIVE"):
    db = await get_db_pool()
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM incident_alerts WHERE status = $1 ORDER BY created_at DESC LIMIT 50;",
            status_filter
        )
        return [
            {
                "alert_id": r["alert_id"],
                "node_id": r["node_id"],
                "severity": r["severity"],
                "metric_name": r["metric_name"],
                "trigger_value": r["trigger_value"],
                "message": r["message"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat(),
                "resolved_at": r["resolved_at"].isoformat() if r["resolved_at"] else None
            }
            for r in rows
        ]

@app.post("/api/v1/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: int):
    db = await get_db_pool()
    async with db.acquire() as conn:
        res = await conn.execute(
            "UPDATE incident_alerts SET status = 'RESOLVED', resolved_at = NOW() WHERE alert_id = $1;",
            alert_id
        )
        if res == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Alert not found.")
        return {"alert_id": alert_id, "status": "RESOLVED"}

@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        await websocket.send_json({
            "type": "CONNECTED",
            "message": "CloudSentinel WebSocket telemetry feed active"
        })
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "PONG"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
