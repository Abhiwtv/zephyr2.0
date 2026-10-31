import json
from core.shared_state import global_state
from agents.traffic.sensor import TrafficSensor
from agents.traffic.voter import TrafficVoter

def run_tests():
    sensor = TrafficSensor()
    voter = TrafficVoter()

    print("=== RUNNING TRAFFIC AGENT TESTS ===\n")

    # TEST 1: Malformed Data Trap
    print("TEST 1: Sensor handles Malformed Data")
    malformed_data = {
        "device_id": "SW_HOSTEL_02",
        "metrics": {"latency_ms": "timeout", "link_utilization_pct": 50}
    }
    alert = sensor.process_telemetry(malformed_data)
    print(json.dumps(alert, indent=2))
    assert alert["alert_category"] == "data_error", "Failed Test 1"

    # TEST 2: Congestion Anomaly
    print("\nTEST 2: Sensor detects Congestion Spike")
    congestion_data = {
        "device_id": "SW_HOSTEL_03",
        "metrics": {"latency_ms": 280, "link_utilization_pct": 94.5, "packet_loss_pct": 1.2, "jitter_ms": 45}
    }
    alert = sensor.process_telemetry(congestion_data)
    print(json.dumps(alert, indent=2))
    assert alert["alert_category"] == "anomaly", "Failed Test 2"
    assert len(alert["evidence"]) >= 2, "Failed to capture utilization and latency evidence"

    # TEST 3: Voting - True Positive
    print("\nTEST 3: Voter APPROVES Congestion Hypothesis")
    hypothesis_true = {
        "incident_id": "INC-003",
        "proposed_root_cause": "Link congestion causing latency",
        "target_devices": ["SW_HOSTEL_03"]
    }
    vote = voter.evaluate_hypothesis(hypothesis_true)
    print(json.dumps(vote, indent=2))
    assert vote["vote"] == "APPROVE", "Failed Test 3"

    # TEST 4: Voting - Conflict Resolution
    print("\nTEST 4: Voter REJECTS Hardware Hypothesis")
    hypothesis_false = {
        "incident_id": "INC-004",
        "proposed_root_cause": "Hardware failure on uplink",
        "target_devices": ["SW_HOSTEL_03"] # Congestion data (1.2% loss), NOT hardware data (>10% loss)
    }
    vote = voter.evaluate_hypothesis(hypothesis_false)
    print(json.dumps(vote, indent=2))
    assert vote["vote"] == "REJECT", "Failed Test 4"
    assert vote["suggested_alternative"] is not None, "Failed to suggest alternative"

    print("\n=== ALL TRAFFIC TESTS PASSED ===")

if __name__ == "__main__":
    run_tests()