from core.fuzzy import FuzzyLogicEngine

class InfrastructureSensor:
    def __init__(self):
        self.domain = "infrastructure"
        
        # Define the fuzzy set boundaries (a, b, c) for each metric
        self.fuzzy_rules = {
            "cpu_utilization_pct": {
                "Normal": (0, 0, 75),       # Peaks at 0, drops to 0 at 75%
                "Warning": (65, 80, 90),    # Peaks at 80%
                "Critical": (85, 100, 100)  # Peaks at 100%
            },
            "queue_drops": {
                "Normal": (0, 0, 500),
                "Warning": (100, 1000, 5000),
                "Critical": (2500, 10000, 999999)
            },
            "interface_errors": {
                "Normal": (0, 0, 5),        # Even a few errors suggest cable degradation
                "Warning": (2, 50, 200),
                "Critical": (100, 1000, 999999)
            }
        }

    def process_telemetry(self, payload):
        metrics = payload.get("metrics", {})
        device_id = payload.get("device_id", "UNKNOWN_DEVICE")
        
        evidence = []
        anomaly_scores = []
        
        # Loop dynamically through all configured rules
        for metric_name, rules in self.fuzzy_rules.items():
            val = metrics.get(metric_name)
            if val is not None:
                state, degree = FuzzyLogicEngine.fuzzify_metric(
                    val, rules["Normal"], rules["Warning"], rules["Critical"]
                )
                
                # Only flag evidence if it crosses into Warning/Critical territory
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