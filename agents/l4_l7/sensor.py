from core.shared_state import global_state

class L4L7Sensor:
    def __init__(self):
        self.agent_id = "l4_l7_agent"

    def process_telemetry(self, raw_telemetry):
        device_id = raw_telemetry.get("device_id", "UNKNOWN")
        metrics = raw_telemetry.get("metrics", {})
        
        # 1. Update shared state
        global_state.update_state(device_id, metrics)
        
        evidence = []
        data_errors = []
        alert_category = "healthy"

        # 2. Robustness Check & Default Handling
        # If the keys don't exist, we assume healthy defaults (10ms DNS, 50% DHCP)
        try:
            dns_latency = float(metrics.get("dns_latency_ms", 10.0))
            dhcp_util = float(metrics.get("dhcp_pool_utilization_pct", 50.0))
        except (ValueError, TypeError) as e:
            alert_category = "data_error"
            data_errors.append(f"Malformed L4/L7 metric types: {str(e)}")
            return self._build_alert(device_id, alert_category, evidence, data_errors)

        # 3. Deterministic Thresholds
        if dns_latency > 150.0:
            alert_category = "anomaly"
            evidence.append({
                "metric": "dns_latency_ms", 
                "value": dns_latency, 
                "interpretation": "DNS resolution timeout/severe latency"
            })
            
        if dhcp_util > 95.0:
            alert_category = "anomaly"
            evidence.append({
                "metric": "dhcp_pool_utilization_pct", 
                "value": dhcp_util, 
                "interpretation": "DHCP IP pool exhausted"
            })

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