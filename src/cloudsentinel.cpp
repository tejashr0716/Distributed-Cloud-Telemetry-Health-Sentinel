#include "cloudsentinel.h"
#include <cmath>
#include <cstring>
#include <algorithm>
#include <cstdio>

extern "C" {

void evaluate_node_health(const NodeMetrics* metrics, double latency_sla_ms, HealthEvaluation* out_eval) {
    if (!metrics || !out_eval) return;

    std::memset(out_eval, 0, sizeof(HealthEvaluation));

    double penalty = 0.0;
    char reason[128] = "Normal";

    // 1. CPU Penalty
    if (metrics->cpu_pct > 70.0) {
        double excess = metrics->cpu_pct - 70.0;
        penalty += excess * 1.2;
        if (metrics->cpu_pct > 90.0) {
            penalty += (metrics->cpu_pct - 90.0) * 1.8;
            std::snprintf(reason, sizeof(reason), "CPU Thrashing (%.1f%%)", metrics->cpu_pct);
        }
    }

    // 2. Memory Penalty
    if (metrics->mem_pct > 75.0) {
        double excess = metrics->mem_pct - 75.0;
        penalty += excess * 1.3;
        if (metrics->mem_pct > 92.0) {
            penalty += (metrics->mem_pct - 92.0) * 2.0;
            std::snprintf(reason, sizeof(reason), "Memory Pressure (%.1f%%)", metrics->mem_pct);
        }
    }

    // 3. Disk I/O Penalty
    if (metrics->disk_pct > 80.0) {
        double excess = metrics->disk_pct - 80.0;
        penalty += excess * 1.0;
        if (metrics->disk_pct > 95.0) {
            penalty += (metrics->disk_pct - 95.0) * 2.5;
            std::snprintf(reason, sizeof(reason), "Disk Near Saturation (%.1f%%)", metrics->disk_pct);
        }
    }

    // 4. Latency SLA Penalty
    double sla = (latency_sla_ms > 0.0) ? latency_sla_ms : 50.0;
    if (metrics->p99_latency_ms > sla) {
        double ratio = metrics->p99_latency_ms / sla;
        penalty += (ratio - 1.0) * 25.0;
        if (ratio > 3.0) {
            std::snprintf(reason, sizeof(reason), "P99 SLA Breach (%.1fms > %.1fms)", metrics->p99_latency_ms, sla);
        }
    }

    // 5. Error Rate Penalty
    if (metrics->error_rate_pct > 1.0) {
        penalty += metrics->error_rate_pct * 6.0;
        if (metrics->error_rate_pct > 5.0) {
            std::snprintf(reason, sizeof(reason), "Elevated Error Rate (%.2f%%)", metrics->error_rate_pct);
        }
    }

    double final_score = 100.0 - penalty;
    if (final_score < 0.0) final_score = 0.0;
    if (final_score > 100.0) final_score = 100.0;

    out_eval->health_score = final_score;
    out_eval->is_anomaly = 0;
    out_eval->z_score = 0.0;

    if (final_score >= 85.0) {
        out_eval->status_code = 0;
        std::strncpy(out_eval->status_label, "HEALTHY", sizeof(out_eval->status_label) - 1);
        std::strncpy(out_eval->alert_reason, "All systems nominal", sizeof(out_eval->alert_reason) - 1);
    } else if (final_score >= 65.0) {
        out_eval->status_code = 1;
        std::strncpy(out_eval->status_label, "WARNING", sizeof(out_eval->status_label) - 1);
        std::strncpy(out_eval->alert_reason, reason, sizeof(out_eval->alert_reason) - 1);
    } else if (final_score >= 35.0) {
        out_eval->status_code = 2;
        std::strncpy(out_eval->status_label, "DEGRADED", sizeof(out_eval->status_label) - 1);
        std::strncpy(out_eval->alert_reason, reason, sizeof(out_eval->alert_reason) - 1);
    } else {
        out_eval->status_code = 3;
        std::strncpy(out_eval->status_label, "CRITICAL", sizeof(out_eval->status_label) - 1);
        std::strncpy(out_eval->alert_reason, reason, sizeof(out_eval->alert_reason) - 1);
    }
}

void batch_evaluate_metrics(const NodeMetrics* batch, const double* slas, int32_t count, HealthEvaluation* out_evals) {
    if (!batch || !out_evals || count <= 0) return;

    // Process with unrolled loop for SIMD auto-vectorization
    int32_t i = 0;
    for (; i <= count - 4; i += 4) {
        evaluate_node_health(&batch[i], slas ? slas[i] : 50.0, &out_evals[i]);
        evaluate_node_health(&batch[i+1], slas ? slas[i+1] : 50.0, &out_evals[i+1]);
        evaluate_node_health(&batch[i+2], slas ? slas[i+2] : 50.0, &out_evals[i+2]);
        evaluate_node_health(&batch[i+3], slas ? slas[i+3] : 50.0, &out_evals[i+3]);
    }
    for (; i < count; ++i) {
        evaluate_node_health(&batch[i], slas ? slas[i] : 50.0, &out_evals[i]);
    }
}

void detect_metric_anomalies(const double* metric_series, int32_t count, double current_value,
                            double* out_mean, double* out_stddev, double* out_zscore, int32_t* out_is_anomaly) {
    if (!metric_series || count <= 1) {
        if (out_mean) *out_mean = current_value;
        if (out_stddev) *out_stddev = 0.0;
        if (out_zscore) *out_zscore = 0.0;
        if (out_is_anomaly) *out_is_anomaly = 0;
        return;
    }

    double sum = 0.0;
    for (int32_t i = 0; i < count; ++i) {
        sum += metric_series[i];
    }
    double mean = sum / (double)count;

    double var_sum = 0.0;
    for (int32_t i = 0; i < count; ++i) {
        double diff = metric_series[i] - mean;
        var_sum += diff * diff;
    }
    double stddev = std::sqrt(var_sum / (double)(count - 1));

    double z = 0.0;
    int32_t anomaly = 0;
    if (stddev > 0.0001) {
        z = (current_value - mean) / stddev;
        if (std::fabs(z) >= 2.5) {
            anomaly = 1;
        }
    }

    if (out_mean) *out_mean = mean;
    if (out_stddev) *out_stddev = stddev;
    if (out_zscore) *out_zscore = z;
    if (out_is_anomaly) *out_is_anomaly = anomaly;
}

double calculate_region_quorum_health(const double* node_scores, int32_t count, int32_t min_quorum_nodes) {
    if (!node_scores || count <= 0) return 0.0;

    int32_t healthy_nodes = 0;
    double score_sum = 0.0;

    for (int32_t i = 0; i < count; ++i) {
        score_sum += node_scores[i];
        if (node_scores[i] >= 65.0) {
            healthy_nodes++;
        }
    }

    double avg_score = score_sum / (double)count;

    // Quorum check penalty
    if (min_quorum_nodes > 0 && healthy_nodes < min_quorum_nodes) {
        double quorum_deficit_pct = (double)(min_quorum_nodes - healthy_nodes) / (double)min_quorum_nodes;
        avg_score = avg_score * (1.0 - (0.5 * quorum_deficit_pct));
    }

    return std::max(0.0, std::min(100.0, avg_score));
}

} // extern "C"
