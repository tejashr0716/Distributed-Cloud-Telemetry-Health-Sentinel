#include "cloudsentinel.h"
#include <iostream>
#include <chrono>
#include <vector>
#include <random>
#include <iomanip>

int main() {
    std::cout << "========================================================\n";
    std::cout << "   CloudSentinel C++ SIMD Telemetry Benchmark           \n";
    std::cout << "========================================================\n\n";

    const int N = 2000000;
    std::vector<NodeMetrics> metrics(N);
    std::vector<double> slas(N, 50.0);
    std::vector<HealthEvaluation> results(N);

    std::mt19937_64 rng(42);
    std::uniform_real_distribution<double> dist_cpu(10.0, 98.0);
    std::uniform_real_distribution<double> dist_mem(20.0, 99.0);
    std::uniform_real_distribution<double> dist_disk(10.0, 95.0);
    std::uniform_real_distribution<double> dist_lat(5.0, 150.0);
    std::uniform_real_distribution<double> dist_err(0.0, 8.0);

    for (int i = 0; i < N; ++i) {
        metrics[i].cpu_pct = dist_cpu(rng);
        metrics[i].mem_pct = dist_mem(rng);
        metrics[i].disk_pct = dist_disk(rng);
        metrics[i].p99_latency_ms = dist_lat(rng);
        metrics[i].error_rate_pct = dist_err(rng);
    }

    // 1. Single Node Evaluation Benchmark
    auto start = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < N; ++i) {
        evaluate_node_health(&metrics[i], slas[i], &results[i]);
    }
    auto end = std::chrono::high_resolution_clock::now();
    double single_elapsed_sec = std::chrono::duration<double>(end - start).count();
    double single_ops_sec = (double)N / single_elapsed_sec;
    double single_ns_op = (single_elapsed_sec / (double)N) * 1e9;

    std::cout << ">> Single Evaluation Throughput: " << std::fixed << std::setprecision(2)
              << (single_ops_sec / 1e6) << " Million evals/sec ("
              << single_ns_op << " ns/op)\n";

    // 2. Batch Loop-Unrolled SIMD Benchmark
    start = std::chrono::high_resolution_clock::now();
    batch_evaluate_metrics(metrics.data(), slas.data(), N, results.data());
    end = std::chrono::high_resolution_clock::now();
    double batch_elapsed_sec = std::chrono::duration<double>(end - start).count();
    double batch_ops_sec = (double)N / batch_elapsed_sec;
    double batch_ns_op = (batch_elapsed_sec / (double)N) * 1e9;

    std::cout << ">> Batch SIMD Throughput:        " << std::fixed << std::setprecision(2)
              << (batch_ops_sec / 1e6) << " Million evals/sec ("
              << batch_ns_op << " ns/op)\n";

    // 3. Statistical Anomaly Detection Benchmark
    std::vector<double> history(100, 45.0);
    double mean, stddev, zscore;
    int anomaly;
    const int ANOMALY_RUNS = 1000000;
    start = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < ANOMALY_RUNS; ++i) {
        detect_metric_anomalies(history.data(), 100, 95.0, &mean, &stddev, &zscore, &anomaly);
    }
    end = std::chrono::high_resolution_clock::now();
    double anom_elapsed_sec = std::chrono::duration<double>(end - start).count();
    double anom_ops_sec = (double)ANOMALY_RUNS / anom_elapsed_sec;
    double anom_ns_op = (anom_elapsed_sec / (double)ANOMALY_RUNS) * 1e9;

    std::cout << ">> Anomaly Detection Throughput: " << std::fixed << std::setprecision(2)
              << (anom_ops_sec / 1e6) << " Million tests/sec ("
              << anom_ns_op << " ns/op)\n";

    std::cout << "\nSample Evaluated Result:\n";
    std::cout << "  Health Score: " << results[0].health_score
              << " | Status: " << results[0].status_label
              << " | Reason: " << results[0].alert_reason << "\n";
    std::cout << "========================================================\n";

    return 0;
}
