import asyncio, os, json
import pytest, httpx, websockets
BASE=os.getenv('BASE_URL','http://127.0.0.1:8011')
def telemetry():return dict(node_id='node-us-east-1a',cpu_pct=99,mem_pct=98,disk_pct=95,p99_latency_ms=500,error_rate_pct=15)
@pytest.mark.asyncio
async def test_real_ingest_persist_alert_and_websocket():
 async with websockets.connect(BASE.replace('http','ws')+'/ws/telemetry') as ws:
  await ws.recv()
  async with httpx.AsyncClient() as c:
   r=await c.post(BASE+'/api/v1/telemetry',json=telemetry());assert r.status_code==201,r.text
   data=r.json();assert data['alert_created'] and data['evaluation']['status_label']=='CRITICAL'
   msg=json.loads(await asyncio.wait_for(ws.recv(),3));assert msg['log_id']==data['log_id']
   alerts=(await c.get(BASE+'/api/v1/alerts')).json();assert any(a['node_id']=='node-us-east-1a' for a in alerts)
@pytest.mark.asyncio
async def test_health_honestly_exposes_broker_status():
 async with httpx.AsyncClient() as c:
  d=(await c.get(BASE+'/health')).json();assert d['database']=='reachable';assert d['broker'] in ['connected','unavailable']
  if d['broker']=='unavailable':assert d['status']=='DEGRADED'
@pytest.mark.asyncio
async def test_invalid_payload_rejected():
 async with httpx.AsyncClient() as c:
  p=telemetry();p['cpu_pct']=101
  assert (await c.post(BASE+'/api/v1/telemetry',json=p)).status_code==422
  assert (await c.post(BASE+'/api/v1/telemetry/batch',json={'items':[telemetry()]*1001})).status_code==422
