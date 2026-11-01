#ifndef CLOUDSENTINEL_H
#define CLOUDSENTINEL_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#pragma pack(push, 8)
typedef struct {
    double cpu_pct;          // 0.0 - 100.0
    double mem_pct;          // 0.0 - 100.0
    double disk_pct;         // 0.0 - 100.0
    double p99_latency_ms;   // e.g. 5.0 - 5000.0
    double error_rate_pct;   // 0.0 - 100.0
} NodeMetrics;

typedef struct {
    double health_score;     // 0.0 (Dead/Critical) - 100.0 (Optimal)
    int32_t status_code;     // 0: HEALTHY, 1: WARNING, 2: DEGRADED, 3: CRITICAL
    int32_t is_anomaly;      // 0 or 1
    double z_score;          // statistical deviation
    char status_label[32];   // "HEALTHY", "WARNING", "DEGRADED", "CRITICAL"
    char alert_reason[128];  // descriptive reason if degraded
} HealthEvaluation;
#pragma pack(pop)

// Single node health evaluation
void evaluate_node_health(const NodeMetrics* metrics, double latency_sla_ms, HealthEvaluation* out_eval);

// Scalar loop-unrolled batch node evaluation
void batch_evaluate_metrics(const NodeMetrics* batch, const double* slas, int32_t count, HealthEvaluation* out_evals);

// Statistical Z-score outlier and anomaly detection
void detect_metric_anomalies(const double* metric_series, int32_t count, double current_value,
                            double* out_mean, double* out_stddev, double* out_zscore, int32_t* out_is_anomaly);

// Region quorum-weighted health index calculation
double calculate_region_quorum_health(const double* node_scores, int32_t count, int32_t min_quorum_nodes);

#ifdef __cplusplus
}
#endif

#endif // CLOUDSENTINEL_H
