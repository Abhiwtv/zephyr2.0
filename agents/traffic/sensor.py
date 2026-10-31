from core.fuzzy import FuzzyLogicEngine

class TrafficSensor:
    def __init__(self):
        self.domain = "traffic"
        self.fuzzy_rules = {
            "link_utilization_pct": {
                "Normal": (0, 0, 75),
                "Warning": (65, 80, 95),
                "Critical": (85, 100, 100)
            },
            "packet_loss_pct": {
                "Normal": (0, 0, 2),
                "Warning": (1, 3, 5),
                "Critical": (4, 10, 100)
            },
            "latency_ms": {
                "Normal": (0, 0, 50),
                "Warning": (40, 100, 200),
                "Critical": (150, 300, 9999)
            },
            "jitter_ms": {
                "Normal": (0, 0, 20),
                "Warning": (15, 30, 50),
                "Critical": (40, 100, 9999)
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