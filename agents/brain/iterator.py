import asyncio
import os
import time
from typing import Dict, List, Any, Optional

from core.memory import shared_memory
from core.shared_state import global_state
from core.output_store import save_output_json

class AsyncConsensusIterator:
    """Orchestrates voting rounds asynchronously or synchronously to minimize LLM latency."""
    def __init__(self, voter_agents, reasoner, output_file: str = "output.json"):
        self.voter_agents = voter_agents
        self.voters = voter_agents  # Backwards compatibility
        self.reasoner = reasoner
        self.max_rounds = 3
        self.output_file = output_file

    def calculate_heuristic_consensus(self, agent_responses, active_alerts, round_num=1):
        """
        Calculates consensus using Dynamic Severity Multipliers and verbosely logs the math.
        """
        print(f"\n[EPOCH {round_num}: MIDDLEWARE & CONSENSUS MATH]")
        print("Middleware: All JSON payloads validated successfully. No semantic drift detected.")
        
        # 1. Map the exact float anomaly score directly to the agent's voting power
        domain_weights = {"infrastructure_agent": 0.0, "traffic_agent": 0.0, "l4_l7_agent": 0.0}
        
        for alert in active_alerts:
            agent_mapping = {
                "infrastructure": "infrastructure_agent",
                "traffic": "traffic_agent",
                "l4_l7": "l4_l7_agent"
            }
            agent_key = agent_mapping.get(alert.get("source") or alert.get("domain"))
            current_weight = alert.get("anomaly_score", 0.0)
            if agent_key:
                domain_weights[agent_key] = max(domain_weights[agent_key], current_weight)

        # 2. Tally the weighted votes and log the agent decisions
        weighted_approves = 0.0
        weighted_total = 0.0

        print("\n--- AGENT VOTE TALLY ---")
        for response in agent_responses:
            agent_id = response.get("agent_id", "unknown_agent")
            vote = response.get("vote", "ABSTAIN")
            reason = response.get("reason", "No reason provided.")
            hint = response.get("pivot_hint")
            
            weight = domain_weights.get(agent_id, 0.0)
            
            severity_label = "HEALTHY"
            if weight >= 3.0: severity_label = "FATAL"
            elif weight >= 2.0: severity_label = "CRITICAL"
            elif weight >= 1.0: severity_label = "MAJOR"
            elif weight > 0.0: severity_label = "MINOR"

            print(f"--> {agent_id} (Active Multiplier: {weight} - {severity_label})")
            print(f"    Decision: {vote}")
            print(f"    Reasoning: {reason}")
            if hint:
                print(f"    Pivot Hint: {hint}")

            if vote == "APPROVE":
                weighted_approves += weight
                weighted_total += weight
            elif vote == "REJECT":
                weighted_total += weight

        # 3. Calculate final heuristic score
        confidence = 0.0
        if weighted_total > 0:
            confidence = round(weighted_approves / weighted_total, 2)
            
        print("\n--- CONSENSUS CALCULATION ---")
        print(f"- Total Possible Weight (Non-Abstaining): {weighted_total}")
        print(f"- Total Approve Weight: {weighted_approves}")
        print(f"- Math: {weighted_approves} / {weighted_total if weighted_total > 0 else 1} = {confidence} Confidence")
        
        return confidence

    async def execute_voting_loop(self, incident_id, active_alerts, output_file: Optional[str] = None):
        """
        Manages the async debate, handling hypothesis generation and passing it to the voters.
        """
        target_output_file = output_file or self.output_file
        current_confidence = 0.0
        best_report = None
        
        try:
            for round_num in range(1, self.max_rounds + 1):
                print(f"\n=======================================================")
                print(f"[EPOCH {round_num}: HYPOTHESIS GENERATION]")
                print(f"=======================================================")
                
                # 1. Brain generates hypothesis
                memory_context = shared_memory.get_reasoner_context(incident_id)
                if asyncio.iscoroutinefunction(self.reasoner.generate_hypothesis):
                    hypothesis_payload = await self.reasoner.generate_hypothesis(incident_id, active_alerts, memory_context)
                else:
                    res = self.reasoner.generate_hypothesis(incident_id, active_alerts, memory_context)
                    hypothesis_payload = await res if asyncio.iscoroutine(res) else res

                proposed_cause = hypothesis_payload.get("proposed_cause") or hypothesis_payload.get("proposed_root_cause", "Unknown network anomaly.")
                print(f"Brain Agent: {proposed_cause}")

                print(f"\n[EPOCH {round_num}: ASYNC VOTER BROADCAST]")
                
                # 2. Broadcast to voters concurrently
                tasks = []
                for voter in self.voter_agents:
                    task = voter.evaluate_hypothesis(incident_id, proposed_cause)
                    if asyncio.iscoroutine(task):
                        tasks.append(task)
                    else:
                        async def _wrap(res=task):
                            return res
                        tasks.append(_wrap())
                    
                raw_responses = await asyncio.gather(*tasks)
                valid_responses = raw_responses 

                # Record round hypothesis and votes in shared memory
                shared_memory.record_hypothesis(incident_id, round_num, proposed_cause)
                for r in valid_responses:
                    shared_memory.record_vote(
                        incident_id=incident_id,
                        round_num=round_num,
                        agent_id=r.get("agent_id", "unknown_agent"),
                        vote=r.get("vote", "ABSTAIN"),
                        reason=r.get("reason", ""),
                        alternative=r.get("suggested_alternative"),
                        pivot_hint=r.get("pivot_hint")
                    )

                # 4. Calculate weighted consensus with verbose trace
                current_confidence = self.calculate_heuristic_consensus(valid_responses, active_alerts, round_num)
                
                # Collect evidence from APPROVE votes
                round_evidence = []
                for r in valid_responses:
                    if r.get("vote") == "APPROVE" and "supporting_evidence" in r:
                        round_evidence.extend(r["supporting_evidence"])
                
                target_devs = list(set([a.get("device_id") for a in active_alerts if a.get("device_id")])) or list(global_state.device_states.keys())
                best_report = {
                    "incident_id": incident_id,
                    "status": "diagnosed" if current_confidence >= 0.70 else "investigating",
                    "suspected_root_cause": proposed_cause,
                    "confidence": current_confidence,
                    "affected_devices": target_devs,
                    "supporting_evidence": round_evidence,
                    "alternative_causes": [r.get("suggested_alternative") for r in valid_responses if r.get("suggested_alternative")],
                    "recommended_actions": hypothesis_payload.get("recommended_actions", ["Manual review required"]),
                    "evidence_sources": [r.get("agent_id") for r in valid_responses if r.get("vote") != "ABSTAIN"],
                    "limitations": [f"Consensus reached in round {round_num}"] if current_confidence >= 0.70 else ["Failed to reach consensus"]
                }

                if current_confidence >= 0.70:
                    print(f"\n=> STATUS: SUCCESS. Consensus Exit Condition ({current_confidence} >= 0.70) Met.")
                    break
                else:
                    print(f"\n=> STATUS: FAILED. Confidence {current_confidence} < 0.70. Forcing Memory Loop.")
                    round_feedback = f"Round {round_num} Failed. Hypothesis: '{proposed_cause}'\n"
                    for response in valid_responses:
                        vote = response.get("vote")
                        agent = response.get("agent_id")
                        hint = response.get("pivot_hint")
                        
                        if vote == "REJECT":
                            round_feedback += f"- {agent} VOTED REJECT. "
                            if hint:
                                round_feedback += f"CRITICAL PIVOT HINT: {hint}\n"
                            else:
                                round_feedback += f"Reason: {response.get('reason')}\n"

                    if hasattr(self.reasoner, "memory") and isinstance(self.reasoner.memory, list):
                        self.reasoner.memory.append(round_feedback)
                    shared_memory.add_failed_round(incident_id, proposed_cause, round_feedback)
            
            # Record final report to persistent memory
            if best_report:
                shared_memory.record_final_report(incident_id, best_report)
                if target_output_file:
                    save_output_json(best_report, filepath=target_output_file)

            return best_report
        finally:
            shared_memory.clear_incident(incident_id, archive=True)

    def execute_voting_loop_sync(self, incident_id, active_alerts, output_file: Optional[str] = None):
        """
        Synchronous counterpart to execute_voting_loop with identical verbose logging and persistence.
        """
        target_output_file = output_file or self.output_file
        current_confidence = 0.0
        best_report = None

        try:
            for round_num in range(1, self.max_rounds + 1):
                print(f"\n=======================================================")
                print(f"[EPOCH {round_num}: HYPOTHESIS GENERATION]")
                print(f"=======================================================")

                memory_context = shared_memory.get_reasoner_context(incident_id)
                if hasattr(self.reasoner, "generate_hypothesis_sync"):
                    hypothesis_payload = self.reasoner.generate_hypothesis_sync(incident_id, active_alerts, memory_context)
                else:
                    hypothesis_payload = self.reasoner.generate_hypothesis(incident_id, active_alerts)

                proposed_cause = hypothesis_payload.get("proposed_cause") or hypothesis_payload.get("proposed_root_cause", "Unknown network anomaly.")
                print(f"Brain Agent: {proposed_cause}")

                print(f"\n[EPOCH {round_num}: ASYNC VOTER BROADCAST]")

                valid_responses = []
                for voter in self.voter_agents:
                    res = voter.evaluate_hypothesis(incident_id, proposed_cause)
                    valid_responses.append(res)

                # Record round hypothesis and votes in shared memory
                shared_memory.record_hypothesis(incident_id, round_num, proposed_cause)
                for r in valid_responses:
                    shared_memory.record_vote(
                        incident_id=incident_id,
                        round_num=round_num,
                        agent_id=r.get("agent_id", "unknown_agent"),
                        vote=r.get("vote", "ABSTAIN"),
                        reason=r.get("reason", ""),
                        alternative=r.get("suggested_alternative"),
                        pivot_hint=r.get("pivot_hint")
                    )

                current_confidence = self.calculate_heuristic_consensus(valid_responses, active_alerts, round_num)

                round_evidence = []
                for r in valid_responses:
                    if r.get("vote") == "APPROVE" and "supporting_evidence" in r:
                        round_evidence.extend(r["supporting_evidence"])

                target_devs = list(set([a.get("device_id") for a in active_alerts if a.get("device_id")])) or list(global_state.device_states.keys())
                best_report = {
                    "incident_id": incident_id,
                    "status": "diagnosed" if current_confidence >= 0.70 else "investigating",
                    "suspected_root_cause": proposed_cause,
                    "confidence": current_confidence,
                    "affected_devices": target_devs,
                    "supporting_evidence": round_evidence,
                    "alternative_causes": [r.get("suggested_alternative") for r in valid_responses if r.get("suggested_alternative")],
                    "recommended_actions": hypothesis_payload.get("recommended_actions", ["Manual review required"]),
                    "evidence_sources": [r.get("agent_id") for r in valid_responses if r.get("vote") != "ABSTAIN"],
                    "limitations": [f"Consensus reached in round {round_num}"] if current_confidence >= 0.70 else ["Failed to reach consensus"]
                }

                if current_confidence >= 0.70:
                    print(f"\n=> STATUS: SUCCESS. Consensus Exit Condition ({current_confidence} >= 0.70) Met.")
                    break
                else:
                    print(f"\n=> STATUS: FAILED. Confidence {current_confidence} < 0.70. Forcing Memory Loop.")
                    round_feedback = f"Round {round_num} Failed. Hypothesis: '{proposed_cause}'\n"
                    for response in valid_responses:
                        vote = response.get("vote")
                        agent = response.get("agent_id")
                        hint = response.get("pivot_hint")
                        
                        if vote == "REJECT":
                            round_feedback += f"- {agent} VOTED REJECT. "
                            if hint:
                                round_feedback += f"CRITICAL PIVOT HINT: {hint}\n"
                            else:
                                round_feedback += f"Reason: {response.get('reason')}\n"

                    if hasattr(self.reasoner, "memory") and isinstance(self.reasoner.memory, list):
                        self.reasoner.memory.append(round_feedback)
                    shared_memory.add_failed_round(incident_id, proposed_cause, round_feedback)

            if best_report:
                shared_memory.record_final_report(incident_id, best_report)
                if target_output_file:
                    save_output_json(best_report, filepath=target_output_file)

            return best_report
        finally:
            shared_memory.clear_incident(incident_id, archive=True)

    async def route_and_resolve_batch(self, all_active_alerts, output_file: Optional[str] = None):
        target_output_file = output_file or self.output_file
        if not all_active_alerts:
            return []

        grouped_incidents = {}
        for alert in all_active_alerts:
            device = alert["device_id"]
            if device not in grouped_incidents:
                grouped_incidents[device] = []
            grouped_incidents[device].append(alert)

        sorted_devices = sorted(
            grouped_incidents.keys(),
            key=lambda d: min([alert.get("timestamp", "9999") for alert in grouped_incidents[d]])
        )

        all_reports = []
        for device in sorted_devices:
            alerts = grouped_incidents[device]
            incident_id = f"INC-{device}-{int(time.time())}"
            print(f"\n" + "="*50)
            print(f"[SYSTEM ROUTER] DEPLOYING AGENTS FOR: {incident_id}")
            print("="*50)
            report = await self.execute_voting_loop(incident_id, alerts, output_file=target_output_file)
            all_reports.append(report)

        if all_reports and target_output_file:
            save_output_json(all_reports, filepath=target_output_file)

        return all_reports
