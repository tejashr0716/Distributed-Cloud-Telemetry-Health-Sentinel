import ctypes
import os
from typing import List, Dict, Any, Optional

class CNodeMetrics(ctypes.Structure):
    _layout_ = "ms"
    _pack_ = 8
    _fields_ = [
        ("cpu_pct", ctypes.c_double),
        ("mem_pct", ctypes.c_double),
        ("disk_pct", ctypes.c_double),
        ("p99_latency_ms", ctypes.c_double),
        ("error_rate_pct", ctypes.c_double)
    ]

class CHealthEvaluation(ctypes.Structure):
    _layout_ = "ms"
    _pack_ = 8
    _fields_ = [
        ("health_score", ctypes.c_double),
        ("status_code", ctypes.c_int32),
        ("is_anomaly", ctypes.c_int32),
        ("z_score", ctypes.c_double),
        ("status_label", ctypes.c_char * 32),
        ("alert_reason", ctypes.c_char * 128)
    ]

class CloudSentinelEngine:
    def __init__(self, dylib_path: Optional[str] = None):
        if dylib_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            dylib_path = os.path.join(base_dir, "libcloudsentinel.dylib")

        if not os.path.exists(dylib_path):
            raise FileNotFoundError(f"Shared library not found at: {dylib_path}")

        self.lib = ctypes.CDLL(dylib_path)

        # void evaluate_node_health(const NodeMetrics* metrics, double latency_sla_ms, HealthEvaluation* out_eval);
        self.lib.evaluate_node_health.argtypes = [
            ctypes.POINTER(CNodeMetrics),
            ctypes.c_double,
            ctypes.POINTER(CHealthEvaluation)
        ]
        self.lib.evaluate_node_health.restype = None

        # void batch_evaluate_metrics(const NodeMetrics* batch, const double* slas, int32_t count, HealthEvaluation* out_evals);
        self.lib.batch_evaluate_metrics.argtypes = [
            ctypes.POINTER(CNodeMetrics),
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_int32,
            ctypes.POINTER(CHealthEvaluation)
        ]
        self.lib.batch_evaluate_metrics.restype = None

        # void detect_metric_anomalies(...)
        self.lib.detect_metric_anomalies.argtypes = [
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_int32,
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_int32)
        ]
        self.lib.detect_metric_anomalies.restype = None

        # double calculate_region_quorum_health(const double* node_scores, int32_t count, int32_t min_quorum_nodes);
        self.lib.calculate_region_quorum_health.argtypes = [
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_int32,
            ctypes.c_int32
        ]
        self.lib.calculate_region_quorum_health.restype = ctypes.c_double

    def evaluate_node(self, cpu: float, mem: float, disk: float, latency: float, error_rate: float, sla: float = 50.0) -> Dict[str, Any]:
        metrics = CNodeMetrics(
            cpu_pct=float(cpu),
            mem_pct=float(mem),
            disk_pct=float(disk),
            p99_latency_ms=float(latency),
            error_rate_pct=float(error_rate)
        )
        eval_result = CHealthEvaluation()
        self.lib.evaluate_node_health(ctypes.byref(metrics), ctypes.c_double(sla), ctypes.byref(eval_result))

        return {
            "health_score": round(eval_result.health_score, 2),
            "status_code": eval_result.status_code,
            "status_label": eval_result.status_label.decode("utf-8"),
            "alert_reason": eval_result.alert_reason.decode("utf-8"),
            "is_anomaly": bool(eval_result.is_anomaly),
            "z_score": round(eval_result.z_score, 2)
        }

    def batch_evaluate(self, items: List[Dict[str, float]], slas: Optional[List[float]] = None) -> List[Dict[str, Any]]:
        n = len(items)
        if n == 0:
            return []

        if slas is None:
            slas = [50.0] * n

        metrics_arr = (CNodeMetrics * n)()
        slas_arr = (ctypes.c_double * n)()
        results_arr = (CHealthEvaluation * n)()

        for i, item in enumerate(items):
            metrics_arr[i] = CNodeMetrics(
                cpu_pct=float(item.get("cpu_pct", 0.0)),
                mem_pct=float(item.get("mem_pct", 0.0)),
                disk_pct=float(item.get("disk_pct", 0.0)),
                p99_latency_ms=float(item.get("p99_latency_ms", 20.0)),
                error_rate_pct=float(item.get("error_rate_pct", 0.0))
            )
            slas_arr[i] = float(slas[i])

        self.lib.batch_evaluate_metrics(metrics_arr, slas_arr, ctypes.c_int32(n), results_arr)

        output = []
        for i in range(n):
            res = results_arr[i]
            output.append({
                "health_score": round(res.health_score, 2),
                "status_code": res.status_code,
                "status_label": res.status_label.decode("utf-8"),
                "alert_reason": res.alert_reason.decode("utf-8")
            })
        return output

    def detect_anomaly(self, series: List[float], current_val: float) -> Dict[str, Any]:
        count = len(series)
        series_arr = (ctypes.c_double * count)(*series)
        mean = ctypes.c_double()
        stddev = ctypes.c_double()
        zscore = ctypes.c_double()
        is_anom = ctypes.c_int32()

        self.lib.detect_metric_anomalies(
            series_arr,
            ctypes.c_int32(count),
            ctypes.c_double(current_val),
            ctypes.byref(mean),
            ctypes.byref(stddev),
            ctypes.byref(zscore),
            ctypes.byref(is_anom)
        )

        return {
            "mean": round(mean.value, 2),
            "stddev": round(stddev.value, 4),
            "z_score": round(zscore.value, 2),
            "is_anomaly": bool(is_anom.value)
        }

    def quorum_health(self, scores: List[float], min_quorum: int = 1) -> float:
        n = len(scores)
        if n == 0:
            return 0.0
        scores_arr = (ctypes.c_double * n)(*scores)
        score = self.lib.calculate_region_quorum_health(scores_arr, ctypes.c_int32(n), ctypes.c_int32(min_quorum))
        return round(score, 2)
