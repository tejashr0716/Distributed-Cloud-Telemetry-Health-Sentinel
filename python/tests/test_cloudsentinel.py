import json
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from python.api.main import app
from python.services.cpp_bridge import CloudSentinelEngine
from python.database.connection import close_db_pool
from python.services.redis_service import init_redis, set_node_heartbeat, is_node_online, close_redis
from python.spark.spark_telemetry_forecaster import run_telemetry_forecaster

@pytest.fixture(scope="module")
def cpp_engine():
    return CloudSentinelEngine()

@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await close_db_pool()
    await close_redis()

def test_cpp_engine_single_healthy(cpp_engine):
    res = cpp_engine.evaluate_node(cpu=25.0, mem=30.0, disk=40.0, latency=15.0, error_rate=0.01, sla=50.0)
    assert res["health_score"] >= 95.0
    assert res["status_label"] == "HEALTHY"
    assert res["status_code"] == 0

def test_cpp_engine_single_degraded(cpp_engine):
    res = cpp_engine.evaluate_node(cpu=95.0, mem=94.0, disk=96.0, latency=180.0, error_rate=6.5, sla=50.0)
    assert res["health_score"] < 40.0
    assert res["status_label"] in ["DEGRADED", "CRITICAL"]

def test_cpp_engine_batch(cpp_engine):
    items = [
        {"cpu_pct": 20.0, "mem_pct": 30.0, "disk_pct": 40.0, "p99_latency_ms": 10.0, "error_rate_pct": 0.0},
        {"cpu_pct": 98.0, "mem_pct": 99.0, "disk_pct": 90.0, "p99_latency_ms": 300.0, "error_rate_pct": 12.0},
        {"cpu_pct": 50.0, "mem_pct": 60.0, "disk_pct": 50.0, "p99_latency_ms": 35.0, "error_rate_pct": 0.5}
    ]
    res = cpp_engine.batch_evaluate(items)
    assert len(res) == 3
    assert res[0]["status_label"] == "HEALTHY"
    assert res[1]["status_label"] == "CRITICAL"
    assert res[2]["status_label"] == "HEALTHY"

def test_cpp_engine_anomaly_detection(cpp_engine):
    history = [25.0, 24.5, 26.0, 25.2, 24.8, 25.1, 25.5, 24.9, 25.3, 25.0]
    normal_res = cpp_engine.detect_anomaly(history, 25.2)
    assert not normal_res["is_anomaly"]

    spike_res = cpp_engine.detect_anomaly(history, 95.0)
    assert spike_res["is_anomaly"]
    assert spike_res["z_score"] > 3.0

def test_cpp_engine_quorum(cpp_engine):
    scores = [90.0, 95.0, 85.0, 92.0]
    q_score = cpp_engine.quorum_health(scores, min_quorum=2)
    assert q_score > 85.0

    unhealthy_scores = [10.0, 20.0, 90.0]
    low_q = cpp_engine.quorum_health(unhealthy_scores, min_quorum=2)
    assert low_q < 50.0

@pytest.mark.asyncio
async def test_redis_heartbeats():
    await init_redis()
    await set_node_heartbeat("test-node-01", ttl_seconds=10)
    online = await is_node_online("test-node-01")
    assert online is True

    offline = await is_node_online("non-existent-node-xyz")
    assert offline is False
    await close_redis()

@pytest.mark.asyncio
async def test_api_health_endpoint(async_client):
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "HEALTHY"

@pytest.mark.asyncio
async def test_api_regions_and_nodes(async_client):
    r_resp = await async_client.get("/api/v1/regions")
    assert r_resp.status_code == 200
    regions = r_resp.json()
    assert len(regions) >= 4

    n_resp = await async_client.get("/api/v1/nodes")
    assert n_resp.status_code == 200
    nodes = n_resp.json()
    assert len(nodes) >= 12

