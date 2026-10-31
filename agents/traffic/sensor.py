from core.shared_state import global_state

class TrafficSensor:
    def __init__(self):
        self.agent_id = "traffic_agent"

    def process_telemetry(self, raw_telemetry):
        device_id = raw_telemetry.get("device_id", "UNKNOWN")
        metrics = raw_telemetry.get("metrics", {})
        
        # 1. Update shared state
        global_state.update_state(device_id, metrics)
        
        evidence = []
        data_errors = []
        alert_category = "healthy"

        # 2. Robustness Check: Type safety
        try:
            latency = float(metrics.get("latency_ms", 0))
            jitter = float(metrics.get("jitter_ms", 0))
            loss = float(metrics.get("packet_loss_pct", 0))
            utilization = float(metrics.get("link_utilization_pct", 0))
        except (ValueError, TypeError) as e:
            alert_category = "data_error"
            data_errors.append(f"Malformed traffic metric types: {str(e)}")
            return self._build_alert(device_id, alert_category, evidence, data_errors)

        # 3. Deterministic Thresholds
        if utilization > 85.0:
            alert_category = "anomaly"
            evidence.append({"metric": "link_utilization_pct", "value": utilization, "interpretation": "Link bandwidth saturated"})
            
        if latency > 150.0:
            alert_category = "anomaly"
            evidence.append({"metric": "latency_ms", "value": latency, "interpretation": "Elevated latency"})

        if loss > 2.0:
            alert_category = "anomaly"
            evidence.append({"metric": "packet_loss_pct", "value": loss, "interpretation": "Significant packet loss"})

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