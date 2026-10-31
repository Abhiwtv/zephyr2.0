from core.shared_state import global_state

class InfrastructureVoter:
    def __init__(self):
        self.agent_id = "infrastructure_agent"

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

            cpu = float(metrics.get("cpu_utilization_pct", 0) or 0)
            errors = int(metrics.get("interface_errors", 0) or 0)

            if "hardware" in proposed_cause or "physical" in proposed_cause:
                if errors > 50 or cpu > 90.0:
                    vote = "APPROVE"
                    reason = "Local telemetry confirms hardware deterioration."
                    evidence.append({
                        "metric": "interface_errors",
                        "value": errors,
                        "interpretation": "Corroborates hardware fault"
                    })
                else:
                    vote = "REJECT"
                    reason = "CPU and interface errors are normal. Hardware is stable."
                    suggested_alt = "Likely link congestion causing elevated latency"
            elif "congestion" in proposed_cause:
                if errors > 50:
                    vote = "REJECT"
                    reason = "High interface errors point to hardware, not simple congestion."
                    suggested_alt = "Hardware failure leading to control plane exhaustion"
                    evidence.append({
                        "metric": "interface_errors",
                        "value": errors,
                        "interpretation": "Contradicts pure congestion"
                    })
                else:
                    vote = "APPROVE"
                    reason = "No hardware faults detected, congestion is plausible."

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
