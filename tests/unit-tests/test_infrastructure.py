import json
import sys
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.shared_state import global_state
from agents.infrastructure.sensor import InfrastructureSensor
from agents.infrastructure.voter import InfrastructureVoter

def run_tests():
    sensor = InfrastructureSensor()
    voter = InfrastructureVoter()

    print("=== RUNNING INFRASTRUCTURE AGENT TESTS ===\n")

    # ---------------------------------------------------------
    # TEST 1: Normal Operation
    # ---------------------------------------------------------
    print("TEST 1: Sensor parses Normal Data")
    normal_data = {
        "device_id": "SW_CORE_01",
        "metrics": {"cpu_utilization_pct": 25.0, "interface_errors": 0, "queue_drops": 0}
    }
    alert = sensor.process_telemetry(normal_data)
    print(json.dumps(alert, indent=2))
    assert alert["alert_category"] == "healthy", "Failed Test 1"
    
    # ---------------------------------------------------------
    # TEST 2: Robustness (The Trap)
    # ---------------------------------------------------------
    print("\nTEST 2: Sensor handles Malformed Data (Type Safety)")
    malformed_data = {
        "device_id": "SW_CORE_02",
        "metrics": {"cpu_utilization_pct": "HIGH", "interface_errors": None}
    }
    alert = sensor.process_telemetry(malformed_data)
    print(json.dumps(alert, indent=2))
    assert alert["alert_category"] == "data_error", "Failed Test 2"

    # ---------------------------------------------------------
    # TEST 3: Anomaly Detection
    # ---------------------------------------------------------
    print("\nTEST 3: Sensor detects Hardware Failure")
    hw_fault_data = {
        "device_id": "SW_HOSTEL_01",
        "metrics": {"cpu_utilization_pct": 99.5, "interface_errors": 250, "queue_drops": 5000}
    }
    alert = sensor.process_telemetry(hw_fault_data)
    print(json.dumps(alert, indent=2))
    assert alert["alert_category"] in ("anomaly", "anomaly_detected"), "Failed Test 3"
    assert len(alert["evidence"]) >= 2, "Failed to capture CPU and Interface errors"

    # ---------------------------------------------------------
    # TEST 4: Voting - True Positive
    # ---------------------------------------------------------
    print("\nTEST 4: Voter APPROVES accurate Brain Hypothesis")
    # Note: global_state already has SW_HOSTEL_01's bad metrics from Test 3
    hypothesis_true = {
        "incident_id": "INC-001",
        "proposed_root_cause": "Hardware failure detected on link",
        "target_devices": ["SW_HOSTEL_01"]
    }
    vote = voter.evaluate_hypothesis(hypothesis_true)
    print(json.dumps(vote, indent=2))
    assert vote["vote"] == "APPROVE", "Failed Test 4"

    # ---------------------------------------------------------
    # TEST 5: Voting - Conflict Resolution
    # ---------------------------------------------------------
    print("\nTEST 5: Voter REJECTS inaccurate Brain Hypothesis")
    hypothesis_false = {
        "incident_id": "INC-002",
        "proposed_root_cause": "Link congestion",
        "target_devices": ["SW_HOSTEL_01"]
    }
    vote = voter.evaluate_hypothesis(hypothesis_false)
    print(json.dumps(vote, indent=2))
    assert vote["vote"] == "REJECT", "Failed Test 5"
    assert vote["suggested_alternative"] is not None, "Failed to suggest alternative"

    print("\n=== ALL INFRASTRUCTURE TESTS PASSED ===")

def test_infrastructure():
    run_tests()

if __name__ == "__main__":
    run_tests()
