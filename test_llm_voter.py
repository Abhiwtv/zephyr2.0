import json
from core.shared_state import global_state
from core.memory import shared_memory
from agents.voters.llm_voter import LLMDomainVoter

def run_tests():
    incident_id = "INC-VOTE-001"
    
    print("=== TEST 1: LLM VOTER (INFRASTRUCTURE) ===\n")
    
    # 1. Initialize the generic LLM Voter as the Infra agent
    infra_voter = LLMDomainVoter(
        agent_id="infrastructure_agent",
        domain_expertise="Layer 1/2 physical hardware, cpu_utilization_pct, interface_errors, and queue_drops."
    )
    
    # 2. Seed the local state with healthy hardware data
    global_state.update_state("SW_HOSTEL_01", {
        "cpu_utilization_pct": 25.0, 
        "interface_errors": 0,
        "queue_drops": 0
    })
    
    # 3. Brain proposes a WRONG hypothesis (hardware failure)
    wrong_hypothesis = {
        "incident_id": incident_id,
        "proposed_root_cause": "Hardware failure on SW_HOSTEL_01 causing packet drops",
        "target_devices": ["SW_HOSTEL_01"]
    }
    
    print("Agent analyzing hypothesis via Gemini...")
    vote_result = infra_voter.evaluate_hypothesis(wrong_hypothesis)
    
    print("\n--- LLM GENERATED VOTE ---")
    print(json.dumps(vote_result, indent=2))
    
    # The LLM should recognize healthy data contradicts the hypothesis
    assert vote_result["vote"] == "REJECT", "LLM failed to reject a false hypothesis"
    assert vote_result["suggested_alternative"] is not None, "LLM failed to suggest an alternative"

    print("\n=== GEMINI VOTER TEST PASSED ===")

if __name__ == "__main__":
    run_tests()