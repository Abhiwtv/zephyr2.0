import asyncio
from core.memory import shared_memory
import time

class AsyncConsensusIterator:
    """Orchestrates voting rounds asynchronously to minimize LLM latency."""
    def __init__(self, voter_agents, reasoner):
        self.voters = voter_agents  # List of instantiated LLMDomainVoter objects
        self.reasoner = reasoner
        self.max_rounds = 3

    async def _async_get_vote(self, voter, hypothesis):
        """Wraps the synchronous Gemini call in an async thread."""
        # For a hackathon, running blocking IO in an async wrapper is sufficient
        return await asyncio.to_thread(voter.evaluate_hypothesis, hypothesis)
    
    async def route_and_resolve_batch(self, all_active_alerts):
        """
        SYSTEM ORCHESTRATOR: Takes a chaotic stream of multi-device alerts, 
        groups them logically, and queues them sequentially to protect local LLM VRAM.
        """
        if not all_active_alerts:
            return []

        # 1. Group alerts by device to strictly separate the incidents
        grouped_incidents = {}
        for alert in all_active_alerts:
            device = alert["device_id"]
            if device not in grouped_incidents:
                grouped_incidents[device] = []
            grouped_incidents[device].append(alert)

        # 2. Sort incidents chronologically (earliest alert first)
        sorted_devices = sorted(
            grouped_incidents.keys(),
            key=lambda d: min([alert.get("timestamp", "9999") for alert in grouped_incidents[d]])
        )

        all_reports = []
        print(f"\n[SYSTEM ROUTER] Detected {len(sorted_devices)} distinct fault domains. Queuing LLM diagnostics...")
        
        # 3. Execute one full debate at a time sequentially
        for device in sorted_devices:
            alerts = grouped_incidents[device]
            incident_id = f"INC-{device}-{int(time.time())}"
            
            print(f"\n" + "="*50)
            print(f"[SYSTEM ROUTER] DEPLOYING AGENTS FOR: {incident_id}")
            print("="*50)
            
            # Await pauses the router until this specific switch's debate is 100% finished
            report = await self.execute_voting_loop(incident_id, alerts)
            all_reports.append(report)

        return all_reports
    
    async def execute_voting_loop(self, incident_id, initial_alerts):
        current_round = 1
        best_report = None
        highest_confidence = -1.0

        while current_round <= self.max_rounds:
            print(f"\n--- INITIATING ROUND {current_round} ---")
            
            # 1. Fetch memory context and generate hypothesis
            memory_context = shared_memory.get_reasoner_context(incident_id)
            hypothesis = self.reasoner.generate_hypothesis(incident_id, initial_alerts, memory_context)
            
            print(f"Brain Hypothesis: {hypothesis['proposed_root_cause']}")
            
            # Save the Brain's guess to memory
            shared_memory.record_hypothesis(incident_id, current_round, hypothesis['proposed_root_cause'])

            # 2. Broadcast to all voters concurrently
            print("Broadcasting to Domain Agents concurrently...")
            tasks = [self._async_get_vote(voter, hypothesis) for voter in self.voters]
            votes = await asyncio.gather(*tasks)

            # 3. Process Votes and update Memory
            approvals = 0
            rejections = 0
            abstentions = 0

            for v in votes:
                agent_id = v["agent_id"]
                vote_cast = v["vote"]
                
                print(f"[{agent_id}] voted {vote_cast}")
                
                shared_memory.record_vote(
                    incident_id=incident_id,
                    round_num=current_round,
                    agent_id=agent_id,
                    vote=vote_cast,
                    reason=v["reason"],
                    alternative=v.get("suggested_alternative"),
                    question=v.get("targeted_question")
                )

                if vote_cast == "APPROVE":
                    approvals += 1
                elif vote_cast == "REJECT":
                    rejections += 1
                elif vote_cast == "ABSTAIN":
                    abstentions += 1

            # 4. Confidence Math
            total_opinions = approvals + rejections
            confidence = 0.30 if total_opinions == 0 else round((approvals / total_opinions), 2)
            
            # Edge case: If 1 approves and 2 abstain (healthy domains), it's a strong hypothesis
            if approvals >= 1 and rejections == 0:
                 confidence = min(0.95, confidence + 0.20)

            print(f"Round {current_round} Confidence: {confidence}")

            # 5. Build Intermediate Report
            report = self._build_report(incident_id, hypothesis, initial_alerts, votes, confidence)
            
            if confidence > highest_confidence:
                highest_confidence = confidence
                best_report = report

            # 6. Break Conditions
            if confidence >= 0.70:
                best_report["limitations"].append(f"Consensus reached in round {current_round}")
                break
                
            current_round += 1

        # Clear memory after the loop concludes to prevent state bleed
        shared_memory.clear_incident(incident_id)
        return best_report

    def _build_report(self, incident_id, hypothesis, initial_alerts, votes, confidence):
        final_evidence = []
        data_errors_found = []
        alternative_causes = []
        sources = set()

        for alert in initial_alerts:
            final_evidence.extend(alert.get("evidence", []))
            data_errors_found.extend(alert.get("data_errors", []))
            
        for vote in votes:
            if vote.get("supporting_evidence"):
                 final_evidence.extend(vote["supporting_evidence"])
            if vote["vote"] != "ABSTAIN":
                sources.add(vote["agent_id"])
            if vote.get("suggested_alternative"):
                alternative_causes.append(vote["suggested_alternative"])

        # Deduplicate evidence
        unique_evidence = []
        seen = set()
        for ev in final_evidence:
            identifier = f"{ev['metric']}_{ev['value']}"
            if identifier not in seen:
                seen.add(identifier)
                unique_evidence.append(ev)

        # Build dynamic actions
        # Build dynamic actions
        actions = []
        cause = hypothesis["proposed_root_cause"].lower()
        if "hardware" in cause or "physical" in cause or "cpu" in cause or "interface" in cause:
            actions = ["Dispatch physical technician", "Isolate affected port", "Check physical cabling"]
        elif "congestion" in cause or "bandwidth" in cause or "saturation" in cause:
            actions = ["Inspect upstream link utilization", "Review QoS configuration"]
        elif "service" in cause or "dns" in cause:
            actions = ["Check DNS/DHCP server logs", "Scale out service instances"]

        limitations = []
        if data_errors_found:
             limitations.append(f"Malformed data encountered: {data_errors_found[0]}")
        if confidence < 0.7:
             limitations.append("Failed to reach strong consensus. Outputting best hypothesis.")

        return {
            "incident_id": incident_id,
            "status": "diagnosed" if confidence >= 0.7 else "investigating",
            "suspected_root_cause": hypothesis["proposed_root_cause"],
            "confidence": confidence,
            "affected_devices": hypothesis["target_devices"],
            "supporting_evidence": unique_evidence,
            "alternative_causes": list(set(alternative_causes)),
            "recommended_actions": actions,
            "evidence_sources": list(sources),
            "limitations": limitations
        }