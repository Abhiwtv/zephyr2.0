from core.fuzzy import FuzzyLogicEngine

class L4L7Sensor:
    def __init__(self):
        self.domain = "l4_l7"
        self.fuzzy_rules = {
            "dhcp_pool_utilization_pct": {
                "Normal": (0, 0, 80),
                "Warning": (70, 85, 95),
                "Critical": (90, 100, 100)
            },
            "dns_latency_ms": {
                "Normal": (0, 0, 50),
                "Warning": (40, 100, 200),
                "Critical": (150, 500, 9999)
            }
        }

    def process_telemetry(self, payload):
        metrics = payload.get("metrics", {})
        device_id = payload.get("device_id", "UNKNOWN_DEVICE")
        
        evidence = []
        anomaly_scores = []
        
        for metric_name, rules in self.fuzzy_rules.items():
            val = metrics.get(metric_name)
            if val is not None:
                state, degree = FuzzyLogicEngine.fuzzify_metric(
                    val, rules["Normal"], rules["Warning"], rules["Critical"]
                )
                if state in ["Warning", "Critical"] and degree > 0.3:
                    evidence.append({
                        "metric": metric_name,
                        "value": val,
                        "interpretation": f"{state} {metric_name.replace('_', ' ')} (Fuzzy Confidence: {degree:.2f})"
                    })
                    anomaly_scores.append(degree)

        # Defuzzification (State-based Hierarchy)
        overall_severity = "healthy"
        if evidence:
            # Check if any evidence explicitly triggered a 'Critical' state
            states = [ev["interpretation"].split()[0] for ev in evidence]
            if "Critical" in states:
                overall_severity = "critical"
            elif "Warning" in states:
                overall_severity = "warning"

        return {
            "device_id": device_id,
            "domain": self.domain,
            "alert_category": overall_severity,
            "evidence": evidence,
            "data_errors": []
        }