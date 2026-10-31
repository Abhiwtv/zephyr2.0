import json
import random
import math
from datetime import datetime, timezone, timedelta

def generate_telemetry(fault_type="healthy_baseline"):
    # 1. Base Setup (Healthy Network)
    timestamp = datetime.now(timezone.utc)
    device_id = f"SW_CAMPUS_{random.randint(1, 100)}"
    status = "Healthy"
    
    metrics = {
        "cpu_utilization_pct": round(random.uniform(10, 35), 2),
        "link_utilization_pct": round(random.uniform(20, 50), 2),
        "packet_loss_pct": 0.0,
        "latency_ms": round(random.uniform(5, 20), 2),
        "jitter_ms": round(random.uniform(1, 5), 2),
        "queue_drops": 0,
        "interface_errors": 0,
        "dns_latency_ms": round(random.uniform(10, 25), 2),
        "dhcp_pool_utilization_pct": round(random.uniform(20, 60), 2)
    }

    # ==========================================
    # CATEGORY 1: L1 & HARDWARE FAULTS
    # ==========================================
    if fault_type == "l1_cable_damage_lhc":
        device_id = "LHC_ROOM_104_SW"
        metrics.update({"interface_errors": random.randint(15000, 25000), "packet_loss_pct": round(random.uniform(15, 25), 2), "link_utilization_pct": 2.5})
        status = "Critical"
    elif fault_type == "l1_fiber_bend_core":
        device_id = "ADMIN_CORE_RTR"
        metrics.update({"interface_errors": random.randint(500, 2000), "packet_loss_pct": round(random.uniform(5, 12), 2), "latency_ms": 45.0})
        status = "Warning"
    elif fault_type == "l1_sfp_failure_ses":
        device_id = "SES_DEPT_SW"
        metrics.update({"interface_errors": random.randint(5000, 9000), "packet_loss_pct": round(random.uniform(8, 15), 2)})
        status = "Critical"
    elif fault_type == "l1_overheating_switch":
        device_id = "HOSTEL_M_CLOSET_SW"
        metrics.update({"cpu_utilization_pct": round(random.uniform(85, 95), 2), "queue_drops": random.randint(100, 500)})
        status = "Critical"
    elif fault_type == "l1_speed_duplex":
        device_id = "ADMIN_PRINTER_SW"
        metrics.update({"interface_errors": random.randint(1000, 3000), "latency_ms": round(random.uniform(100, 300), 2)})
        status = "Warning"
    elif fault_type == "l1_port_flap":
        device_id = "FACULTY_CABIN_SW"
        metrics.update({"link_utilization_pct": 0.0, "interface_errors": random.randint(50, 150)})
        status = "Warning"
    elif fault_type == "l1_dying_asic":
        device_id = "CAMPUS_CORE_02"
        metrics.update({"queue_drops": 99999, "packet_loss_pct": 99.0, "latency_ms": 5000.0, "cpu_utilization_pct": 100.0})
        status = "Critical"
    elif fault_type == "l1_cable_length":
        device_id = "CCTV_OUTDOOR_SW"
        metrics.update({"jitter_ms": round(random.uniform(150, 300), 2), "interface_errors": random.randint(100, 400)})
        status = "Warning"
    elif fault_type == "l1_ups_dip":
        device_id = "DATA_CENTER_SW_04"
        metrics.update({"cpu_utilization_pct": 99.0, "queue_drops": 5000}) # Reboot spike
        status = "Critical"

    # ==========================================
    # CATEGORY 2: L2 & CONTROL PLANE
    # ==========================================
    elif fault_type == "l2_broadcast_storm":
        device_id = "LIBRARY_ACCESS_SW"
        metrics.update({"cpu_utilization_pct": 100.0, "link_utilization_pct": 100.0, "queue_drops": random.randint(20000, 50000)})
        status = "Critical"
    elif fault_type == "l2_stp_loop":
        device_id = "SMS_DEPT_SW"
        metrics.update({"cpu_utilization_pct": 98.5, "latency_ms": round(random.uniform(800, 1200), 2), "packet_loss_pct": 25.0})
        status = "Critical"
    elif fault_type == "l2_mac_flap":
        device_id = "WIFI_CTRL_01"
        metrics.update({"cpu_utilization_pct": round(random.uniform(65, 85), 2), "jitter_ms": round(random.uniform(50, 100), 2)})
        status = "Warning"
    elif fault_type == "l2_mtu_mismatch":
        device_id = "CORE_TO_FW_LINK"
        metrics.update({"packet_loss_pct": round(random.uniform(2, 5), 2), "interface_errors": random.randint(100, 500)}) # fragmented drops show as errors/loss
        status = "Warning"
    elif fault_type == "l2_vlan_mismatch":
        device_id = "TRUNK_PORT_01"
        metrics.update({"latency_ms": round(random.uniform(100, 200), 2), "cpu_utilization_pct": 55.0})
        status = "Warning"
    elif fault_type == "l2_port_security":
        device_id = "HOSTEL_S_ROOM_SW"
        metrics.update({"link_utilization_pct": 0.0, "packet_loss_pct": 100.0}) # Port shutdown
        status = "Critical"
    elif fault_type == "l2_arp_storm":
        device_id = "GUEST_WIFI_VLAN"
        metrics.update({"cpu_utilization_pct": 95.0, "latency_ms": round(random.uniform(200, 400), 2)})
        status = "Critical"
    elif fault_type == "l2_udld_err":
        device_id = "FIBER_RUN_SES_SMS"
        metrics.update({"packet_loss_pct": 50.0, "interface_errors": 5000})
        status = "Critical"
    elif fault_type == "l2_storm_control":
        device_id = "LAB_COMPLEX_SW"
        metrics.update({"queue_drops": random.randint(5000, 10000), "packet_loss_pct": round(random.uniform(5, 10), 2)})
        status = "Warning"
    elif fault_type == "l2_stp_recalc":
        device_id = "DISTRIBUTION_SW_02"
        metrics.update({"latency_ms": round(random.uniform(300, 500), 2), "jitter_ms": round(random.uniform(100, 200), 2)})
        status = "Warning"

    # ==========================================
    # CATEGORY 3: L3 & TRAFFIC CONGESTION
    # ==========================================
    elif fault_type == "l3_hostel_congestion":
        device_id = "MAHANADI_UPLINK"
        metrics.update({"link_utilization_pct": 99.5, "queue_drops": random.randint(4000, 8000), "latency_ms": round(random.uniform(200, 400), 2)})
        status = "Critical"
    elif fault_type == "l3_erp_microburst":
        device_id = "ERP_SERVER_SW"
        metrics.update({"queue_drops": random.randint(15000, 25000), "link_utilization_pct": 98.0}) # CPU fine, buffers full
        status = "Critical"
    elif fault_type == "l3_bgp_flap":
        device_id = "NKN_GATEWAY_RTR"
        metrics.update({"packet_loss_pct": round(random.uniform(5, 15), 2), "latency_ms": round(random.uniform(400, 800), 2)})
        status = "Critical"
    elif fault_type == "l3_dataset_download":
        device_id = "AI_LAB_SW"
        metrics.update({"link_utilization_pct": 100.0, "latency_ms": round(random.uniform(100, 250), 2), "queue_drops": random.randint(500, 2000)})
        status = "Warning"
    elif fault_type == "l3_10g_1g_bottleneck":
        device_id = "CORE_TO_EDGE_1G"
        metrics.update({"queue_drops": random.randint(30000, 50000), "packet_loss_pct": round(random.uniform(10, 20), 2)})
        status = "Critical"
    elif fault_type == "l3_asymmetric_routing":
        device_id = "FW_CLUSTER_01"
        metrics.update({"jitter_ms": round(random.uniform(150, 300), 2), "packet_loss_pct": round(random.uniform(1, 3), 2)})
        status = "Warning"
    elif fault_type == "l3_qos_voip_drop":
        device_id = "DIRECTOR_OFFICE_SW"
        metrics.update({"jitter_ms": round(random.uniform(80, 150), 2), "queue_drops": random.randint(100, 500), "link_utilization_pct": 95.0})
        status = "Warning"
    elif fault_type == "l3_icmp_flood":
        device_id = "CYBERSEC_LAB_SW"
        metrics.update({"latency_ms": round(random.uniform(300, 600), 2), "cpu_utilization_pct": 80.0})
        status = "Warning"
    elif fault_type == "l3_tcam_full":
        device_id = "CORE_ROUTER_01"
        metrics.update({"cpu_utilization_pct": 100.0, "latency_ms": round(random.uniform(800, 1500), 2)})
        status = "Critical"
    elif fault_type == "l3_multicast_flood":
        device_id = "LHC_VIDEO_SW"
        metrics.update({"link_utilization_pct": 95.0, "queue_drops": random.randint(5000, 10000)})
        status = "Critical"

    # ==========================================
    # CATEGORY 4: WIRELESS & RF
    # ==========================================
    elif fault_type == "rf_rogue_ap":
        device_id = "SUBARNAREKHA_WIFI_22"
        metrics.update({"jitter_ms": round(random.uniform(100, 250), 2), "packet_loss_pct": round(random.uniform(5, 10), 2)})
        status = "Warning"
    elif fault_type == "rf_weak_signal":
        device_id = "HOSTEL_BASEMENT_AP"
        metrics.update({"packet_loss_pct": round(random.uniform(15, 30), 2), "latency_ms": round(random.uniform(200, 500), 2)})
        status = "Warning"
    elif fault_type == "rf_high_density_lhc":
        device_id = "LHC_AUDITORIUM_AP"
        metrics.update({"latency_ms": round(random.uniform(500, 900), 2), "queue_drops": random.randint(2000, 5000), "dhcp_pool_utilization_pct": 95.0})
        status = "Critical"
    elif fault_type == "rf_microwave_interf":
        device_id = "MESS_HALL_AP"
        metrics.update({"jitter_ms": round(random.uniform(200, 400), 2), "packet_loss_pct": round(random.uniform(10, 20), 2)})
        status = "Warning"
    elif fault_type == "rf_sticky_client":
        device_id = "LIBRARY_AP_02"
        metrics.update({"link_utilization_pct": round(random.uniform(80, 95), 2), "latency_ms": round(random.uniform(150, 300), 2)}) # low data rates consume airtime
        status = "Warning"
    elif fault_type == "rf_radius_timeout":
        device_id = "RADIUS_AUTH_SERVER"
        metrics.update({"latency_ms": round(random.uniform(1000, 2000), 2)})
        status = "Critical"
    elif fault_type == "rf_beacon_overhead":
        device_id = "SAC_WIFI_AP"
        metrics.update({"link_utilization_pct": 99.0, "queue_drops": random.randint(1000, 3000)})
        status = "Warning"
    elif fault_type == "rf_ap_memory_leak":
        device_id = "STAFF_QTRS_AP_14"
        metrics.update({"cpu_utilization_pct": 99.5, "latency_ms": round(random.uniform(300, 600), 2)})
        status = "Critical"
    elif fault_type == "rf_channel_overlap":
        device_id = "DEPT_CORRIDOR_AP"
        metrics.update({"packet_loss_pct": round(random.uniform(8, 15), 2), "jitter_ms": round(random.uniform(80, 150), 2)})
        status = "Warning"
    elif fault_type == "rf_controller_disconnect":
        device_id = "WIFI_CTRL_02"
        metrics.update({"link_utilization_pct": 0.0, "cpu_utilization_pct": 0.0, "queue_drops": 0})
        status = "Critical"

    # ==========================================
    # CATEGORY 5: L7 SERVICES & DHCP/DNS
    # ==========================================
    elif fault_type == "svc_dhcp_exhaust":
        device_id = "LIBRARY_DHCP_SCOPE"
        metrics.update({"dhcp_pool_utilization_pct": 100.0})
        status = "Critical"
    elif fault_type == "svc_dns_timeout":
        device_id = "INSTITUTE_DNS_01"
        metrics.update({"dns_latency_ms": round(random.uniform(2000, 5000), 2)})
        status = "Critical"
    elif fault_type == "svc_nat_exhaust":
        device_id = "EDGE_FIREWALL_01"
        metrics.update({"cpu_utilization_pct": 90.0, "packet_loss_pct": round(random.uniform(10, 25), 2)}) # Dropping new SYNs
        status = "Critical"
    elif fault_type == "svc_captive_portal":
        device_id = "GUEST_PORTAL_SVR"
        metrics.update({"dns_latency_ms": round(random.uniform(500, 1000), 2), "cpu_utilization_pct": 95.0})
        status = "Warning"

    # ==========================================
    # CATEGORY 6: EDGE CASES / MISSING DATA
    # ==========================================
    elif fault_type == "edge_missing_cpu":
        device_id = "LEGACY_SW_01"
        del metrics["cpu_utilization_pct"] # Pydantic/Sensors must handle this natively
        metrics.update({"queue_drops": 5000})
        status = "Warning"
    elif fault_type == "edge_inconsistent_data":
        device_id = "BUGGY_FIRMWARE_SW"
        metrics.update({"link_utilization_pct": None, "interface_errors": "NaN"}) 
        status = "Warning"
    elif fault_type == "edge_outdated_time":
        device_id = "NTP_SYNC_FAIL_SW"
        # Set timestamp 2 hours in the past
        timestamp = timestamp - timedelta(hours=2)
        metrics.update({"cpu_utilization_pct": 99.0})
        status = "Critical"
    elif fault_type == "compound_sfp_dhcp":
        device_id = "HOSTEL_CORE_SW"
        metrics.update({"interface_errors": 12000, "packet_loss_pct": 15.0, "dhcp_pool_utilization_pct": 98.0})
        status = "Critical"
    elif fault_type == "healthy_elevated":
        device_id = "ADMIN_DAY_TRAFFIC"
        metrics.update({"cpu_utilization_pct": 60.0, "link_utilization_pct": 75.0, "latency_ms": 30.0})
        status = "Healthy"

    # Final Compilation
    data = {
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "device_id": device_id,
        "metrics": metrics,
        "status": status
    }
    
    return data

