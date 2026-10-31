from core.shared_state import global_state

class TrafficVoter:
    def __init__(self):
        self.agent_id = "traffic_agent"

    def evaluate_hypothesis(self, incident_or_payload, proposed_cause_param=None, target_devices_param=None):
        active_dev = [global_state.latest_device] if hasattr(global_state, "latest_device") and global_state.latest_device else list(global_state.device_states.keys())
        if isinstance(incident_or_payload, dict):
            hypothesis_broadcast = incident_or_payload
        else:
            hypothesis_broadcast = {
                "incident_id": incident_or_payload,
                "proposed_root_cause": proposed_cause_param or "",
                "proposed_cause": proposed_cause_param or "",
                "target_devices": target_devices_param or active_dev
            }
        incident_id = hypothesis_broadcast.get("incident_id")
        target_devices = hypothesis_broadcast.get("target_devices") or active_dev
        proposed_cause = (hypothesis_broadcast.get("proposed_root_cause") or hypothesis_broadcast.get("proposed_cause", "")).lower()

        vote = "ABSTAIN"
        reason = "No relevant telemetry found for target devices."
        evidence = []
        suggested_alt = None

        for device in target_devices:
            metrics = global_state.get_state(device)
            if not metrics:
                continue

            utilization = float(metrics.get("link_utilization_pct", 0) or 0)
            latency = float(metrics.get("latency_ms", 0) or 0)
            loss = float(metrics.get("packet_loss_pct", 0) or 0)

            if "congestion" in proposed_cause or "bandwidth" in proposed_cause:
                if utilization > 85.0 or latency > 150.0:
                    vote = "APPROVE"
                    reason = "High link utilization and latency confirm congestion."
                    evidence.append({
                        "metric": "link_utilization_pct",
                        "value": utilization,
                        "interpretation": "Confirms saturated link"
                    })
                else:
                    vote = "REJECT"
                    reason = "Link utilization and latency are normal. Not a congestion issue."
                    suggested_alt = "Investigate L4-L7 services or physical hardware"
            elif "hardware" in proposed_cause or "physical" in proposed_cause:
                if loss > 10.0 or latency > 400.0:
                    vote = "APPROVE"
                    reason = "Severe packet loss and latency corroborate physical link failure."
                    evidence.append({
                        "metric": "packet_loss_pct",
                        "value": loss,
                        "interpretation": "Severe drop rate matches hardware fault profile"
                    })
                else:
                    vote = "REJECT"
                    reason = "Traffic metrics are too stable for a severe hardware fault."
                    suggested_alt = "Check for localized software or service anomalies"

        return {
            "message_type": "hypothesis_vote",
            "incident_id": incident_id,
            "agent_id": self.agent_id,
            "vote": vote,
            "reason": reason,
            "pivot_hint": suggested_alt if vote == "REJECT" else None,
            "supporting_evidence": evidence,
            "suggested_alternative": suggested_alt
        }
