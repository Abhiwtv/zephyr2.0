import os
import json
import shutil
import tempfile
from core.memory import IncidentMemory
from core.output_store import save_output_json, load_output_json

def run_persistence_tests():
    print("=== RUNNING PERSISTENCE & OUTPUT JSON VALIDATION TESTS ===\n")
    
    test_dir = os.path.join(tempfile.gettempdir(), "test_persistence_temp")
    os.makedirs(test_dir, exist_ok=True)
    test_memory_file = os.path.join(test_dir, "incident_memory_test.json")
    test_output_file = os.path.join(test_dir, "output.json")

    try:
        # -------------------------------------------------------------
        # TEST 1: Incident Memory Persistence Across Process Restarts
        # -------------------------------------------------------------
        print("TEST 1: Record incident rounds & verify file persistence...")
        mem1 = IncidentMemory(persistence_file=test_memory_file)
        incident_id = "INC-PERSIST-101"

        mem1.record_hypothesis(incident_id, 1, "Fiber attenuation causing high BER")
        mem1.record_vote(
            incident_id=incident_id,
            round_num=1,
            agent_id="infrastructure_agent",
            vote="APPROVE",
            reason="High physical interface CRC errors verified."
        )
        mem1.record_vote(
            incident_id=incident_id,
            round_num=1,
            agent_id="traffic_agent",
            vote="APPROVE",
            reason="Elevated packet loss corroborates Layer 1 faults."
        )

        assert os.path.exists(test_memory_file), "Memory file was not written to disk!"
        print("-> File successfully created on disk.")

        # Simulate total process restart by creating a new IncidentMemory instance
        print("\nTEST 2: Simulate process restart and reload persistent memory...")
        mem2 = IncidentMemory(persistence_file=test_memory_file)
        inc_data = mem2.get_incident(incident_id)

        assert inc_data is not None, f"Failed to retrieve {incident_id} after reload"
        assert inc_data["rounds"][1]["hypothesis"] == "Fiber attenuation causing high BER"
        assert inc_data["rounds"][1]["votes"]["infrastructure_agent"]["vote"] == "APPROVE"
        print("-> All rounds, hypotheses, and agent votes successfully recovered from disk!")

        # -------------------------------------------------------------
        # TEST 3: Record Final Diagnostic Report in Persistent Memory
        # -------------------------------------------------------------
        print("\nTEST 3: Record and archive final diagnostic report...")
        mock_output_report = {
            "incident_id": incident_id,
            "status": "diagnosed",
            "suspected_root_cause": "Fiber attenuation causing high BER",
            "confidence": 0.95,
            "affected_devices": ["CORE_SW_01"],
            "supporting_evidence": [
                {
                    "metric": "interface_errors",
                    "value": 12500,
                    "interpretation": "Critical physical interface errors"
                },
                {
                    "metric": "packet_loss_pct",
                    "value": 18.0,
                    "interpretation": "Significant packet loss"
                }
            ],
            "alternative_causes": [],
            "recommended_actions": [
                "Inspect optical patch cable",
                "Clean transceiver bulkhead"
            ],
            "evidence_sources": [
                "infrastructure_agent",
                "traffic_agent"
            ],
            "limitations": [
                "Consensus reached in round 1"
            ]
        }

        mem2.record_final_report(incident_id, mock_output_report)
        mem2.clear_incident(incident_id, archive=True)

        # Reload once more to ensure archived incident + final report are saved
        mem3 = IncidentMemory(persistence_file=test_memory_file)
        archived_inc = mem3.get_incident(incident_id)
        assert archived_inc["status"] == "diagnosed"
        assert archived_inc["final_report"]["confidence"] == 0.95
        print("-> Final report successfully persisted in incident memory archive!")

        # -------------------------------------------------------------
        # TEST 4: Save Generated Output as JSON in Exact OUTPUT Format
        # -------------------------------------------------------------
        print("\nTEST 4: Save output report directly to JSON file in exact OUTPUT format...")
        saved_path = save_output_json(mock_output_report, filepath=test_output_file)
        assert os.path.exists(saved_path), "output.json was not created!"

        # Read back raw JSON content and verify format
        with open(test_output_file, "r", encoding="utf-8") as f:
            raw_loaded = json.load(f)

        # Strict equality check - must match the exact OUTPUT format without modification
        assert raw_loaded == mock_output_report, "Saved output JSON does not match exact OUTPUT format!"
        
        # Verify required output fields are present
        required_keys = [
            "incident_id", "status", "suspected_root_cause", "confidence",
            "affected_devices", "supporting_evidence", "alternative_causes",
            "recommended_actions", "evidence_sources", "limitations"
        ]
        for key in required_keys:
            assert key in raw_loaded, f"Missing key in output JSON: {key}"

        print("-> Single output JSON matches the EXACT format as generated as OUTPUT!")

        # -------------------------------------------------------------
        # TEST 5: Batch / Multiple Outputs in Exact Format
        # -------------------------------------------------------------
        print("\nTEST 5: Verify multiple outputs saved as JSON in exact OUTPUT format...")
        mock_output_report_2 = dict(mock_output_report)
        mock_output_report_2["incident_id"] = "INC-PERSIST-102"
        mock_output_report_2["suspected_root_cause"] = "DHCP Pool Exhaustion"
        mock_output_report_2["affected_devices"] = ["DHCP_SRV_01"]

        batch_reports = [mock_output_report, mock_output_report_2]
        test_batch_file = os.path.join(test_dir, "batch_output.json")
        save_output_json(batch_reports, filepath=test_batch_file)

        with open(test_batch_file, "r", encoding="utf-8") as f:
            batch_loaded = json.load(f)

        assert isinstance(batch_loaded, list), "Batch output should be a JSON list"
        assert len(batch_loaded) == 2, "Batch output count mismatch"
        assert batch_loaded[0] == mock_output_report, "First item format mismatch"
        assert batch_loaded[1] == mock_output_report_2, "Second item format mismatch"
        print("-> Batch outputs correctly saved with every item in the exact OUTPUT format!")

        print("\n=== ALL PERSISTENCE TESTS PASSED SUCCESSFULLY! ===")

    finally:
        # Cleanup temp directory
        if os.path.exists(test_dir):
            try:
                shutil.rmtree(test_dir)
            except Exception:
                pass

def test_persistence():
    run_persistence_tests()

if __name__ == "__main__":
    run_persistence_tests()
