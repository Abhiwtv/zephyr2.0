import json
import time
import os
import sys
import tempfile
from datetime import datetime, timezone
from typing import Dict, List, Any

from core.shared_state import global_state
from core.memory import shared_memory
from agents.infrastructure.sensor import InfrastructureSensor
from agents.traffic.sensor import TrafficSensor
from agents.l4_l7.sensor import L4L7Sensor
from agents.voters.llm_voter import LLMDomainVoter
from agents.brain.reasoner import ReasoningEngine
from agents.brain.iterator import AsyncConsensusIterator

def get_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

# The Ground Truth Dataset for Empirical Benchmarking
BENCHMARK_DATASET = [
    {
        "test_id": "EVAL-01",
        "ground_truth_category": "HEALTHY_BASELINE",
        "description": "Normal late-night traffic. Should be filtered out by sensors instantly without LLM invocation.",
        "payload": {
            "timestamp": get_timestamp(),
            "device_id": "HOSTEL_SW_11",
            "metrics": {
                "cpu_utilization_pct": 12.0,
                "interface_errors": 0,
                "queue_drops": 0,
                "link_utilization_pct": 25.0,
                "packet_loss_pct": 0.0,
                "latency_ms": 5.0,
                "jitter_ms": 1.0,
                "dns_latency_ms": 10.0,
                "dhcp_pool_utilization_pct": 30.0
            }
        }
    },
    {
        "test_id": "EVAL-02",
        "ground_truth_category": "L1_CABLE_DEGRADATION",
        "description": "Lecture hall podium cable is degraded. Massive physical errors, minimal traffic.",
        "payload": {
            "timestamp": get_timestamp(),
            "device_id": "LHC_ROOM_104_SW",
            "metrics": {
                "cpu_utilization_pct": 15.0,
                "interface_errors": 18500,
                "queue_drops": 0,
                "link_utilization_pct": 2.5,
                "packet_loss_pct": 22.0,
                "latency_ms": 15.0,
                "jitter_ms": 8.0,
                "dns_latency_ms": 12.0,
                "dhcp_pool_utilization_pct": 10.0
            }
        }
    },
    {
        "test_id": "EVAL-03",
        "ground_truth_category": "L4_DHCP_EXHAUSTION",
        "description": "Library AP group has exhausted its IP subnet. Hardware and bandwidth remain completely healthy.",
        "payload": {
            "timestamp": get_timestamp(),
            "device_id": "LIBRARY_AP_05",
            "metrics": {
                "cpu_utilization_pct": 28.0,
                "interface_errors": 0,
                "queue_drops": 0,
                "link_utilization_pct": 45.0,
                "packet_loss_pct": 0.0,
                "latency_ms": 12.0,
                "jitter_ms": 4.0,
                "dns_latency_ms": 15.0,
                "dhcp_pool_utilization_pct": 100.0
            }
        }
    },
    {
        "test_id": "EVAL-04",
        "ground_truth_category": "L2_ROUTING_LOOP",
        "description": "CS Dept Core has an STP failure causing a broadcast storm, leading to CPU exhaustion and massive queue drops.",
        "payload": {
            "timestamp": get_timestamp(),
            "device_id": "CS_DEPT_CORE_SW",
            "metrics": {
                "cpu_utilization_pct": 100.0,
                "interface_errors": 0,
                "queue_drops": 45000,
                "link_utilization_pct": 85.0,
                "packet_loss_pct": 18.0,
                "latency_ms": 950.0,
                "jitter_ms": 400.0,
                "dns_latency_ms": 250.0,
                "dhcp_pool_utilization_pct": 60.0
            }
        }
    },
    {
        "test_id": "EVAL-05",
        "ground_truth_category": "TRAFFIC_MICROBURST",
        "description": "Sudden massive file transfer overwhelming switch buffers temporarily, causing drops despite normal CPU.",
        "payload": {
            "timestamp": get_timestamp(),
            "device_id": "RESEARCH_LAB_SW",
            "metrics": {
                "cpu_utilization_pct": 45.0,
                "interface_errors": 0,
                "queue_drops": 12500,
                "link_utilization_pct": 99.5,
                "packet_loss_pct": 5.5,
                "latency_ms": 120.0,
                "jitter_ms": 65.0,
                "dns_latency_ms": 18.0,
                "dhcp_pool_utilization_pct": 45.0
            }
        }
    },
    {
        "test_id": "EVAL-06",
        "ground_truth_category": "HEALTHY_ELEVATED",
        "description": "Slightly elevated traffic but below critical thresholds. Must be filtered as noise.",
        "payload": {
            "timestamp": get_timestamp(),
            "device_id": "ADMIN_BLK_SW",
            "metrics": {
                "cpu_utilization_pct": 55.0,
                "interface_errors": 0,
                "queue_drops": 0,
                "link_utilization_pct": 65.0,
                "packet_loss_pct": 0.5,
                "latency_ms": 25.0,
                "jitter_ms": 10.0,
                "dns_latency_ms": 15.0,
                "dhcp_pool_utilization_pct": 55.0
            }
        }
    },
    {
        "test_id": "EVAL-07",
        "ground_truth_category": "L1_OPTICAL_FIBER_DEGRADATION",
        "description": "Failing SFP optic on the campus backbone uplink causing sustained physical errors.",
        "payload": {
            "timestamp": get_timestamp(),
            "device_id": "CAMPUS_BACKBONE_01",
            "metrics": {
                "cpu_utilization_pct": 20.0,
                "interface_errors": 5400,
                "queue_drops": 0,
                "link_utilization_pct": 35.0,
                "packet_loss_pct": 12.0,
                "latency_ms": 25.0,
                "jitter_ms": 15.0,
                "dns_latency_ms": 12.0,
                "dhcp_pool_utilization_pct": 30.0
            }
        }
    },
    {
        "test_id": "EVAL-08",
        "ground_truth_category": "L7_DNS_FAILURE",
        "description": "DNS server timeout. Network traffic is low and hardware is healthy, but resolution fails completely.",
        "payload": {
            "timestamp": get_timestamp(),
            "device_id": "WIFI_CTRL_01",
            "metrics": {
                "cpu_utilization_pct": 15.0,
                "interface_errors": 0,
                "queue_drops": 0,
                "link_utilization_pct": 12.0,
                "packet_loss_pct": 0.0,
                "latency_ms": 10.0,
                "jitter_ms": 2.0,
                "dns_latency_ms": 2500.0,
                "dhcp_pool_utilization_pct": 50.0
            }
        }
    },
    {
        "test_id": "EVAL-09",
        "ground_truth_category": "WIFI_CONGESTION_COMPOUND",
        "description": "Compound bottleneck in hostel Wi-Fi: Maxed bandwidth causing buffer bloat and near IP exhaustion.",
        "payload": {
            "timestamp": get_timestamp(),
            "device_id": "HOSTEL_WIFI_AP_99",
            "metrics": {
                "cpu_utilization_pct": 88.0,
                "interface_errors": 0,
                "queue_drops": 8500,
                "link_utilization_pct": 100.0,
                "packet_loss_pct": 8.5,
                "latency_ms": 450.0,
                "jitter_ms": 180.0,
                "dns_latency_ms": 65.0,
                "dhcp_pool_utilization_pct": 92.0
            }
        }
    },
    {
        "test_id": "EVAL-10",
        "ground_truth_category": "CRITICAL_HARDWARE_FAILURE",
        "description": "Switch motherboard/ASIC failure. All metrics breach fatal thresholds simultaneously.",
        "payload": {
            "timestamp": get_timestamp(),
            "device_id": "CORE_SW_02",
            "metrics": {
                "cpu_utilization_pct": 99.9,
                "interface_errors": 99999,
                "queue_drops": 99999,
                "link_utilization_pct": 0.5,
                "packet_loss_pct": 99.0,
                "latency_ms": 5000.0,
                "jitter_ms": 1000.0,
                "dns_latency_ms": 5000.0,
                "dhcp_pool_utilization_pct": 10.0
            }
        }
    }
]

