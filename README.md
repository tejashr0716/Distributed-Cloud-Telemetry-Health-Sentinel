# CloudSentinel — educational local prototype

Synthetic multi-region telemetry prototype with a scalar C++ health-scoring library, PostgreSQL history, Redis windows and best-effort RabbitMQ alerts. No live AWS/Azure integration or explicit SIMD implementation.

**Security boundary:** no authentication, authorization, rate limiting or public-hosting hardening. Bind to loopback only. This is not production-ready and has not been publicly deployed by this remediation.

## Start a disposable local demo

Python 3.13 and C++17 are the tested runtime family. PostgreSQL 16 and Redis are required. RabbitMQ is optional for degraded local demonstrations; unavailable broker state is reported explicitly. Spark is optional and not installed in the supplied validation run.

### Docker Compose (configuration supplied; not executed in this audit)

```bash
docker compose up --build -d
docker compose ps
# Open http://127.0.0.1:8001/demo
```

Compose binds published ports to 127.0.0.1. Its database passwords are local demo defaults, not production secrets. Initial schema runs only on an empty Docker database volume. Never use `docker compose down -v` on data you need. Image tags are not immutable digests.

### Native processes (this path was actually tested on Linux)

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./scripts/build_native.sh
export POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5432
export POSTGRES_DB=cloudsentinel_db POSTGRES_USER=your_local_user
export POSTGRES_PASSWORD=your_local_password
export REDIS_HOST=127.0.0.1 REDIS_PORT=6379
# Create the database first, then initialize a fresh/disposable database:
psql -v ON_ERROR_STOP=1 -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f sql/schema.sql
uvicorn python.api.main:app --host 127.0.0.1 --port 8011
# Open http://127.0.0.1:8011/demo
```

Set `PGPASSWORD` privately for psql if needed; it does not read POSTGRES_PASSWORD. Do not commit credentials. Services in the supplied audit used isolated PostgreSQL port 55432 and Redis port 56379, not your system services. The build script emits the host's `.so` or `.dylib`; no precompiled Mac binaries are shipped.

## Test and benchmark

Start the gateway above before running the real HTTP suite. These tests and benchmarks mutate a **disposable** local database.

```bash
source .venv/bin/activate
export BASE_URL=http://127.0.0.1:8011
PYTHONPATH=. pytest python/tests tests -v --junitxml=reports/tests.xml
./scripts/build_native.sh > reports/native-benchmark.txt
python benchmarks/run_real_http_benchmark.py
```

The HTTP script defaults to three trials of 200 requests, concurrency 10, ten warmups per trial (none for contention); it records successes, status counts and raw timings. Latency is complete request/response time over loopback TCP, **not network transit time alone**. Failed requests are not counted as successful throughput. Measurements are not cloud SLAs. Native numbers have zero HTTP/database/network work and must never be presented as distributed throughput.

The legacy Spark test explicitly skips without PySpark. A skipped test is not a passing test and test pass rate is not code coverage. Installing Spark additionally requires a compatible PySpark/Java combination; that path is unverified here.

## Actual dashboard vs static showcase

`/demo` is served by FastAPI and calls same-origin API/WebSocket endpoints. It shows actual response JSON, dependency status and bounded reconnect attempts. `web/index.html` is an informational static showcase only, not a backend simulation or performance measurement. Publishing that HTML to GitHub Pages does not deploy Python, C++, PostgreSQL or RabbitMQ.

WebSocket events are best-effort and **process-local**: clients connected to another gateway process do not receive them. Slow sends are bounded by a two-second timeout per client; sequential broadcasts can still delay responses with many slow clients. There is no durable replay, outbox or exactly-once delivery. SQL commits and external notifications are not one atomic operation.

## Validation and publication

See `reports/VALIDATION.md`, `reports/tests.log`, JUnit XML, native output and real HTTP JSON. CI configuration has been repaired to build Linux `.so` and run the HTTP suite, but a remote CI run was not performed. Docker and RabbitMQ delivery were not executed here. No cloud integration, crash-recovery proof or production resilience claim is implied. Local fixes must be reviewed, committed and pushed by the repository owner; public GitHub and Pages are unchanged until that happens.

## Telemetry semantics and remaining limitations

Regions and nodes are seeded synthetic labels, not live AWS CloudWatch or Azure Monitor connectors. Health is a configurable-style heuristic, not a proven predictive model. The batch loop is scalar, unrolled by four; no explicit SIMD or measured speedup attribution is claimed.

Single-event telemetry and any resulting alert rows are committed together before notification. Redis rolling history, RabbitMQ publication and WebSocket messages occur after SQL commit and are best-effort. A committed alert can therefore exist without a delivered broker notification. No worker acknowledgement or durable outbox delivery has been verified. Batch ingestion does not offer atomic cross-service consistency; concurrent rolling-window updates are not a linearizable global stream. Restart does not reconstruct every Redis history window from PostgreSQL.

`sql/schema.sql` now preserves tables and skips duplicate seed IDs. It is not a general migration framework; schema changes on existing installations require explicit reviewed migrations. JSON health measurements reject non-finite values; batches are limited to 1,000 items.
