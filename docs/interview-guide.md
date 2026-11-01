# CloudSentinel: honest interview walkthrough

## 30-second explanation

Synthetic multi-region telemetry prototype with a scalar C++ health-scoring library, PostgreSQL history, Redis windows and best-effort RabbitMQ alerts. No live AWS/Azure integration or explicit SIMD implementation.

I tested the real native library, PostgreSQL/Redis integration, HTTP calls and a same-origin browser demo. I report local measurements with workload and hardware context, rather than presenting CPU-loop throughput as distributed-system throughput. RabbitMQ delivery, Docker execution, optional Spark and a public backend were not validated in this run.

## Show, do not just claim

1. Start the local stack and show `/health`. Explain DEGRADED if RabbitMQ is missing.
2. Open `/demo` and show actual API JSON and WebSocket events.
3. Submit healthy and critical synthetic telemetry, inspect persisted alerts and observe actual WebSocket messages.
4. Explain health scoring, the 30-sample Redis window and Z-score limitations. A threshold heuristic is not machine learning.
5. Show tests for committed alerts, live events, invalid inputs and the explicit unavailable-broker state.
6. Explain why loop unrolling is not automatically SIMD and why a live alert row does not prove broker delivery.

## Safe résumé wording

Built a synthetic telemetry ingestion prototype using FastAPI, a scalar C++17 health-scoring library, PostgreSQL history and Redis windows; demonstrated persisted critical alerts and real WebSocket updates.

If quoting a number, use reports/VALIDATION.md with “local synthetic benchmark” and the test boundary. Do not claim 100% coverage, zero split-brain risk, production readiness or deployed multi-cloud operation. Do not attribute personal reconstruction benchmarks to employer production work without independent employer evidence.