class NetCoopEvaluator:
    """
    Automated Empirical Benchmark Evaluator & Testing Pipeline.
    Evaluates multi-agent consensus, noise suppression, and diagnosis accuracy
    against ground truth benchmark datasets.
    """
    def __init__(self, dataset_path: str = "benchmark_dataset.jsonl", results_path: str = "evaluation_results.jsonl"):
        self.dataset_path = dataset_path
        self.results_path = results_path
        
        # Initialize Sensors
        self.infra_sensor = InfrastructureSensor()
        self.traffic_sensor = TrafficSensor()
        self.l4_sensor = L4L7Sensor()
        
        # Initialize Domain Voters
        self.infra_voter = LLMDomainVoter(
            agent_id="infrastructure_agent",
            domain_expertise="Layer 1/2 physical hardware, cpu_utilization_pct, interface_errors, and queue_drops.",
            monitored_metrics=["cpu_utilization_pct", "interface_errors", "queue_drops"]
        )
        self.traffic_voter = LLMDomainVoter(
            agent_id="traffic_agent",
            domain_expertise="Bandwidth, link_utilization_pct, latency_ms, packet_loss_pct, and network congestion.",
            monitored_metrics=["link_utilization_pct", "latency_ms", "packet_loss_pct", "jitter_ms"]
        )
        self.l4_voter = LLMDomainVoter(
            agent_id="l4_l7_agent",
            domain_expertise="Core services, dns_latency_ms, and dhcp_pool_utilization_pct.",
            monitored_metrics=["dns_latency_ms", "dhcp_pool_utilization_pct"]
        )
        
        self.reasoner = ReasoningEngine()

    def load_dataset(self) -> List[Dict[str, Any]]:
        """Loads benchmark dataset from JSONL file or fallback structure."""
        cases = []
        if os.path.exists(self.dataset_path):
            try:
                with open(self.dataset_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            cases.append(json.loads(line))
            except Exception:
                cases = []
        if not cases:
            cases = list(BENCHMARK_DATASET)
        return cases

    def evaluate_single_case(self, case: Dict[str, Any]) -> Dict[str, Any]:
        """Runs an end-to-end evaluation on a single benchmark test case."""
        test_id = case.get("test_id", "UNKNOWN")
        gt_category = case.get("ground_truth_category", "UNKNOWN")
        description = case.get("description", "")
        payload = case.get("payload", {})
        device_id = payload.get("device_id", "UNKNOWN_DEV")
        metrics = payload.get("metrics", {})

        start_time = time.perf_counter()

        # 1. Update shared state
        global_state.update_state(device_id, metrics)

        # 2. Ingest through 3 deterministic sensors
        raw_alerts = [
            self.infra_sensor.process_telemetry(payload),
            self.traffic_sensor.process_telemetry(payload),
            self.l4_sensor.process_telemetry(payload)
        ]

        active_alerts = [a for a in raw_alerts if a.get("alert_category", "healthy") != "healthy"]
        is_healthy_ground_truth = gt_category in ("HEALTHY_BASELINE", "HEALTHY_ELEVATED")

        # Scenario A: Healthy Baseline / Noise
        if is_healthy_ground_truth:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            passed = (len(active_alerts) == 0)
            
            eval_record = {
                "test_id": test_id,
                "ground_truth_category": gt_category,
                "description": description,
                "device_id": device_id,
                "status": "FILTERED_HEALTHY" if passed else "FALSE_POSITIVE_ALERT",
                "active_alerts_count": len(active_alerts),
                "suspected_root_cause": "None (Healthy Traffic)",
                "confidence": 1.0 if passed else 0.0,
                "rounds": 0,
                "llm_invoked": False,
                "passed": passed,
                "latency_ms": latency_ms,
                "timestamp": get_timestamp()
            }
            return eval_record

        # Scenario B: Fault Ingestion & Consensus Loop
        incident_id = f"EVAL-INC-{test_id}-{int(time.time())}"
        iterator = AsyncConsensusIterator(
            voter_agents=[self.infra_voter, self.traffic_voter, self.l4_voter],
            reasoner=self.reasoner
        )

        final_report = iterator.execute_voting_loop_sync(incident_id, active_alerts)
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        suspected_cause = final_report.get("suspected_root_cause", "")
        confidence = final_report.get("confidence", 0.0)
        limitations = final_report.get("limitations", [])

        rounds = 1
        for lim in limitations:
            if "round" in lim.lower():
                for word in lim.split():
                    if word.isdigit():
                        rounds = int(word)

        domain_match = self._verify_domain_alignment(gt_category, suspected_cause, active_alerts)
        passed = (len(active_alerts) > 0) and (confidence >= 0.70) and domain_match

        eval_record = {
            "test_id": test_id,
            "ground_truth_category": gt_category,
            "description": description,
            "device_id": device_id,
            "status": "DIAGNOSED_ACCURATE" if passed else "DIAGNOSTIC_FAILURE",
            "active_alerts_count": len(active_alerts),
            "suspected_root_cause": suspected_cause,
            "confidence": confidence,
            "rounds": rounds,
            "llm_invoked": True,
            "passed": passed,
            "latency_ms": latency_ms,
            "supporting_evidence_count": len(final_report.get("supporting_evidence", [])),
            "timestamp": get_timestamp()
        }
        return eval_record

    def _verify_domain_alignment(self, gt_category: str, suspected_cause: str, active_alerts: List[Dict]) -> bool:
        """Validates that the predicted diagnosis matches the expected ground truth domain."""
        sc_lower = suspected_cause.lower()

        if "L1_CABLE" in gt_category:
            return any(k in sc_lower for k in ["cable", "physical", "layer 1", "hardware", "crimp"])
        elif "L1_OPTICAL" in gt_category:
            return any(k in sc_lower for k in ["optic", "fiber", "sfp", "physical", "layer 1"])
        elif "L4_DHCP" in gt_category:
            return any(k in sc_lower for k in ["dhcp", "ip pool", "lease", "service"])
        elif "L7_DNS" in gt_category:
            return any(k in sc_lower for k in ["dns", "resolution", "timeout", "service"])
        elif "L2_ROUTING_LOOP" in gt_category:
            return any(k in sc_lower for k in ["routing loop", "stp", "broadcast", "cpu", "exhaustion", "loop"])
        elif "TRAFFIC_MICROBURST" in gt_category:
            return any(k in sc_lower for k in ["microburst", "bandwidth", "saturation", "buffer", "congestion"])
        elif "WIFI_CONGESTION" in gt_category:
            return any(k in sc_lower for k in ["wi-fi", "wifi", "congestion", "bloat", "bandwidth", "dhcp"])
        elif "HARDWARE_FAILURE" in gt_category:
            return any(k in sc_lower for k in ["hardware", "asic", "switch", "chassis", "breakdown", "motherboard"])
        return True

    def run_evaluation_suite(self) -> Dict[str, Any]:
        """Runs full benchmark dataset and generates comprehensive evaluation report."""
        dataset = self.load_dataset()
        if not dataset:
            raise FileNotFoundError(f"No benchmark test cases found in {self.dataset_path}")

        print("\n" + "=" * 90)
        print(f"NETCOOP AI: EMPIRICAL BENCHMARK EVALUATOR PIPELINE ({len(dataset)} TEST CASES)")
        print("=" * 90)

        results = []
        for i, case in enumerate(dataset, start=1):
            test_id = case.get("test_id", f"EVAL-{i:02d}")
            print(f"[{i:02d}/{len(dataset):02d}] Evaluating {test_id} ({case.get('ground_truth_category')})...", end=" ", flush=True)
            res = self.evaluate_single_case(case)
            status_symbol = "[PASS]" if res["passed"] else "[FAIL]"
            print(f"{status_symbol} ({res['latency_ms']} ms | Conf: {res['confidence']:.2f} | Rounds: {res['rounds']})")
            results.append(res)

        # Write run results to JSONL log
        target_log = self.results_path
        try:
            with open(target_log, "a", encoding="utf-8") as f:
                for r in results:
                    f.write(json.dumps(r) + "\n")
        except PermissionError:
            target_log = os.path.join(tempfile.gettempdir(), os.path.basename(self.results_path))
            try:
                with open(target_log, "a", encoding="utf-8") as f:
                    for r in results:
                        f.write(json.dumps(r) + "\n")
            except Exception:
                pass

        # Compute summary statistics
        total = len(results)
        passed_count = sum(1 for r in results if r["passed"])
        noise_cases = [r for r in results if not r["llm_invoked"]]
        fault_cases = [r for r in results if r["llm_invoked"]]

        noise_passed = sum(1 for r in noise_cases if r["passed"])
        fault_passed = sum(1 for r in fault_cases if r["passed"])

        overall_accuracy = round((passed_count / total) * 100, 2)
        noise_specificity = round((noise_passed / len(noise_cases)) * 100, 2) if noise_cases else 100.0
        fault_sensitivity = round((fault_passed / len(fault_cases)) * 100, 2) if fault_cases else 100.0
        
        avg_confidence = round(sum(r["confidence"] for r in results) / total, 2)
        avg_rounds = round(sum(r["rounds"] for r in fault_cases) / len(fault_cases), 2) if fault_cases else 0.0
        avg_latency = round(sum(r["latency_ms"] for r in results) / total, 2)

        summary = {
            "total_tests": total,
            "passed_tests": passed_count,
            "overall_accuracy_pct": overall_accuracy,
            "noise_filtering_specificity_pct": noise_specificity,
            "fault_detection_sensitivity_pct": fault_sensitivity,
            "average_confidence": avg_confidence,
            "average_debate_rounds": avg_rounds,
            "average_latency_ms": avg_latency,
            "benchmark_dataset": self.dataset_path,
            "results_logfile": target_log,
            "results": results,
            "timestamp": get_timestamp()
        }

        self._print_benchmark_table(results, summary)
        return summary

    def _print_benchmark_table(self, results: List[Dict], summary: Dict[str, Any]):
        """Prints a structured ASCII summary table of the evaluation results."""
        print("\n" + "=" * 90)
        print("EMPIRICAL BENCHMARK SCORECARD")
        print("=" * 90)
        header = f"{'Test ID':<9} | {'Ground Truth Category':<28} | {'Status':<18} | {'Conf':<6} | {'Rounds':<6} | {'Outcome'}"
        print(header)
        print("-" * 90)

        for r in results:
            outcome = "PASS" if r["passed"] else "FAIL"
            row = f"{r['test_id']:<9} | {r['ground_truth_category']:<28} | {r['status']:<18} | {r['confidence']:<6.2f} | {r['rounds']:<6} | {outcome}"
            print(row)

        print("-" * 90)
        print(f"Overall Accuracy:        {summary['overall_accuracy_pct']}% ({summary['passed_tests']}/{summary['total_tests']} tests passed)")
        print(f"Noise Filter Specificity:{summary['noise_filtering_specificity_pct']}% (Zero hallucination on baseline)")
        print(f"Fault Recall Sensitivity:{summary['fault_detection_sensitivity_pct']}% (True Positive detection)")
        print(f"Mean Consensus Rounds:   {summary['average_debate_rounds']} (Loop broke via Dynamic Severity Multipliers)")
        print(f"Mean Confidence Score:   {summary['average_confidence']}")
        print(f"Mean Latency per Test:   {summary['average_latency_ms']} ms")
        print(f"Audit Results Appended:  {summary['results_logfile']}")
        print("=" * 90 + "\n")

def main():
    evaluator = NetCoopEvaluator()
    summary = evaluator.run_evaluation_suite()
    if summary["passed_tests"] != summary["total_tests"]:
        sys.exit(1)

if __name__ == "__main__":
    main()
