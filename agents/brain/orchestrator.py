import uuid

class ReasoningEngine:
    """Part A: Isolated logic engine. Generates a hypothesis based on evidence OR feedback."""
    def __init__(self):
        pass

    def generate_hypothesis(self, incident_id, aggregated_alerts, feedback_from_last_round=None):
        devices = list(set([alert["device_id"] for alert in aggregated_alerts]))

        if feedback_from_last_round:
            return {
                "message_type": "hypothesis_broadcast",
                "incident_id": incident_id,
                "proposed_root_cause": feedback_from_last_round[0],
                "target_devices": devices
            }

        has_hw_fault = False
        has_congestion = False
        has_l4_fault = False

        for alert in aggregated_alerts:
            for ev in alert.get("evidence", []):
                metric = ev.get("metric", "")
                if metric in ("interface_errors", "cpu_utilization_pct", "queue_drops"):
                    has_hw_fault = True
                elif metric in ("link_utilization_pct", "latency_ms"):
                    has_congestion = True
                elif metric in ("dns_latency_ms", "dhcp_pool_utilization_pct"):
                    has_l4_fault = True

        if has_hw_fault:
            cause = "Hardware failure leading to control plane exhaustion"
        elif has_l4_fault:
            cause = "Core L4-L7 Service Timeout (DNS/DHCP)"
        elif has_congestion:
            cause = "Likely link congestion causing elevated latency"
        else:
            cause = "Unknown network anomaly"

        return {
            "message_type": "hypothesis_broadcast",
            "incident_id": incident_id,
            "proposed_root_cause": cause,
            "target_devices": devices
        }

class ConsensusIterator:
    """Part B: The loop manager. Orchestrates rounds between Reasoner and Voters."""
    def __init__(self, voter_agents, reasoner):
        self.voters = voter_agents
        self.reasoner = reasoner
        self.max_rounds = 3

    def calculate_heuristic_consensus(self, agent_responses, active_alerts):
        """
        Calculates consensus using Dynamic Severity Multipliers.
        Agents with FATAL (3.0) anomalies mathematically bulldoze agents with MINOR (0.5) anomalies.
        """
        domain_weights = {"infrastructure_agent": 0.0, "traffic_agent": 0.0, "l4_l7_agent": 0.0}
        
        for alert in active_alerts:
            agent_mapping = {
                "infrastructure": "infrastructure_agent",
                "traffic": "traffic_agent",
                "l4_l7": "l4_l7_agent"
            }
            agent_key = agent_mapping.get(alert.get("source") or alert.get("domain"))
            if agent_key:
                current_weight = alert.get("anomaly_score", 0.0)
                domain_weights[agent_key] = max(domain_weights[agent_key], current_weight)

        weighted_approves = 0.0
        weighted_total = 0.0

        for response in agent_responses:
            agent_id = response.get("agent_id")
            vote = response.get("vote")
            weight = domain_weights.get(agent_id, 0.0)

            if vote == "APPROVE":
                weighted_approves += weight
                weighted_total += weight
            elif vote == "REJECT":
                weighted_total += weight

        if weighted_total == 0:
            return 0.0
            
        confidence = weighted_approves / weighted_total
        return round(confidence, 2)

    def execute_voting_loop(self, incident_id, initial_alerts):
        current_round = 1
        feedback = []
        best_report = None
        highest_confidence = -1.0

        while current_round <= self.max_rounds:
            hypothesis = self.reasoner.generate_hypothesis(incident_id, initial_alerts, feedback)

            votes = []
            for voter in self.voters:
                vote_result = voter.evaluate_hypothesis(hypothesis)
                votes.append(vote_result)

            approvals = sum(1 for v in votes if v["vote"] == "APPROVE")
            rejections = sum(1 for v in votes if v["vote"] == "REJECT")
            abstentions = sum(1 for v in votes if v["vote"] == "ABSTAIN")
            total_opinions = approvals + rejections

            heuristic_conf = self.calculate_heuristic_consensus(votes, initial_alerts)
            if heuristic_conf > 0.0:
                confidence = heuristic_conf
            else:
                confidence = 0.3 if total_opinions == 0 else round(approvals / total_opinions, 2)
                if approvals == 1 and abstentions == 2:
                    confidence = min(0.85, confidence)

            report = self._build_report(incident_id, hypothesis, initial_alerts, votes, confidence)

            if confidence > highest_confidence:
                highest_confidence = confidence
                best_report = report

            if confidence >= 0.7:
                best_report["limitations"].append(f"Consensus reached in round {current_round}")
                return best_report

            feedback = [v["suggested_alternative"] for v in votes if v.get("suggested_alternative")]
            current_round += 1

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

        unique_evidence = []
        seen_evidence = set()
        for ev in final_evidence:
            identifier = f"{ev['metric']}_{ev['value']}"
            if identifier not in seen_evidence:
                seen_evidence.add(identifier)
                unique_evidence.append(ev)

        actions = []
        cause = hypothesis["proposed_root_cause"].lower()
        if "hardware" in cause:
            actions = ["Dispatch physical technician", "Isolate affected port"]
        elif "congestion" in cause:
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

class BrainAgent:
    """Simple wrapper to initialize the decoupled components."""
    def __init__(self, voter_agents):
        self.reasoner = ReasoningEngine()
        self.iterator = ConsensusIterator(voter_agents, self.reasoner)

    def diagnose_network(self, active_alerts):
        if not active_alerts:
            return {"status": "healthy", "message": "No active alerts."}

        incident_id = f"INC-{str(uuid.uuid4())[:8].upper()}"
        return self.iterator.execute_voting_loop(incident_id, active_alerts)
