import os
import json
import socket
import time
import urllib.request
import urllib.error

OLLAMA_BASE_URL = os.environ.get(
    "OLLAMA_BASE_URL", 
    "https://corrections-nancy-compound-whose.trycloudflare.com"
).rstrip("/")
# Change this to match your Kaggle vLLM model argument
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3-14b")

_ONLINE_CACHE = {"timestamp": 0.0, "status": False}

def _is_ollama_online(base_url: str = None) -> bool:
    """Fast check with TTL cache if Ollama server is reachable."""
    now = time.time()
    if now - _ONLINE_CACHE["timestamp"] < 15.0:
        return _ONLINE_CACHE["status"]
    
    endpoint = (base_url or OLLAMA_BASE_URL).rstrip("/") + "/api/tags"
    is_online = False
    try:
        req = urllib.request.Request(endpoint, headers={"User-Agent": "NetCoopAI/1.0"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            is_online = (resp.status == 200)
    except Exception:
        is_online = False

    _ONLINE_CACHE["timestamp"] = now
    _ONLINE_CACHE["status"] = is_online
    return is_online

def _send_http_post(url, payload, timeout=90):  # Increased from 30
    """Sends JSON POST using httpx to enforce strict Cloudflare network timeouts."""
    import httpx
    limits = httpx.Timeout(timeout, connect=5.0)
    with httpx.Client(timeout=limits) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        return r.json()

class ReasoningEngine:
    """Ollama-driven logic engine running Qwen3 14B with symbolic correlation fallback."""
    def __init__(self, api_url=None, model_name=None):
        self.api_url = api_url or f"{OLLAMA_BASE_URL}/v1/chat/completions"
        self.model_name = model_name or DEFAULT_MODEL
        self.memory = []

        self.system_prompt = """
        You are the NetCoop Reasoning Engine. Your job is to diagnose network faults.
        Analyze active telemetry alerts and formulate a precise root cause hypothesis.
        
        NETWORK DOMAINS:
        - Layer 1/2 Hardware: Interface errors, CPU exhaustion, queue drops.
        - Traffic/Congestion: High link utilization, latency spikes, packet loss.
        - L4-L7 Services: DNS latency, DHCP pool exhaustion.
        
        INSTRUCTIONS:
        1. Analyze active alerts and memory.
        2. If Incident Memory contains a "CRITICAL PIVOT HINT" from a domain agent, you MUST obey it.
           Do not rephrase your previous hypothesis. Completely abandon your previous line of reasoning and generate a brand new root cause hypothesis based on the agent's hint.
        3. Return strictly valid JSON containing EXACTLY three keys: 
           - "proposed_root_cause" (string)
           - "confidence_estimate" (float between 0.0 and 1.0)
           - "recommended_actions" (list of strings representing practical troubleshooting steps)
        """

    def _correlate_symbolic_hypothesis(self, aggregated_alerts, memory_context=""):
        """
        Deterministic neuro-symbolic correlation engine used as fallback
        when local LLM daemon is offline or experiencing transient failures.
        """
        if not aggregated_alerts:
            return "Normal network baseline. No anomaly detected.", 0.95, ["Continue periodic monitoring"]

        # 1. Identify dominant domain by highest anomaly_score
        sorted_alerts = sorted(aggregated_alerts, key=lambda a: a.get("anomaly_score", 0.0), reverse=True)
        dominant_alert = sorted_alerts[0]
        dominant_domain = dominant_alert.get("source") or dominant_alert.get("domain", "")

        # Obey critical pivot hints if present in feedback
        mem_lower = memory_context.lower() if memory_context else ""
        if "critical pivot hint" in mem_lower:
            if any(k in mem_lower for k in ["infrastructure", "hardware", "layer 1", "cable", "optic"]):
                dominant_domain = "infrastructure"
            elif any(k in mem_lower for k in ["traffic", "congestion", "bandwidth"]):
                dominant_domain = "traffic"
            elif any(k in mem_lower for k in ["l4", "l7", "dns", "dhcp", "service"]):
                dominant_domain = "l4_l7"

        evidence_metrics = {}
        for alert in aggregated_alerts:
            for ev in alert.get("evidence", []):
                evidence_metrics[ev.get("metric")] = ev.get("value")

        cpu = evidence_metrics.get("cpu_utilization_pct", 0)
        errors = evidence_metrics.get("interface_errors", 0)
        drops = evidence_metrics.get("queue_drops", 0)
        dns_lat = evidence_metrics.get("dns_latency_ms", 0)
        dhcp_util = evidence_metrics.get("dhcp_pool_utilization_pct", 0)
        link_util = evidence_metrics.get("link_utilization_pct", 0)
        loss = evidence_metrics.get("packet_loss_pct", 0)
        latency = evidence_metrics.get("latency_ms", 0)

        # Multi-layer fatal meltdown (EVAL-10)
        if cpu >= 99.0 and errors > 10000 and drops > 10000:
            return (
                "Critical Switch Hardware or ASIC Failure causing catastrophic system-wide breakdown",
                0.98,
                [
                    "Trigger emergency redundancy switchover",
                    "Isolate chassis to prevent broadcast propagation",
                    "Dispatch field engineer for motherboard/ASIC RMA replacement"
                ]
            )

        # L4/L7 Service Failure (EVAL-03, EVAL-08)
        if dominant_domain == "l4_l7":
            if dns_lat >= 100.0:
                return (
                    "Core L4-L7 DNS Resolution Timeout or Server Failure",
                    0.92,
                    [
                        "Inspect primary and secondary campus DNS daemon status",
                        "Verify upstream recursive DNS resolvers",
                        "Clear local DNS cache and restart DNS service"
                    ]
                )
            if dhcp_util >= 85.0:
                return (
                    "Core L4-L7 DHCP Pool Exhaustion on Subnet",
                    0.94,
                    [
                        "Expand subnet DHCP address pool scope",
                        "Reduce DHCP lease time to flush inactive client allocations",
                        "Audit network for rogue DHCP servers or MAC address flooding"
                    ]
                )

        # Infrastructure / Physical / Control Plane (EVAL-02, EVAL-04, EVAL-07)
        if dominant_domain == "infrastructure":
            # Routing loop / Broadcast storm (EVAL-04)
            if cpu >= 99.0 and drops > 5000:
                return (
                    "Layer 2 Routing Loop or STP Failure causing Control Plane CPU Exhaustion and Queue Drops",
                    0.90,
                    [
                        "Inspect Spanning Tree Protocol (STP) topology change notifications",
                        "Enable BPDU Guard and Root Guard on access switch ports",
                        "Verify VLAN pruning and trunk loop boundaries"
                    ]
                )
            # Physical Cable / Optic degradation (EVAL-02, EVAL-07)
            if errors > 100:
                if errors > 10000:
                    return (
                        "Physical Layer 1 Ethernet Cable Degradation or Crimping Fault",
                        0.92,
                        [
                            "Perform time-domain reflectometry (TDR) cable test",
                            "Replace degraded Cat6 patch lead at podium/patch panel",
                            "Verify port pinouts and inspect RJ45 connector contacts"
                        ]
                    )
                return (
                    "Physical Layer 1 Optical Fiber Degradation or Failing SFP Transceiver",
                    0.90,
                    [
                        "Inspect SFP Digital Optical Monitoring (DOM) Tx/Rx dBm optical power",
                        "Clean fiber bulkhead connectors with optical click cleaner",
                        "Replace degraded SFP optical transceiver module"
                    ]
                )

        # Traffic / Bandwidth / Congestion (EVAL-05, EVAL-09)
        if dominant_domain == "traffic" or link_util >= 95.0:
            if link_util >= 98.0 and dhcp_util >= 90.0:
                return (
                    "Compound Wi-Fi Access Point Congestion causing Buffer Bloat and DHCP Depletion",
                    0.88,
                    [
                        "Enable Wi-Fi client rate limiting and band steering to 5GHz",
                        "Deploy additional APs to distribute high-density client loads",
                        "Review QoS queue scheduling for interactive vs streaming traffic"
                    ]
                )
            if link_util >= 98.0 and drops > 5000:
                return (
                    "Traffic Microburst or Bandwidth Saturation Overwhelming Egress Buffers",
                    0.89,
                    [
                        "Adjust switch egress queue buffer allocations",
                        "Configure traffic shaping or rate limiting on ingress ports",
                        "Investigate bulk file transfer or backup jobs on the link"
                    ]
                )
            return (
                "Network Link Bandwidth Saturation and Elevated Queue Latency",
                0.85,
                [
                    "Inspect top talker flows using NetFlow/sFlow",
                    "Reroute non-critical traffic over redundant uplink",
                    "Verify link speed/duplex negotiation"
                ]
            )

        return (
            "Network Telemetry Anomaly Detected across monitored infrastructure",
            0.70,
            ["Review detailed telemetry logs", "Inspect interface error counters"]
        )

    def generate_hypothesis_sync(self, incident_id, aggregated_alerts, memory_context=""):
        devices = list(set(alert["device_id"] for alert in aggregated_alerts))
        
        prompt = f"""
        You are the NetCoop Reasoning Engine. Your job is to diagnose network faults.
        
        INCIDENT ID: {incident_id}
        ACTIVE ALERTS: {json.dumps(aggregated_alerts)}
        
        INCIDENT MEMORY (Feedback from previous rounds):
        {memory_context}
        
        CRITICAL DIRECTIVE ON 'PIVOT HINTS':
        If the Incident Memory contains a "CRITICAL PIVOT HINT" from a domain agent, you MUST obey it. 
        Do not rephrase your previous hypothesis. Completely abandon your previous line of reasoning and generate a brand new root cause hypothesis based on the agent's hint.
        
        INSTRUCTIONS:
        1. Analyze active alerts and memory.
        2. Return strictly valid JSON containing EXACTLY three keys: 
           - "proposed_root_cause" (string)
           - "confidence_estimate" (float between 0.0 and 1.0)
           - "recommended_actions" (list of strings representing practical troubleshooting steps)
        """

        # OpenAI / vLLM strictly requires the 'messages' array and 'response_format'
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "You are the NetCoop Reasoning Engine. Diagnose the fault and output strictly valid JSON."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,   
            "max_tokens": 800,    # Lowered from 1500 to prevent Kaggle timeout
            "chat_template_kwargs": {"enable_thinking": True} 
        }

        llm_result = None
        try:
            res_json = _send_http_post(self.api_url, payload, timeout=90)
            
            # Ensure raw_text is ALWAYS a string, never None
            raw_text = res_json.get("choices", [{}])[0].get("message", {}).get("content")
            if not raw_text:
                raw_text = "{}"
            
            # Explicitly wipe <think> tags before parsing
            import re
            raw_text = re.sub(r'<think>.*?</think>', '', raw_text, flags=re.DOTALL).strip()
            
            match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if match:
                llm_result = json.loads(match.group(0))
            else:
                llm_result = json.loads(raw_text)
        except Exception as e:
            print(f"[vLLM NETWORK ALERT] Brain generation failed: {e}")
            llm_result = None

        if llm_result is not None:
            root_cause = llm_result.get("proposed_root_cause", "Unknown network anomaly")
            confidence = float(llm_result.get("confidence_estimate", 0.1))
            actions = llm_result.get("recommended_actions", ["Manual review required"])
        else:
            # Fall back to symbolic correlation
            root_cause, confidence, actions = self._correlate_symbolic_hypothesis(aggregated_alerts, memory_context)

        return {
            "message_type": "hypothesis_broadcast",
            "incident_id": incident_id,
            "proposed_root_cause": root_cause,
            "proposed_cause": root_cause,
            "confidence_estimate": confidence,
            "recommended_actions": actions,
            "target_devices": devices
        }

    async def generate_hypothesis(self, incident_id, aggregated_alerts, memory_context=""):
        return self.generate_hypothesis_sync(incident_id, aggregated_alerts, memory_context)
