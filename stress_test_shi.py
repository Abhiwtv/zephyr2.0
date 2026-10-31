import asyncio
import json
import random
import os
from datetime import datetime, timezone

# Import our NetCoop architecture
from core.shared_state import global_state
from agents.brain.reasoner import ReasoningEngine
from agents.brain.iterator import AsyncConsensusIterator
from agents.voters.llm_voter import LLMDomainVoter
from agents.infrastructure.sensor import InfrastructureSensor
from agents.traffic.sensor import TrafficSensor
from agents.l4_l7.sensor import L4L7Sensor

# --- HARDCODED CAMPUS NETWORK FAULT SCENARIOS (IIT BHUBANESWAR) ---
SCENARIOS = {
    "HOSTEL_WIFI_EVENING_CONGESTION": {
        # Typical 9 PM hostel scenario: Everyone streaming/gaming. 
        # Bandwidth is saturated, DHCP pool is almost full, causing high jitter and buffer bloat.
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "device_id": "HOSTEL_MAHANADI_WLC_01",
        "metrics": {
            "cpu_utilization_pct": 65.0,
            "link_utilization_pct": 98.5,
            "packet_loss_pct": 2.5,
            "latency_ms": 250.0,
            "jitter_ms": 115.0,
            "queue_drops": 4500,
            "interface_errors": 0,
            "dns_latency_ms": 45.0,
            "dhcp_pool_utilization_pct": 96.0
        },
        "status": "Warning"
    },
    "LECTURE_HALL_BAD_ETHERNET_CABLE": {
        # Physical Layer 1 issue: A damaged Cat6 cable or bad crimp at a lecture hall podium.
        # Traffic is very low, but interface errors (FCS/CRC) and packet loss are high.
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "device_id": "LHC_ROOM_201_SW",
        "metrics": {
            "cpu_utilization_pct": 10.5,
            "link_utilization_pct": 5.2,
            "packet_loss_pct": 18.0,
            "latency_ms": 12.0,
            "jitter_ms": 4.0,
            "queue_drops": 0,
            "interface_errors": 12500,
            "dns_latency_ms": 8.0,
            "dhcp_pool_utilization_pct": 15.0
        },
        "status": "Critical"
    },
    "LIBRARY_DHCP_EXHAUSTION": {
        # L4/L7 Issue: Too many students with multiple devices (phones, laptops, tablets) 
        # have exhausted the /24 subnet IP pool. Hardware and traffic are perfectly fine.
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "device_id": "CENTRAL_LIBRARY_AP_GRP",
        "metrics": {
            "cpu_utilization_pct": 22.0,
            "link_utilization_pct": 35.0,
            "packet_loss_pct": 0.0,
            "latency_ms": 15.0,
            "jitter_ms": 5.0,
            "queue_drops": 0,
            "interface_errors": 0,
            "dns_latency_ms": 10.0,
            "dhcp_pool_utilization_pct": 100.0
        },
        "status": "Critical"
    },
    "CS_DEPT_ROUTING_LOOP_CPU_SPIKE": {
        # Control Plane Issue: A misconfigured OSPF route or STP failure is causing a broadcast storm.
        # The CPU hits 100% trying to process loops, dropping queues massively.
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "device_id": "CS_DEPT_CORE_RTR",
        "metrics": {
            "cpu_utilization_pct": 100.0,
            "link_utilization_pct": 65.0,
            "packet_loss_pct": 15.5,
            "latency_ms": 850.0,
            "jitter_ms": 300.0,
            "queue_drops": 25000,
            "interface_errors": 0,
            "dns_latency_ms": 120.0,
            "dhcp_pool_utilization_pct": 40.0
        },
        "status": "Critical"
    },
    "CAMPUS_CORE_FIBER_DEGRADATION": {
        # Optical Issue: A fiber link between the main academic block and a distant hostel is failing 
        # (e.g., bent fiber or failing SFP optic). Manifests as high packet loss and interface errors on an uplink.
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "device_id": "CAMPUS_BACKBONE_SW_01",
        "metrics": {
            "cpu_utilization_pct": 15.0,
            "link_utilization_pct": 45.0,
            "packet_loss_pct": 8.5,
            "latency_ms": 25.0,
            "jitter_ms": 12.0,
            "queue_drops": 0,
            "interface_errors": 5400,
            "dns_latency_ms": 15.0,
            "dhcp_pool_utilization_pct": 50.0
        },
        "status": "Warning"
    }
}

