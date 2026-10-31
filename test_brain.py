import json
from core.shared_state import global_state

from agents.infrastructure.sensor import InfrastructureSensor
from agents.infrastructure.voter import InfrastructureVoter
from agents.traffic.sensor import TrafficSensor
from agents.traffic.voter import TrafficVoter
from agents.l4_l7.sensor import L4L7Sensor
from agents.l4_l7.voter import L4L7Voter

from agents.brain.orchestrator import BrainAgent

def run_integration_test():
    print("=== RUNNING MULTI-ROUND CONSENSUS TEST ===\n")
    
    # 1. Initialize Edge Components
    infra_sensor = InfrastructureSensor()
    infra_voter = InfrastructureVoter()
    
    traffic_sensor = TrafficSensor()
    traffic_voter = TrafficVoter()
    
    l4_sensor = L4L7Sensor()
    l4_voter = L4L7Voter()

    # 2. Initialize Brain
    brain = BrainAgent(voter_agents=[infra_voter, traffic_voter, l4_voter])

    # ---------------------------------------------------------
    # The Trap Scenario: Looks like hardware (queue drops), is actually congestion.
    # ---------------------------------------------------------
    telemetry_payload = {
        "device_id": "SW_HOSTEL_05",
        "metrics": {
            # Traffic metrics (screaming congestion)
            "link_utilization_pct": 98.0,
            "latency_ms": 320.0,
            
            # Infra metrics (high drops, but zero interface errors - means it's a traffic jam, not a bad cable)
            "queue_drops": 1500, 
            "cpu_utilization_pct": 86.0,
            "interface_errors": 0, 
            
            # L4/L7 (healthy)
            "dns_latency_ms": 15.0,
            "dhcp_pool_utilization_pct": 45.0
        }
    }

    print("Step 1: Sensors ingest telemetry and update shared state...")
    active_alerts = []
    for sensor in [infra_sensor, traffic_sensor, l4_sensor]:
        alert = sensor.process_telemetry(telemetry_payload)
        if alert["alert_category"] != "healthy":
            active_alerts.append(alert)
            
    print(f"-> Generated {len(active_alerts)} alerts.")

    print("\nStep 2: Brain initiates voting loop...")
    final_report = brain.diagnose_network(active_alerts)
    
    print("\n=== FINAL DIAGNOSTIC REPORT ===")
    print(json.dumps(final_report, indent=2))
    
    # Assertions to prove the loop worked
    assert "limitations" in final_report, "Report missing limitations"
    assert any("Consensus reached" in x for x in final_report["limitations"]), "Failed to reach consensus"

if __name__ == "__main__":
    run_integration_test()