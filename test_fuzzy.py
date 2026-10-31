import json
from core.fuzzy import FuzzyLogicEngine
from agents.infrastructure.sensor import InfrastructureSensor
from agents.traffic.sensor import TrafficSensor
from agents.l4_l7.sensor import L4L7Sensor

def run_fuzzy_tests():
    print("=== INITIALIZING NEURO-SYMBOLIC FUZZY SENSOR TESTS ===\n")
    
    infra = InfrastructureSensor()
    traffic = TrafficSensor()
    l4l7 = L4L7Sensor()

    test_payloads = [
        {
            "desc": "BENIGN BACKGROUND NOISE (Should be dropped)",
            "device_id": "ACCESS_SW_01",
            "metrics": {
                "cpu_utilization_pct": 12.5,
                "link_utilization_pct": 35.0,
                "packet_loss_pct": 0.0,
                "latency_ms": 10.0,
                "interface_errors": 0,
                "dns_latency_ms": 12.0
            }
        },
        {
            "desc": "BORDERLINE DEGRADATION (Should flag warnings)",
            "device_id": "CORE_RTR_02",
            "metrics": {
                "cpu_utilization_pct": 77.0,
                "link_utilization_pct": 82.0,
                "packet_loss_pct": 2.5,
                "latency_ms": 110.0,
                "interface_errors": 45,
                "dhcp_pool_utilization_pct": 86.0
            }
        },
        {
            "desc": "CRITICAL INCIDENT (Should flag severe hardware & traffic faults)",
            "device_id": "EDGE_FW_03",
            "metrics": {
                "cpu_utilization_pct": 99.5,
                "link_utilization_pct": 99.0,
                "packet_loss_pct": 15.0,
                "latency_ms": 450.0,
                "interface_errors": 12000,
                "dhcp_pool_utilization_pct": 100.0
            }
        }
    ]

    for payload in test_payloads:
        print(f"\n--- TESTING: {payload['desc']} ---")
        
        # Pass payload through all 3 sensors
        infra_alert = infra.process_telemetry(payload)
        traffic_alert = traffic.process_telemetry(payload)
        l4_alert = l4l7.process_telemetry(payload)
        
        for alert in [infra_alert, traffic_alert, l4_alert]:
            if alert["alert_category"] != "healthy":
                print(f"\n[{alert['domain'].upper()}] Severity: {alert['alert_category'].upper()}")
                for ev in alert["evidence"]:
                    print(f"  -> {ev['metric']}: {ev['value']} | {ev['interpretation']}")

if __name__ == "__main__":
    run_fuzzy_tests()