# Generate benign background noise to prove the sensors filter correctly
def generate_noise_payload():
    return {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "device_id": f"ADMIN_BLK_SW_{random.randint(1, 10)}",
        "metrics": {
            "cpu_utilization_pct": round(random.uniform(5, 25), 2),
            "link_utilization_pct": round(random.uniform(10, 40), 2),
            "packet_loss_pct": 0.0,
            "latency_ms": round(random.uniform(2, 10), 2),
            "jitter_ms": round(random.uniform(1, 3), 2),
            "queue_drops": 0,
            "interface_errors": 0,
            "dns_latency_ms": round(random.uniform(5, 12), 2),
            "dhcp_pool_utilization_pct": round(random.uniform(20, 45), 2)
        },
        "status": "Healthy"
    }

async def run_stress_test():
    print("=== INITIALIZING NETCOOP CAMPUS ISSUE RESOLVER TEST SUITE ===\n")
    
    # 1. Initialize strictly isolated agents
    infra_voter = LLMDomainVoter("infrastructure_agent", "Layer 1/2 hardware, CPU, and physical errors", ["cpu_utilization_pct", "interface_errors", "queue_drops"])
    traffic_voter = LLMDomainVoter("traffic_agent", "Bandwidth, congestion, latency, and packet loss", ["link_utilization_pct", "latency_ms", "packet_loss_pct", "jitter_ms"])
    l4_voter = LLMDomainVoter("l4_l7_agent", "Core network services like DHCP and DNS", ["dns_latency_ms", "dhcp_pool_utilization_pct"])

    infra_sensor = InfrastructureSensor()
    traffic_sensor = TrafficSensor()
    l4_sensor = L4L7Sensor()

    reasoner = ReasoningEngine()
    
    test_counter = 1
    
    # 2. Loop through each hardcoded scenario one by one
    for scenario_name, faulty_payload in SCENARIOS.items():
        print(f"\n=======================================================")
        print(f"[{test_counter}/{len(SCENARIOS)}] DIAGNOSING SCENARIO: {scenario_name}")
        print(f"=======================================================\n")
        
        iterator = AsyncConsensusIterator(voter_agents=[infra_voter, traffic_voter, l4_voter], reasoner=reasoner)
        
        noise_payload = generate_noise_payload()
        active_alerts = []
        
        print(f"--> Ingesting Faulty Telemetry from {faulty_payload['device_id']}...")
        print(f"--> Ingesting Benign Background Noise from {noise_payload['device_id']}...")
        global_state.update_state(faulty_payload["device_id"], faulty_payload["metrics"])
        global_state.update_state(noise_payload["device_id"], noise_payload["metrics"])
        # 3. Process both payloads through the deterministic sensors
        for payload in [faulty_payload, noise_payload]:
            for sensor in [infra_sensor, traffic_sensor, l4_sensor]:
                alert = sensor.process_telemetry(payload)
                # The sensors should automatically drop the noise_payload because it's healthy
                if alert.get("alert_category", "healthy") != "healthy":
                    active_alerts.append(alert)

        print(f"\n--> Sensors filtered noise and generated {len(active_alerts)} valid domain alerts.")
        print("--> STARTING ASYNC CONSENSUS LOOP (Brain + Domain Agents)...\n")
        
        incident_id = f"INC-{scenario_name}-{random.randint(1000,9999)}"
        
        # 4. Execute the consensus loop for this specific scenario
        final_report = await iterator.execute_voting_loop(incident_id, active_alerts)

        print(f"\n=== FINAL DIAGNOSTIC REPORT: {scenario_name} ===")
        print(json.dumps(final_report, indent=2))
        print(f"\n[Finished {scenario_name}. Moving to next in 3 seconds...]\n")
        
        test_counter += 1
        await asyncio.sleep(3) 

    print("=== ALL CAMPUS NETWORK DIAGNOSTICS COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    asyncio.run(run_stress_test())