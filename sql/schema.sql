-- CloudSentinel Distributed Multi-Region Telemetry Schema

CREATE TABLE IF NOT EXISTS regions (
    region_id VARCHAR(32) PRIMARY KEY,
    provider VARCHAR(32) NOT NULL,
    location VARCHAR(64) NOT NULL,
    status VARCHAR(32) DEFAULT 'HEALTHY',
    latency_sla_ms DOUBLE PRECISION DEFAULT 50.0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nodes (
    node_id VARCHAR(64) PRIMARY KEY,
    region_id VARCHAR(32) NOT NULL REFERENCES regions(region_id) ON DELETE CASCADE,
    hostname VARCHAR(128) NOT NULL,
    instance_type VARCHAR(64) NOT NULL,
    ip_address VARCHAR(45) NOT NULL,
    status VARCHAR(32) DEFAULT 'ONLINE',
    last_heartbeat_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS telemetry_logs (
    log_id BIGSERIAL PRIMARY KEY,
    node_id VARCHAR(64) NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    cpu_pct DOUBLE PRECISION NOT NULL,
    mem_pct DOUBLE PRECISION NOT NULL,
    disk_pct DOUBLE PRECISION NOT NULL,
    p99_latency_ms DOUBLE PRECISION NOT NULL,
    error_rate_pct DOUBLE PRECISION NOT NULL,
    health_score DOUBLE PRECISION NOT NULL,
    status VARCHAR(32) NOT NULL,
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS incident_alerts (
    alert_id BIGSERIAL PRIMARY KEY,
    node_id VARCHAR(64) NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    severity VARCHAR(32) NOT NULL, -- WARNING, CRITICAL, FATAL
    metric_name VARCHAR(64) NOT NULL,
    trigger_value DOUBLE PRECISION NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(32) DEFAULT 'ACTIVE', -- ACTIVE, ACKNOWLEDGED, RESOLVED
    created_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_telemetry_node_time ON telemetry_logs(node_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_health ON telemetry_logs(health_score);
CREATE INDEX IF NOT EXISTS idx_nodes_region ON nodes(region_id);
CREATE INDEX IF NOT EXISTS idx_alerts_node_status ON incident_alerts(node_id, status);

-- Seed Initial Cloud Topology
INSERT INTO regions (region_id, provider, location, status, latency_sla_ms) VALUES
('aws-us-east-1', 'AWS', 'N. Virginia, USA', 'HEALTHY', 35.0),
('aws-eu-west-1', 'AWS', 'Dublin, Ireland', 'HEALTHY', 45.0),
('azure-eastus', 'Azure', 'Virginia, USA', 'HEALTHY', 38.0),
('azure-westeurope', 'Azure', 'Amsterdam, Netherlands', 'HEALTHY', 42.0) ON CONFLICT DO NOTHING;

INSERT INTO nodes (node_id, region_id, hostname, instance_type, ip_address, status) VALUES
('node-us-east-1a', 'aws-us-east-1', 'prod-ingress-01.us-east.aws', 'c6i.4xlarge', '10.0.1.15', 'ONLINE'),
('node-us-east-1b', 'aws-us-east-1', 'prod-worker-01.us-east.aws', 'r6i.2xlarge', '10.0.1.16', 'ONLINE'),
('node-us-east-1c', 'aws-us-east-1', 'prod-db-replica-01.us-east.aws', 'r6i.8xlarge', '10.0.1.17', 'ONLINE'),
('node-eu-west-1a', 'aws-eu-west-1', 'prod-ingress-01.eu-west.aws', 'c6i.4xlarge', '10.1.1.20', 'ONLINE'),
('node-eu-west-1b', 'aws-eu-west-1', 'prod-worker-01.eu-west.aws', 'r6i.2xlarge', '10.1.1.21', 'ONLINE'),
('node-eu-west-1c', 'aws-eu-west-1', 'prod-cache-01.eu-west.aws', 'r6g.xlarge', '10.1.1.22', 'ONLINE'),
('node-azure-eastus-01', 'azure-eastus', 'vm-gateway-01.eastus.cloud', 'Standard_D16s_v5', '10.2.1.10', 'ONLINE'),
('node-azure-eastus-02', 'azure-eastus', 'vm-compute-01.eastus.cloud', 'Standard_E8s_v5', '10.2.1.11', 'ONLINE'),
('node-azure-eastus-03', 'azure-eastus', 'vm-storage-01.eastus.cloud', 'Standard_L8s_v3', '10.2.1.12', 'ONLINE'),
('node-azure-weur-01', 'azure-westeurope', 'vm-gateway-01.westeur.cloud', 'Standard_D16s_v5', '10.3.1.5', 'ONLINE'),
('node-azure-weur-02', 'azure-westeurope', 'vm-compute-01.westeur.cloud', 'Standard_E8s_v5', '10.3.1.6', 'ONLINE'),
('node-azure-weur-03', 'azure-westeurope', 'vm-analytics-01.westeur.cloud', 'Standard_E16s_v5', '10.3.1.7', 'ONLINE') ON CONFLICT DO NOTHING;
