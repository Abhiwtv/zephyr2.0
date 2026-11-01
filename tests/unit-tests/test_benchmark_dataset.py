import json
import os
import sys

# Ensure repository root is on sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from agents.infrastructure.sensor import InfrastructureSensor
from agents.traffic.sensor import TrafficSensor
from agents.l4_l7.sensor import L4L7Sensor

def load_first_10_benchmark_items():
    candidate_paths = [
        os.path.join(REPO_ROOT, "data", "iit_bbs_benchmark_dataset.json"),
        os.path.join(REPO_ROOT, "iit_bbs_benchmark_dataset.json"),
        os.path.join("data", "iit_bbs_benchmark_dataset.json"),
        "iit_bbs_benchmark_dataset.json"
    ]
    dataset_file = next((p for p in candidate_paths if os.path.exists(p)), None)
    assert dataset_file is not None, f"iit_bbs_benchmark_dataset.json not found in candidate paths: {candidate_paths}"

    with open(dataset_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, list) and len(data) >= 10, "Dataset must contain at least 10 items"
    # Default to first 10 items
    return data[:10]

def run_tests():
    print("=== RUNNING BENCHMARK DATASET UNIT TESTS (FIRST 10 ITEMS) ===\n")
    items = load_first_10_benchmark_items()
    assert len(items) == 10, f"Expected 10 items, got {len(items)}"

    infra_sensor = InfrastructureSensor()
    traffic_sensor = TrafficSensor()
    l4_sensor = L4L7Sensor()

    for idx, item in enumerate(items):
        scenario = item.get("scenario", f"item_{idx}")
        payload = item.get("payload", {})
        status = payload.get("status", "Unknown")
        device_id = payload.get("device_id")

        print(f"[{idx+1:02d}/10] Testing scenario: {scenario} (Device: {device_id}, Status: {status})")

        assert device_id, f"Item {idx} missing device_id"
        assert "metrics" in payload, f"Item {idx} missing metrics"

        # Ingest through all three sensors
        alert_infra = infra_sensor.process_telemetry(payload)
        alert_traffic = traffic_sensor.process_telemetry(payload)
        alert_l4 = l4_sensor.process_telemetry(payload)

        for alert in [alert_infra, alert_traffic, alert_l4]:
            assert "domain" in alert
            assert "alert_category" in alert
            assert "anomaly_score" in alert

        # If ground truth was Critical, at least one sensor should detect an anomaly or error
        if status == "Critical":
            scores = [alert_infra["anomaly_score"], alert_traffic["anomaly_score"], alert_l4["anomaly_score"]]
            has_anomaly = any(s > 0 for s in scores) or any(a["alert_category"] != "healthy" for a in [alert_infra, alert_traffic, alert_l4])
            assert has_anomaly, f"Critical scenario {scenario} triggered no sensor anomalies"

    print("\n=== ALL 10 BENCHMARK DATASET ITEMS VALIDATED SUCCESSFULLY ===")

def test_benchmark_dataset_first_10_items():
    run_tests()

if __name__ == "__main__":
    run_tests()
