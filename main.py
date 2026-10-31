import asyncio
import json
import os
from core.shared_state import global_state
from core.memory import shared_memory

from agents.brain.reasoner import ReasoningEngine
from agents.brain.iterator import AsyncConsensusIterator
from agents.voters.llm_voter import LLMDomainVoter

async def run_full_system():
    print("=== INITIALIZING NETCOOP AI MULTI-AGENT SYSTEM ===\n")
    
    # 1. Initialize the 3 LLM Voters with distinct, greedy personas
    infra_voter = LLMDomainVoter(
        agent_id="infrastructure_agent",
        domain_expertise="Layer 1/2 physical hardware, cpu_utilization_pct, interface_errors, and queue_drops.",
        monitored_metrics=["cpu_utilization_pct", "interface_errors", "queue_drops"]
    )
    
    traffic_voter = LLMDomainVoter(
        agent_id="traffic_agent",
        domain_expertise="Bandwidth, link_utilization_pct, latency_ms, packet_loss_pct, and network congestion.",
        monitored_metrics=["link_utilization_pct", "latency_ms", "packet_loss_pct"]
    )
    
    l4_voter = LLMDomainVoter(
        agent_id="l4_l7_agent",
        domain_expertise="Core services, dns_latency_ms, and dhcp_pool_utilization_pct.",
        monitored_metrics=["dns_latency_ms", "dhcp_pool_utilization_pct"]
    )

    # 2. Initialize Brain Components
    reasoner = ReasoningEngine()
    iterator = AsyncConsensusIterator(
        voter_agents=[infra_voter, traffic_voter, l4_voter], 
        reasoner=reasoner
    )

    # 3. Inject Test Telemetry (The Trap Scenario: Severe Congestion)
    target_device = "SW_HOSTEL_05"
    telemetry_payload = {
        "device_id": target_device,
        "metrics": {
            "link_utilization_pct": 99.0,
            "latency_ms": 400.0,
            "queue_drops": 5000, 
            "cpu_utilization_pct": 86.0,
            "interface_errors": 0,  # Zero errors = healthy cables, proving it's congestion, not hardware
            "dns_latency_ms": 12.0,
            "dhcp_pool_utilization_pct": 45.0
        }
    }

    # Update shared state (simulating what the Sensor Processors would do)
    global_state.update_state(target_device, telemetry_payload["metrics"])

    # Simulate the initial trigger alert
    initial_alerts = [{
        "device_id": target_device,
        "alert_category": "anomaly",
        "evidence": [
            {"metric": "link_utilization_pct", "value": 99.0, "interpretation": "Severe link saturation"},
            {"metric": "queue_drops", "value": 5000, "interpretation": "Elevated queue drops"}
        ],
        "data_errors": []
    }]

    print("=== STARTING DIAGNOSTIC LOOP ===\n")
    incident_id = "INC-HACKATHON-FINAL"
    
    # Execute the async loop
    final_report = await iterator.execute_voting_loop(incident_id, initial_alerts)

    print("\n=== FINAL DIAGNOSTIC REPORT ===")
    print(json.dumps(final_report, indent=2))

if __name__ == "__main__":
    # Ensure API key is present
        asyncio.run(run_full_system())