@pytest.mark.asyncio
async def test_api_telemetry_ingest_and_alert_lifecycle(async_client):
    # Ingest nominal telemetry
    payload_ok = {
        "node_id": "node-us-east-1a",
        "cpu_pct": 32.5,
        "mem_pct": 45.0,
        "disk_pct": 50.0,
        "p99_latency_ms": 22.0,
        "error_rate_pct": 0.02
    }
    resp_ok = await async_client.post("/api/v1/telemetry", json=payload_ok)
    assert resp_ok.status_code == 201
    data_ok = resp_ok.json()
    assert data_ok["evaluation"]["status_label"] == "HEALTHY"
    assert not data_ok["alert_created"]

    # Ingest critical degraded telemetry
    payload_crit = {
        "node_id": "node-us-east-1b",
        "cpu_pct": 98.0,
        "mem_pct": 96.5,
        "disk_pct": 94.0,
        "p99_latency_ms": 280.0,
        "error_rate_pct": 8.5
    }
    resp_crit = await async_client.post("/api/v1/telemetry", json=payload_crit)
    assert resp_crit.status_code == 201
    data_crit = resp_crit.json()
    assert data_crit["alert_created"] is True
    assert data_crit["evaluation"]["status_label"] == "CRITICAL"

    # Check alerts
    alerts_resp = await async_client.get("/api/v1/alerts")
    assert alerts_resp.status_code == 200
    alerts = alerts_resp.json()
    assert len(alerts) >= 1
    active_alert = [a for a in alerts if a["node_id"] == "node-us-east-1b"][0]

    # Resolve alert
    res_resp = await async_client.post(f"/api/v1/alerts/{active_alert['alert_id']}/resolve")
    assert res_resp.status_code == 200
    assert res_resp.json()["status"] == "RESOLVED"

@pytest.mark.asyncio
async def test_api_batch_telemetry(async_client):
    batch_payload = {
        "items": [
            {"node_id": "node-azure-eastus-01", "cpu_pct": 40.0, "mem_pct": 50.0, "disk_pct": 45.0, "p99_latency_ms": 18.0, "error_rate_pct": 0.0},
            {"node_id": "node-azure-eastus-02", "cpu_pct": 45.0, "mem_pct": 55.0, "disk_pct": 50.0, "p99_latency_ms": 22.0, "error_rate_pct": 0.01}
        ]
    }
    b_resp = await async_client.post("/api/v1/telemetry/batch", json=batch_payload)
    assert b_resp.status_code == 201
    res = b_resp.json()
    assert res["ingested"] == 2
    assert len(res["evaluations"]) == 2

def test_spark_forecaster_analytics(tmp_path):
    input_file = str(tmp_path / "telemetry_input.json")
    output_report = str(tmp_path / "telemetry_report.json")

    sample_logs = [
        {"log_id": 1, "node_id": "node-us-east-1a", "region_id": "aws-us-east-1", "cpu_pct": 45.0, "mem_pct": 50.0, "disk_pct": 40.0, "p99_latency_ms": 25.0, "error_rate_pct": 0.01, "health_score": 95.0, "timestamp": "2026-10-17T10:00:00"},
        {"log_id": 2, "node_id": "node-us-east-1a", "region_id": "aws-us-east-1", "cpu_pct": 48.0, "mem_pct": 52.0, "disk_pct": 41.0, "p99_latency_ms": 27.0, "error_rate_pct": 0.02, "health_score": 93.0, "timestamp": "2026-10-17T10:01:00"},
        {"log_id": 3, "node_id": "node-us-east-1b", "region_id": "aws-us-east-1", "cpu_pct": 92.0, "mem_pct": 95.0, "disk_pct": 88.0, "p99_latency_ms": 150.0, "error_rate_pct": 5.2, "health_score": 28.0, "timestamp": "2026-10-17T10:00:00"},
        {"log_id": 4, "node_id": "node-azure-eastus-01", "region_id": "azure-eastus", "cpu_pct": 60.0, "mem_pct": 40.0, "disk_pct": 45.0, "p99_latency_ms": 30.0, "error_rate_pct": 0.0, "health_score": 88.0, "timestamp": "2026-10-17T10:00:00"},
        {"log_id": 5, "node_id": "node-azure-eastus-01", "region_id": "azure-eastus", "cpu_pct": 65.0, "mem_pct": 72.0, "disk_pct": 46.0, "p99_latency_ms": 32.0, "error_rate_pct": 0.0, "health_score": 82.0, "timestamp": "2026-10-17T10:01:00"}
    ]

    with open(input_file, "w") as f:
        for log in sample_logs:
            f.write(json.dumps(log) + "\n")

    report = run_telemetry_forecaster(input_file, output_report)
    assert report["nodes_analyzed"] == 3
    assert len(report["region_sla_compliance"]) >= 2
    assert os.path.exists(output_report)
