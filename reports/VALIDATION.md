# Independent local validation: cloudsentinel

Generated: 2026-11-01T13:53:14.920863+00:00

## What was actually executed

- **13 tests passed; 1 optional Spark test skipped.** No coverage percentage was measured.
- Real PostgreSQL 16.4, real Redis server, native C++ shared library and Uvicorn HTTP endpoints. RabbitMQ was unavailable; this is an intentionally **DEGRADED broker configuration**, not the full messaging stack.
- Chromium browser: actual /demo API interactions and WebSocket events succeeded; zero page errors; no overflow at 390px viewport. Desktop/mobile screenshots are included.
- Docker build, remote GitHub Actions CI, public backend hosting, AWS/Azure provider connectors and optional Spark were **not executed**. Configuration changes are not execution proof.

## Environment

- OS: Linux-6.18.56-x86_64-with-glibc2.34
- CPU: Intel(R) Xeon(R) Processor @ 2.50GHz; shared virtualized audit machine, not dedicated benchmark hardware.
- Python: 3.13.15
- Compiler: g++ (GCC) 11.5.0 20240719 (Red Hat 11.5.0-5); optimized C++17 dynamic library (-O3).
- Dependencies: requirements.lock. Extra audit-only tools (embedded PostgreSQL distribution, redislite, Playwright, YAML parser) are not application runtime dependencies.

## Real HTTP performance

Three trials per scenario, 200 measured requests per trial, concurrency 10, ten warmups except contention; loopback TCP and full JSON request/response. The two final project benchmarks ran sequentially. Other host activity cannot be eliminated. Statistics below are medians of per-trial results, not a fabricated pooled percentile.

| Scenario | Observed result | Boundary / caveat |
|---|---|---|
| telemetry | 343.0 successful requests/s | 25.23 ms median of trial P50s; 600/600 measured requests succeeded |

Broker state in benchmark: `unavailable`. Do not describe these results as RabbitMQ-confirmed end-to-end delivery or as pure network transit latency. The HTTP harness retains raw statuses and all timings, including rejections. Results are local synthetic measurements, not production SLAs or a reproduction of the user's Apple Silicon numbers.

HTTP benchmark source revision: `31ca829daf6284e7d3615bc0919a9d2fb933d76a`; dirty flag `True` because local evidence artifacts were present. Source implementation revisions are preserved in the supplied Git bundle. Subsequent export/browser harness and documentation-only changes do not alter the measured request paths.

## CPU-only native output

This is local function execution, **not distributed throughput**, not database commit rate, and not a network benchmark. Native runs were not repeated statistical trials. The two native builds/runs overlapped on the shared host; do not use their numbers as isolated hardware comparisons. No claim that all benchmark data fits in L1 cache is made.

```text
========================================================
   CloudSentinel C++ scalar loop-unrolled Telemetry Benchmark           
========================================================

>> Single Evaluation Throughput: 4.66 Million evals/sec (214.39 ns/op)
>> Batch scalar throughput:        4.62 Million evals/sec (216.26 ns/op)
>> Anomaly Detection Throughput: 4.15 Million tests/sec (241.12 ns/op)

Sample Evaluated Result:
  Health Score: 48.90 | Status: DEGRADED | Reason: Elevated Error Rate (7.23%)
========================================================
```

The scalar batch run was slightly slower than single evaluation in this sample. No claim that unrolling improves performance, reduces branch misprediction or generates SIMD follows from that result.

## Correctness fixes and evidence

| Fix | Implementation | Executed evidence |
|---|---|---|
| Honest cloud/SIMD scope | Synthetic region labels, scalar C++ documentation | Code inspection and native tests; no provider calls claimed |
| Persist before side effects | Telemetry and alert SQL transaction precedes best-effort notifications | Real critical ingestion creates alert row and sends matching WebSocket log ID |
| Dependency transparency | Broker unavailable reported as DEGRADED | Actual health response and HTTP test |
| Input bounds | Finite metric values; batch max 1000 | Real API invalid CPU and oversized batch tests |
| Preserve data on bootstrap reapply | IF NOT EXISTS and duplicate-seed skip | schema-reapply.json records unchanged telemetry count |

RabbitMQ alert delivery and consumer acknowledgements are not demonstrated by a persisted SQL alert or WebSocket message. Redis windows, SQL and broker publication are not one distributed transaction. No outbox or guaranteed replay exists.

## Files containing execution evidence

- tests.log and tests.xml: exact pytest output, including skipped Spark.
- native-benchmark.txt: terminal output from source compilation/run.
- real-http-benchmark.json and .log: trial definitions, environment, complete raw samples and statuses.
- browser-check.json/.log and browser-desktop.png / browser-mobile.png.

## Safe résumé wording

Built a synthetic telemetry ingestion prototype integrating FastAPI, a scalar C++17 scoring library, PostgreSQL history and Redis windows; validated persisted critical alerts and real WebSocket updates.

Metrics may be added only with “local synthetic benchmark” and explicit boundary. Do not claim autonomous Raft, zero split-brain risk, SIMD speedups, live multi-cloud integration, production readiness or 100% code coverage. Personal reconstruction benchmarks are not employer production outcomes.
