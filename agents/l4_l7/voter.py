from core.shared_state import global_state

class L4L7Voter:
    def __init__(self):
        self.agent_id = "l4_l7_agent"

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

            dns_latency = float(metrics.get("dns_latency_ms", 10.0) or 10.0)
            dhcp_util = float(metrics.get("dhcp_pool_utilization_pct", 50.0) or 50.0)

            if "dns" in proposed_cause or "dhcp" in proposed_cause or "service" in proposed_cause:
                if dns_latency > 150.0 or dhcp_util > 95.0:
                    vote = "APPROVE"
                    reason = "L4/L7 telemetry confirms service exhaustion or timeout."
                    if dns_latency > 150.0:
                        evidence.append({
                            "metric": "dns_latency_ms",
                            "value": dns_latency,
                            "interpretation": "Confirms DNS failure"
                        })
                    if dhcp_util > 95.0:
                        evidence.append({
                            "metric": "dhcp_pool_utilization_pct",
                            "value": dhcp_util,
                            "interpretation": "Confirms DHCP exhaustion"
                        })
                else:
                    vote = "REJECT"
                    reason = "DNS and DHCP metrics are well within normal operating bounds."
                    suggested_alt = "Check physical hardware or link congestion"
            elif "hardware" in proposed_cause or "congestion" in proposed_cause:
                if dns_latency > 150.0 or dhcp_util > 95.0:
                    vote = "REJECT"
                    reason = "Metrics show an L4/L7 service failure, which might be misidentified as general congestion."
                    suggested_alt = "DNS or DHCP Service Failure"
                else:
                    vote = "ABSTAIN"
                    reason = "Core services are healthy. Hardware/Congestion hypothesis is outside this agent's domain."

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
