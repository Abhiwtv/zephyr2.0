from datetime import datetime, timezone
from core.shared_state import global_state

class InfrastructureSensor:
    def __init__(self):
        self.domain = "infrastructure"
        self.agent_id = "infrastructure_agent"

    def process_telemetry(self, payload: dict) -> dict:
        device_id = payload.get("device_id", "UNKNOWN_DEVICE")
        metrics = payload.get("metrics", {})
        timestamp = payload.get("timestamp") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Update shared state
        global_state.update_state(device_id, metrics)

        # Type safety validation for malformed inputs
        try:
            raw_cpu = metrics.get("cpu_utilization_pct", 0)
            cpu = float(raw_cpu if raw_cpu is not None else 0)

            raw_errors = metrics.get("interface_errors", 0)
            errors = int(raw_errors if raw_errors is not None else 0)

            raw_drops = metrics.get("queue_drops", 0)
            drops = int(raw_drops if raw_drops is not None else 0)
        except (ValueError, TypeError) as e:
            return {
                "source": self.domain,
                "domain": self.domain,
                "device_id": device_id,
                "timestamp": timestamp,
                "anomaly_score": 0.0,
                "alert_category": "data_error",
                "evidence": [],
                "data_errors": [f"Malformed infrastructure metric: {e}"]
            }

        # Calculate dynamic severity multipliers
        cpu_score = 0.0
        if cpu >= 99.0:
            cpu_score = 3.0    # FATAL (Total Meltdown)
        elif cpu >= 90.0:
            cpu_score = 2.0    # CRITICAL
        elif cpu >= 75.0:
            cpu_score = 1.0    # MAJOR (Warning)
        elif cpu >= 60.0:
            cpu_score = 0.5    # MINOR (Elevated)

        error_score = 3.0 if errors > 5000 else (1.5 if errors > 100 else 0.0)
        drop_score = 2.0 if drops > 10000 else (1.0 if drops > 1000 else 0.0)

        # The total anomaly score is the highest individual metric score
        max_anomaly_score = max(cpu_score, error_score, drop_score)

        evidence = []
        if cpu_score > 0:
            evidence.append({"metric": "cpu_utilization_pct", "value": cpu, "interpretation": f"CPU severity score {cpu_score}"})
        if error_score > 0:
            evidence.append({"metric": "interface_errors", "value": errors, "interpretation": f"Interface errors severity score {error_score}"})
        if drop_score > 0:
            evidence.append({"metric": "queue_drops", "value": drops, "interpretation": f"Queue drops severity score {drop_score}"})

        if max_anomaly_score > 0.0:
            return {
                "source": self.domain,
                "domain": self.domain,
                "device_id": device_id,
                "timestamp": timestamp,
                "anomaly_score": max_anomaly_score, # <-- NEW NUANCED MULTIPLIER
                "alert_category": "anomaly_detected", # Generic flag, math does the work now
                "evidence": evidence,
                "data_errors": []
            }

        return {
            "source": self.domain,
            "domain": self.domain,
            "device_id": device_id,
            "timestamp": timestamp,
            "alert_category": "healthy",
            "anomaly_score": 0.0,
            "evidence": [],
            "data_errors": []
        }
