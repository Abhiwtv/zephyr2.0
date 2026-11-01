import asyncio
import json
import random
import os
import sys
from datetime import timezone, datetime

# Ensure repository root is on sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Import our NetCoop architecture
from core.shared_state import global_state
from agents.brain.reasoner import ReasoningEngine
from agents.brain.iterator import AsyncConsensusIterator
from agents.voters.llm_voter import LLMDomainVoter
from agents.infrastructure.sensor import InfrastructureSensor
from agents.traffic.sensor import TrafficSensor
from agents.l4_l7.sensor import L4L7Sensor

# --- THE HACKATHON'S TELEMETRY GENERATOR ---
def generate_telemetry(fault_type="normal"):
    data = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "device_id": f"SW_CAMPUS_{random.randint(1, 10)}",
        "metrics": {}
    }

    if fault_type == "latency_spike": 
        data["metrics"] = {
            "cpu_utilization_pct": round(random.uniform(40, 70), 2),
            "link_utilization_pct": round(random.uniform(60, 85), 2),
            "packet_loss_pct": round(random.uniform(0.1, 1.5), 2),
            "latency_ms": round(random.uniform(150, 400), 2), 
            "jitter_ms": round(random.uniform(30, 80), 2),
            "queue_drops": random.randint(0, 50)
        }
        data["status"] = "Warning"
    elif fault_type == "hardware_failure":
        data["metrics"] = {
            "cpu_utilization_pct": 99.9,
            "link_utilization_pct": 100.0,
            "packet_loss_pct": round(random.uniform(15, 30), 2),
            "latency_ms": round(random.uniform(500, 1000), 2),
            "queue_drops": random.randint(5000, 15000),
            "interface_errors": random.randint(100, 500)
        }
        data["status"] = "Critical"
    else:
        data["metrics"] = {
            "cpu_utilization_pct": round(random.uniform(10, 35), 2),
            "link_utilization_pct": round(random.uniform(20, 50), 2),
            "packet_loss_pct": 0.0,
            "latency_ms": round(random.uniform(5, 20), 2),
            "jitter_ms": round(random.uniform(1, 5), 2),
            "queue_drops": 0
        }
        data["status"] = "Healthy"
    return data


async def run_stress_test():
    print("=== INITIALIZING NETCOOP AI STRESS TEST ===\n")
    
    # 1. Initialize strictly isolated agents
    infra_voter = LLMDomainVoter("infrastructure_agent", "Layer 1/2 hardware...", ["cpu_utilization_pct", "interface_errors", "queue_drops"])
    traffic_voter = LLMDomainVoter("traffic_agent", "Bandwidth and congestion...", ["link_utilization_pct", "latency_ms", "packet_loss_pct", "jitter_ms"])
    l4_voter = LLMDomainVoter("l4_l7_agent", "Core services...", ["dns_latency_ms", "dhcp_pool_utilization_pct"])

    infra_sensor = InfrastructureSensor()
    traffic_sensor = TrafficSensor()
    l4_sensor = L4L7Sensor()

    reasoner = ReasoningEngine()
    iterator = AsyncConsensusIterator(voter_agents=[infra_voter, traffic_voter, l4_voter], reasoner=reasoner)

    # 2. GENERATE CASCADING FAILURE + NOISE
    print("Generating telemetry payloads...")
    # Target A: The Cascade Failure
    payload_a = generate_telemetry("hardware_failure")
    payload_a["device_id"] = "CORE_SW_01" 
    
    # Target B: Pure Noise (Healthy switch elsewhere on campus to see if Brain gets confused)
    payload_b = generate_telemetry("normal")
    payload_b["device_id"] = "ACCESS_SW_09"

    # 3. Process through deterministic sensors
    active_alerts = []
    
    for payload in [payload_a, payload_b]:
        for sensor in [infra_sensor, traffic_sensor, l4_sensor]:
            alert = sensor.process_telemetry(payload)
            # The sensors should automatically drop payload_b because it's healthy
            if alert["alert_category"] != "healthy":
                active_alerts.append(alert)

    print(f"Sensors generated {len(active_alerts)} valid alerts (filtered out noise).")

    print("\n=== STARTING ASYNC DIAGNOSTIC LOOP ===")
    incident_id = "INC-STRESS-999"
    final_report = await iterator.execute_voting_loop(incident_id, active_alerts)

    print("\n=== FINAL DIAGNOSTIC REPORT ===")
    print(json.dumps(final_report, indent=2))

if __name__ == "__main__":
    asyncio.run(run_stress_test())
