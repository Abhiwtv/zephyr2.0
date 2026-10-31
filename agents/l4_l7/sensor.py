from datetime import datetime, timezone
from core.shared_state import global_state

class L4L7Sensor:
    def __init__(self):
        self.domain = "l4_l7"
        self.agent_id = "l4_l7_agent"

    def process_telemetry(self, payload: dict) -> dict:
        device_id = payload.get("device_id", "UNKNOWN_DEVICE")
        metrics = payload.get("metrics", {})
        timestamp = payload.get("timestamp") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Update shared state
        global_state.update_state(device_id, metrics)

        # Type safety validation for malformed inputs
        try:
            raw_dhcp = metrics.get("dhcp_pool_utilization_pct")
            dhcp = float(raw_dhcp) if raw_dhcp is not None else None

            raw_dns = metrics.get("dns_latency_ms")
            dns = float(raw_dns) if raw_dns is not None else None
        except (ValueError, TypeError) as e:
            return {
                "source": self.domain,
                "domain": self.domain,
                "device_id": device_id,
                "timestamp": timestamp,
                "anomaly_score": 0.0,
                "alert_category": "data_error",
                "evidence": [],
                "data_errors": [f"Malformed L4/L7 metric: {e}"]
            }

        # Calculate dynamic severity multipliers
        # DHCP pool utilization tiers
        dhcp_score = 0.0
        if dhcp is not None:
            if dhcp >= 99.0:
                dhcp_score = 3.0    # FATAL (Complete pool exhaustion)
            elif dhcp >= 90.0:
                dhcp_score = 2.0    # CRITICAL
            elif dhcp >= 80.0:
                dhcp_score = 1.0    # MAJOR
            elif dhcp >= 70.0:
                dhcp_score = 0.5    # MINOR

        # DNS latency tiers
        dns_score = 0.0
        if dns is not None:
            if dns >= 400.0:
                dns_score = 3.0     # FATAL (DNS Service failure/timeout)
            elif dns >= 200.0:
                dns_score = 2.0     # CRITICAL
            elif dns >= 100.0:
                dns_score = 1.0     # MAJOR
            elif dns >= 50.0:
                dns_score = 0.5     # MINOR

        # The total anomaly score is the highest individual metric score
        max_anomaly_score = max(dhcp_score, dns_score)

        evidence = []
        if dhcp_score > 0 and dhcp is not None:
            evidence.append({"metric": "dhcp_pool_utilization_pct", "value": dhcp, "interpretation": f"DHCP pool utilization score {dhcp_score}"})
        if dns_score > 0 and dns is not None:
            evidence.append({"metric": "dns_latency_ms", "value": dns, "interpretation": f"DNS latency score {dns_score}"})

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
