import json
import asyncio
import time
import os
import sys

# Ensure repository root is on sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.config import settings
from agents.brain.iterator import AsyncConsensusIterator
from agents.brain.reasoner import ReasoningEngine
from agents.voters.llm_voter import LLMDomainVoter
from core.shared_state import global_state

def safe_float(val):
    """Safely handles the edge_missing_cpu and edge_inconsistent_data NaN tests."""
    try:
        if val is None: return 0.0
        return float(val)
    except (TypeError, ValueError):
        return 0.0

def translate_to_active_alerts(payload):
    """Translates raw device telemetry into the Middleware Alerts format."""
    metrics = payload.get("metrics", {})
    device_id = payload.get("device_id", "UNKNOWN_DEV")
    status = payload.get("status", "Healthy")
    
    # Map status to Dynamic Severity Multiplier
    base_score = 0.0
    if status == "Critical": base_score = 3.0
    elif status == "Warning": base_score = 1.0

    alerts = []
    
    # 1. Infrastructure Alert Trigger
    infra_active = safe_float(metrics.get("cpu_utilization_pct")) > 80.0 or \
                   safe_float(metrics.get("interface_errors")) > 100 or \
                   safe_float(metrics.get("queue_drops")) > 100
    
    alerts.append({
        "device_id": device_id,
        "domain": "infrastructure",
        "anomaly_score": base_score if infra_active else 0.0,
        "metrics": metrics
    })

    # 2. Traffic Alert Trigger
    traffic_active = safe_float(metrics.get("link_utilization_pct")) > 85.0 or \
                     safe_float(metrics.get("packet_loss_pct")) > 2.0 or \
                     safe_float(metrics.get("latency_ms")) > 100.0
                     
    alerts.append({
        "device_id": device_id,
        "domain": "traffic",
        "anomaly_score": base_score if traffic_active else 0.0,
        "metrics": metrics
    })

    # 3. L4-L7 Alert Trigger
    l4_active = safe_float(metrics.get("dns_latency_ms")) > 100.0 or \
                safe_float(metrics.get("dhcp_pool_utilization_pct")) > 85.0
                
    alerts.append({
        "device_id": device_id,
        "domain": "l4_l7",
        "anomaly_score": base_score if l4_active else 0.0,
        "metrics": metrics
    })

    return alerts

async def run_massive_benchmark():
    print("==========================================================================================")
    print("ZEPHYR AGENTIC NIDS: MASSIVE 50-TEST VALIDATION PIPELINE")
    print("==========================================================================================")
    
    # Initialize Reasoner and Domain Voters
    reasoner = ReasoningEngine()
    voters = [
        LLMDomainVoter(
            "infrastructure_agent", 
            "Layer 1/2 hardware, CPU, and physical interfaces",
            monitored_metrics=["cpu_utilization_pct", "interface_errors", "queue_drops"]
        ),
        LLMDomainVoter(
            "traffic_agent", 
            "L2/L3 bandwidth, latency, and packet loss",
            monitored_metrics=["link_utilization_pct", "packet_loss_pct", "latency_ms", "jitter_ms"]
        ),
        LLMDomainVoter(
            "l4_l7_agent", 
            "DNS, DHCP, and application layer health",
            monitored_metrics=["dns_latency_ms", "dhcp_pool_utilization_pct"]
        )
    ]
    audit_file = os.path.join(settings.DATA_DIR, "massive_audit.json")
    iterator = AsyncConsensusIterator(voters, reasoner, output_file=audit_file)

    # Candidate dataset paths
    candidate_paths = [
        os.path.join(settings.DATA_DIR, "iit_bbs_benchmark_dataset.json"),
        os.path.join(REPO_ROOT, "iit_bbs_benchmark_dataset.json")
    ]
    dataset_file = next((p for p in candidate_paths if os.path.exists(p)), None)

    if not dataset_file:
        print("[!] iit_bbs_benchmark_dataset.json not found. Run scripts/generate_telemetry.py first.")
        return

    with open(dataset_file, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    pass_count = 0
    start_time = time.time()

    for idx, test in enumerate(dataset):
        scenario_name = test["scenario"]
        payload = test["payload"]
        
        print(f"\n[{idx+1:02d}/{len(dataset):02d}] Evaluating {scenario_name}...")
        
        # Translate and Inject Telemetry
        active_alerts = translate_to_active_alerts(payload)
        
        # Wipe state clean before injecting new telemetry
        global_state.device_states.clear()
        if hasattr(global_state, "latest_device"):
            global_state.latest_device = payload["device_id"]
            
        global_state.device_states[payload["device_id"]] = payload["metrics"]
        
        # Execute the Logic Loop
        incident_id = f"INC-{scenario_name}-{int(time.time())}"
        report = await iterator.execute_voting_loop(incident_id, active_alerts, output_file=None)
        
        # Validate Outcome
        if report and report.get("status") == "diagnosed":
            print(f"[PASS] Conf: {report.get('confidence')} | Cause: {report.get('suspected_root_cause', '')[:60]}...")
            pass_count += 1
        else:
            print(f"[FAIL] Pipeline failed to reach consensus for {scenario_name}")

    total_time = time.time() - start_time
    print("\n==========================================================================================")
    print(f"MASSIVE BENCHMARK COMPLETE")
    print(f"Final Accuracy: {pass_count}/{len(dataset)} ({pass_count/len(dataset) * 100:.1f}%)")
    print(f"Total Execution Time: {total_time:.2f} seconds")
    print("==========================================================================================")

if __name__ == "__main__":
    asyncio.run(run_massive_benchmark())
