"""
CloudSentinel Apache Spark Telemetry Forecaster & Anomaly Pipeline
Calculates rolling node degradation slopes, resource exhaustion forecasting, and SLA compliance.
"""

import os
import sys
import json
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType, TimestampType, LongType
)

def build_spark_session(app_name: str = "CloudSentinel-Telemetry-Analytics") -> SparkSession:
    return (
        SparkSession.builder
        .appName(app_name)
        .master("local[*]")
        .config("spark.driver.memory", "2g")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )

def run_telemetry_forecaster(input_data_path: str, output_report_path: str):
    spark = build_spark_session()
    spark.sparkContext.setLogLevel("WARN")

    schema = StructType([
        StructField("log_id", LongType(), True),
        StructField("node_id", StringType(), True),
        StructField("region_id", StringType(), True),
        StructField("cpu_pct", DoubleType(), True),
        StructField("mem_pct", DoubleType(), True),
        StructField("disk_pct", DoubleType(), True),
        StructField("p99_latency_ms", DoubleType(), True),
        StructField("error_rate_pct", DoubleType(), True),
        StructField("health_score", DoubleType(), True),
        StructField("timestamp", StringType(), True)
    ])

    df = spark.read.schema(schema).json(input_data_path)

    # 1. Rolling Aggregate Metrics per Node
    node_summary = df.groupBy("node_id", "region_id").agg(
        F.count("log_id").alias("sample_count"),
        F.round(F.avg("cpu_pct"), 2).alias("avg_cpu_pct"),
        F.round(F.max("cpu_pct"), 2).alias("peak_cpu_pct"),
        F.round(F.avg("mem_pct"), 2).alias("avg_mem_pct"),
        F.round(F.max("mem_pct"), 2).alias("peak_mem_pct"),
        F.round(F.avg("p99_latency_ms"), 2).alias("avg_latency_ms"),
        F.round(F.expr("percentile_approx(p99_latency_ms, 0.99)"), 2).alias("p99_sla_latency_ms"),
        F.round(F.avg("health_score"), 2).alias("avg_health_score"),
        F.round(F.min("health_score"), 2).alias("min_health_score")
    )

    # 2. Memory Degradation & Leak Detection Slope
    window_spec = Window.partitionBy("node_id").orderBy("timestamp")
    df_windowed = df.withColumn("row_num", F.row_number().over(window_spec))

    # Slope approximation: (mem_latest - mem_first) / count
    mem_trend = df_windowed.groupBy("node_id").agg(
        F.first("mem_pct").alias("initial_mem"),
        F.last("mem_pct").alias("latest_mem"),
        F.count("log_id").alias("count")
    ).withColumn("mem_growth_pct", F.round(F.col("latest_mem") - F.col("initial_mem"), 2))

    # Join results
    analytics = node_summary.join(mem_trend.select("node_id", "mem_growth_pct"), on="node_id")

    # Add Automated Sentinel Action Recommendation
    analytics = analytics.withColumn(
        "recommended_action",
        F.when(F.col("min_health_score") < 35.0, "DRAIN_AND_REPLACE")
         .when(F.col("mem_growth_pct") > 15.0, "INVESTIGATE_MEMORY_LEAK")
         .when(F.col("avg_cpu_pct") > 80.0, "HORIZONTAL_SCALE_OUT")
         .otherwise("NOMINAL")
    )

    results = [row.asDict() for row in analytics.collect()]

    # SLA Compliance per Region
    sla_compliance = df.groupBy("region_id").agg(
        F.round(F.avg(F.when(F.col("p99_latency_ms") <= 50.0, 1.0).otherwise(0.0)) * 100.0, 2).alias("sla_compliance_pct")
    )
    sla_results = [row.asDict() for row in sla_compliance.collect()]

    report = {
        "engine": "Apache Spark 4.2 Telemetry Forecaster",
        "nodes_analyzed": len(results),
        "node_analytics": results,
        "region_sla_compliance": sla_results
    }

    os.makedirs(os.path.dirname(output_report_path), exist_ok=True)
    with open(output_report_path, "w") as f:
        json.dump(report, f, indent=2)

    spark.stop()
    return report

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: spark_telemetry_forecaster.py <input_json> <output_json>")
        sys.exit(1)
    run_telemetry_forecaster(sys.argv[1], sys.argv[2])
