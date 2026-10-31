from core.memory import shared_memory

def run_tests():
    incident_id = "INC-TEST-99"
    
    print("=== TEST 1: EMPTY MEMORY ===")
    print("Reasoner Context:", shared_memory.get_reasoner_context(incident_id))
    
    # Simulate Round 1
    shared_memory.record_hypothesis(incident_id, 1, "Hardware failure on uplink")
    shared_memory.record_vote(incident_id, 1, "infrastructure_agent", "APPROVE", "High interface errors detected.")
    shared_memory.record_vote(incident_id, 1, "traffic_agent", "REJECT", "No packet loss detected.", "Look into L4-L7 services", pivot_hint="Pivot to Layer 1 hardware or L4-L7 services.")
    
    print("\n=== TEST 2: REASONER CONTEXT AFTER ROUND 1 ===")
    ctx = shared_memory.get_reasoner_context(incident_id)
    print(ctx)
    assert "CRITICAL PIVOT HINT" in ctx, "Failed to include CRITICAL PIVOT HINT in reasoner context"
    
    print("=== TEST 3: VOTER CONTEXT AFTER ROUND 1 ===")
    print(shared_memory.get_voter_context(incident_id, "traffic_agent"))
    
    # Simulate Round 2
    shared_memory.record_hypothesis(incident_id, 2, "L4-L7 service failure")
    shared_memory.record_vote(incident_id, 2, "traffic_agent", "ABSTAIN", "Out of my domain.")
    
    print("=== TEST 4: VOTER CONTEXT AFTER ROUND 2 ===")
    print(shared_memory.get_voter_context(incident_id, "traffic_agent"))
    
    shared_memory.clear_incident(incident_id)

def test_memory():
    run_tests()

if __name__ == "__main__":
    run_tests()
