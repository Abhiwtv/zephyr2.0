import os
import json
import asyncio
from agents.brain.reasoner import ReasoningEngine
from core.memory import shared_memory

def run_tests():
    reasoner = ReasoningEngine()
    incident_id = "INC-LLM-001"

    print("=== TEST 1: GEMINI REASONER (ROUND 1) ===\n")
    
    # Simulate alerts coming from the sensors
    active_alerts = [
        {
            "device_id": "SW_HOSTEL_01",
            "alert_category": "anomaly",
            "evidence": [
                {"metric": "cpu_utilization_pct", "value": 99.5, "interpretation": "Critical CPU exhaustion"},
                {"metric": "interface_errors", "value": 250, "interpretation": "High physical interface errors detected"}
            ]
        }
    ]

    # Fetch context (will be empty for Round 1)
    memory_context = shared_memory.get_reasoner_context(incident_id)
    
    print("Generating hypothesis via Reasoner...")
    hypothesis = reasoner.generate_hypothesis_sync(incident_id, active_alerts, memory_context)
    
    print("\n--- LLM GENERATED HYPOTHESIS BROADCAST ---")
    print(json.dumps(hypothesis, indent=2))
    
    assert hypothesis["proposed_root_cause"] != "", "Failed to generate a root cause string"
    assert "SW_HOSTEL_01" in hypothesis["target_devices"], "Failed to extract target devices"

    print("\n=== GEMINI REASONER TEST PASSED ===")

def test_reasoner():
    run_tests()

if __name__ == "__main__":
    run_tests()
