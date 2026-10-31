from core.shared_state import global_state

class InfrastructureSensor:
    def __init__(self):
        self.agent_id = "infrastructure_agent"

    def process_telemetry(self, raw_telemetry):
        device_id = raw_telemetry.get("device_id", "UNKNOWN")
        metrics = raw_telemetry.get("metrics", {})
        
        # 1. Update shared state so the Voter can read it later
        global_state.update_state(device_id, metrics)
        
        evidence = []
        data_errors = []
        alert_category = "healthy"

        # 2. Robustness Check: Type safety for malformed JSON
        try:
            cpu = float(metrics.get("cpu_utilization_pct", 0))
            errors = int(metrics.get("interface_errors", 0))
            drops = int(metrics.get("queue_drops", 0))
        except (ValueError, TypeError) as e:
            alert_category = "data_error"
            data_errors.append(f"Malformed metric types: {str(e)}")
            return self._build_alert(device_id, alert_category, evidence, data_errors)

        # 3. Threshold Evaluation
        if cpu > 85.0:
            alert_category = "anomaly"
            evidence.append({"metric": "cpu_utilization_pct", "value": cpu, "interpretation": "Critical CPU exhaustion"})
            
        if errors > 50:
            alert_category = "anomaly"
            evidence.append({"metric": "interface_errors", "value": errors, "interpretation": "High physical interface errors detected"})

        return self._build_alert(device_id, alert_category, evidence, data_errors)

    def _build_alert(self, device_id, category, evidence, errors):
        return {
            "message_type": "sensor_alert",
            "agent_id": self.agent_id,
            "device_id": device_id,
            "alert_category": category,
            "evidence": evidence,
            "data_errors": errors
        }