# ==========================================
# USAGE EXAMPLE: GENERATING ALL 50 SCENARIOS
# ==========================================
if __name__ == "__main__":
    fault_types = [
        "healthy_baseline", "l1_cable_damage_lhc", "l1_fiber_bend_core", "l1_sfp_failure_ses",
        "l1_overheating_switch", "l1_speed_duplex", "l1_port_flap", "l1_dying_asic",
        "l1_cable_length", "l1_ups_dip", "l2_broadcast_storm", "l2_stp_loop", "l2_mac_flap",
        "l2_mtu_mismatch", "l2_vlan_mismatch", "l2_port_security", "l2_arp_storm",
        "l2_udld_err", "l2_storm_control", "l2_stp_recalc", "l3_hostel_congestion",
        "l3_erp_microburst", "l3_bgp_flap", "l3_dataset_download", "l3_10g_1g_bottleneck",
        "l3_asymmetric_routing", "l3_qos_voip_drop", "l3_icmp_flood", "l3_tcam_full",
        "l3_multicast_flood", "rf_rogue_ap", "rf_weak_signal", "rf_high_density_lhc",
        "rf_microwave_interf", "rf_sticky_client", "rf_radius_timeout", "rf_beacon_overhead",
        "rf_ap_memory_leak", "rf_channel_overlap", "rf_controller_disconnect",
        "svc_dhcp_exhaust", "svc_dns_timeout", "svc_nat_exhaust", "svc_captive_portal",
        "edge_missing_cpu", "edge_inconsistent_data", "edge_outdated_time",
        "compound_sfp_dhcp", "healthy_elevated", "healthy_baseline" # 50 total calls
    ]

    dataset = []
    for f_type in fault_types:
        payload = generate_telemetry(f_type)
        dataset.append({
            "scenario": f_type,
            "payload": payload
        })

    # Output to file or terminal
    with open("iit_bbs_benchmark_dataset.json", "w") as f:
        json.dump(dataset, f, indent=2)

    print(f"Successfully generated {len(dataset)} campus network scenarios.")
    print("Example Output (Compound L1 + L7 Fault):")
    print(json.dumps(generate_telemetry("compound_sfp_dhcp"), indent=2))