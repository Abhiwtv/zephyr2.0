import json
from core.shared_state import global_state
from agents.l4_l7.sensor import L4L7Sensor
from agents.l4_l7.voter import L4L7Voter

def run_tests():
    sensor = L4L7Sensor()
    voter = L4L7Voter()

    print("=== RUNNING L4-L7 AGENT TESTS ===\n")

    # TEST 1: Handles standard data (Missing L4 keys = Healthy)
    print("TEST 1: Sensor parses data without L4 keys (Defaults to Healthy)")
    standard_data = {
        "device_id": "SW_CORE_01",
        "metrics": {"cpu_utilization_pct": 25.0} # No DNS/DHCP data here
    }
    alert = sensor.process_telemetry(standard_data)
    print(json.dumps(alert, indent=2))
    assert alert["alert_category"] == "healthy", "Failed Test 1"

    # TEST 2: DNS Failure Detection
    print("\nTEST 2: Sensor detects DNS Failure Spike")
    dns_fault_data = {
        "device_id": "SRV_DNS_01",
        "metrics": {"dns_latency_ms": 500, "dhcp_pool_utilization_pct": 40.0}
    }
    alert = sensor.process_telemetry(dns_fault_data)
    print(json.dumps(alert, indent=2))
    assert alert["alert_category"] in ("anomaly", "anomaly_detected"), "Failed Test 2"

    # TEST 3: Voting - True Positive (DNS Failure)
    print("\nTEST 3: Voter APPROVES DNS Hypothesis")
    hypothesis_true = {
        "incident_id": "INC-005",
        "proposed_root_cause": "DNS service timeout",
        "target_devices": ["SRV_DNS_01"]
    }
    vote = voter.evaluate_hypothesis(hypothesis_true)
    print(json.dumps(vote, indent=2))
    assert vote["vote"] == "APPROVE", "Failed Test 3"

    # TEST 4: Voting - Abstain (Out of Domain)
    print("\nTEST 4: Voter ABSTAINS on Hardware Hypothesis when L4 is healthy")
    # First, feed healthy data so state is updated
    sensor.process_telemetry({"device_id": "SW_HOSTEL_01", "metrics": {"cpu_utilization_pct": 99.0}})
    
    hypothesis_hw = {
        "incident_id": "INC-006",
        "proposed_root_cause": "Hardware failure",
        "target_devices": ["SW_HOSTEL_01"]
    }
    vote = voter.evaluate_hypothesis(hypothesis_hw)
    print(json.dumps(vote, indent=2))
    assert vote["vote"] == "ABSTAIN", "Failed Test 4"

    # TEST 5: Voting - Conflict Resolution
    print("\nTEST 5: Voter REJECTS Congestion Hypothesis when L4 is broken")
    # Feed bad L4 data to state
    sensor.process_telemetry({
        "device_id": "SRV_DNS_01", 
        "metrics": {"dns_latency_ms": 500, "dhcp_pool_utilization_pct": 40.0}
    })
    hypothesis_congestion = {
        "incident_id": "INC-007",
        "proposed_root_cause": "Link congestion",
        "target_devices": ["SRV_DNS_01"]
    }
    vote = voter.evaluate_hypothesis(hypothesis_congestion)
    print(json.dumps(vote, indent=2))
    assert vote["vote"] == "REJECT", "Failed Test 5"
    assert vote["suggested_alternative"] is not None, "Failed to suggest alternative"

    print("\n=== ALL L4-L7 TESTS PASSED ===")

def test_l4_l7():
    run_tests()

if __name__ == "__main__":
    run_tests()
