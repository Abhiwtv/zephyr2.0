from datetime import datetime, timezone
from core.shared_state import global_state

class TrafficSensor:
    def __init__(self):
        self.domain = "traffic"
        self.agent_id = "traffic_agent"

    def process_telemetry(self, payload: dict) -> dict:
        device_id = payload.get("device_id", "UNKNOWN_DEVICE")
        metrics = payload.get("metrics", {})
        timestamp = payload.get("timestamp") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Update shared state
        global_state.update_state(device_id, metrics)

        # Type safety validation for malformed inputs
        try:
            raw_util = metrics.get("link_utilization_pct", 0)
            utilization = float(raw_util if raw_util is not None else 0)

            raw_loss = metrics.get("packet_loss_pct", 0)
            loss = float(raw_loss if raw_loss is not None else 0)

            raw_lat = metrics.get("latency_ms", 0)
            latency = float(raw_lat if raw_lat is not None else 0)

            raw_jit = metrics.get("jitter_ms", 0)
            jitter = float(raw_jit if raw_jit is not None else 0)
        except (ValueError, TypeError) as e:
            return {
                "source": self.domain,
                "domain": self.domain,
                "device_id": device_id,
                "timestamp": timestamp,
                "anomaly_score": 0.0,
                "alert_category": "data_error",
                "evidence": [],
                "data_errors": [f"Malformed traffic metric: {e}"]
            }

        # Calculate dynamic severity multipliers
        # Link utilization tiers
        util_score = 0.0
        if utilization >= 98.0:
            util_score = 3.0    # FATAL (Severe link saturation)
        elif utilization >= 90.0:
            util_score = 2.0    # CRITICAL
        elif utilization >= 80.0:
            util_score = 1.0    # MAJOR
        elif utilization >= 70.0:
            util_score = 0.5    # MINOR (Elevated - below 70% is baseline noise)

        # Packet loss tiers
        loss_score = 0.0
        if loss >= 25.0:
            loss_score = 3.0    # FATAL
        elif loss >= 20.0:
            loss_score = 2.0    # CRITICAL
        elif loss >= 10.0:
            loss_score = 1.0    # MAJOR (e.g. 15.5% routing loop symptom)
        elif loss >= 2.0:
            loss_score = 0.5    # MINOR

        # Latency tiers
        lat_score = 0.0
        if latency >= 1000.0:
            lat_score = 2.0
        elif latency >= 500.0:
            lat_score = 1.0     # MAJOR
        elif latency >= 150.0:
            lat_score = 0.5     # MINOR

        # Jitter tiers
        jit_score = 1.0 if jitter >= 100.0 else (0.5 if jitter >= 40.0 else 0.0)

        # The total anomaly score is the highest individual metric score
        max_anomaly_score = max(util_score, loss_score, lat_score, jit_score)

        evidence = []
        if util_score > 0:
            evidence.append({"metric": "link_utilization_pct", "value": utilization, "interpretation": f"Bandwidth utilization score {util_score}"})
        if loss_score > 0:
            evidence.append({"metric": "packet_loss_pct", "value": loss, "interpretation": f"Packet loss score {loss_score}"})
        if lat_score > 0:
            evidence.append({"metric": "latency_ms", "value": latency, "interpretation": f"Latency score {lat_score}"})
        if jit_score > 0:
            evidence.append({"metric": "jitter_ms", "value": jitter, "interpretation": f"Jitter score {jit_score}"})

        if max_anomaly_score > 0.0:
            return {
                "source": self.domain,
                "domain": self.domain,
                "device_id": device_id,
                "timestamp": timestamp,
                "anomaly_score": max_anomaly_score,
                "alert_category": "anomaly_detected",
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
