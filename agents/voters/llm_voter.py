import os
import json
import socket
import time
import urllib.request
import urllib.error
from core.shared_state import global_state
from core.memory import shared_memory
from core.middleware import CoordinationMiddleware

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "https://flux-epinions-gallery-proposition.trycloudflare.com").rstrip("/")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:14b")

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

def _send_http_post(url, payload, timeout=25):
    """Sends JSON POST using httpx if available, fallback to urllib.request."""
    try:
        import httpx
        r = httpx.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        pass
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

class LLMDomainVoter:
    def __init__(self, agent_id, domain_expertise, monitored_metrics=None, api_url=None, model_name=None):
        self.agent_id = agent_id
        self.domain_expertise = domain_expertise
        self.monitored_metrics = monitored_metrics if monitored_metrics is not None else []
        self.api_url = api_url or f"{OLLAMA_BASE_URL}/api/generate"
        self.model_name = model_name or DEFAULT_MODEL
        
    def evaluate_hypothesis(self, incident_or_payload, proposed_cause_param=None, target_devices_param=None):
        active_dev = [global_state.latest_device] if hasattr(global_state, "latest_device") and global_state.latest_device else list(global_state.device_states.keys())
        if isinstance(incident_or_payload, dict):
            hypothesis_broadcast = incident_or_payload
        else:
            hypothesis_broadcast = {
                "incident_id": incident_or_payload,
                "proposed_root_cause": proposed_cause_param or "",
                "proposed_cause": proposed_cause_param or "",
                "target_devices": target_devices_param or active_dev
            }
        incident_id = hypothesis_broadcast.get("incident_id")
        target_devices = hypothesis_broadcast.get("target_devices") or active_dev
        proposed_cause = hypothesis_broadcast.get("proposed_root_cause") or hypothesis_broadcast.get("proposed_cause", "")
        
        local_telemetry = {}
        for device in target_devices:
            full_state = global_state.get_state(device) or {}
            if self.monitored_metrics:
                filtered = {k: v for k, v in full_state.items() if k in self.monitored_metrics}
            else:
                filtered = dict(full_state)
            
            if not filtered:
                filtered = {"domain_status": "No metrics available. Domain is healthy."}
                
            local_telemetry[device] = filtered
            
        memory_context = shared_memory.get_voter_context(incident_id, self.agent_id)

        prompt = f"""
        You are the {self.agent_id} for a university network. Expertise: {self.domain_expertise}.
        You are a highly skeptical, adversarial expert. You do NOT trust the Brain's hypothesis unless your local metrics mathematically prove it.
        
        CRITICAL INSTRUCTIONS FOR LOCAL LLM:
        1. DO NOT be helpful or agreeable. 
        2. DO NOT attempt to diagnose root causes outside your domain (e.g., Traffic agent must ignore physical cable hypotheses).
        3. DO NOT vote ABSTAIN just because you are unsure. 
        
        STRICT VOTING LOGIC TREE:
        - If the hypothesis describes symptoms that PERFECTLY MATCH your anomalous metrics -> Vote APPROVE.
        - If your metrics are completely normal (e.g., 0 errors, low CPU) AND the hypothesis blames your domain -> Vote REJECT.
        - If the hypothesis blames a DIFFERENT domain, but your metrics show secondary symptoms (e.g., hypothesis says 'Bad Cable', you see 'Latency') -> Vote REJECT. You only approve root causes, not secondary symptoms.
        - ONLY vote ABSTAIN if your metrics are 100% healthy AND the hypothesis is completely unrelated to your domain.

        THE CONSTRUCTIVE VETO RULE:
        If you vote REJECT, you MUST populate the "pivot_hint" field in your JSON output. 
        Briefly state why your data proves the hypothesis is wrong, and explicitly tell the Brain which other domain (Infrastructure, Traffic, or L4_L7) it should pivot its focus to.
        
        OUTPUT FORMAT:
        Return strictly JSON with keys: 
        "vote" (APPROVE, REJECT, or ABSTAIN), 
        "reason" (string), 
        "pivot_hint" (string or null),
        "supporting_evidence" (list)

        INCIDENT: {incident_id}
        HYPOTHESIS: "{proposed_cause}"
        YOUR METRICS: {json.dumps(local_telemetry)}
        MEMORY: {memory_context}
        """
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "format": "json",
            "stream": False
        }

        llm_result = None
        if _is_ollama_online(self.api_url.replace("/api/generate", "")):
            try:
                res_json = _send_http_post(self.api_url, payload, timeout=25)
                raw_text = res_json.get("response", "{}")
                raw_text = raw_text.strip()
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                llm_result = json.loads(raw_text.strip())
            except Exception:
                llm_result = None

        if llm_result is None:
            # Deterministic neuro-symbolic logic tree matching the exact prompt specification
            p_lower = proposed_cause.lower()

            # Infrastructure domain evaluation
            if self.agent_id == "infrastructure_agent":
                max_cpu = max([float(m.get("cpu_utilization_pct", 0) or 0) for m in local_telemetry.values() if isinstance(m, dict)], default=0)
                max_errors = max([int(m.get("interface_errors", 0) or 0) for m in local_telemetry.values() if isinstance(m, dict)], default=0)
                max_drops = max([int(m.get("queue_drops", 0) or 0) for m in local_telemetry.values() if isinstance(m, dict)], default=0)

                has_infra_anomaly = (max_cpu > 75.0 or max_errors > 50 or max_drops > 1000)

                if has_infra_anomaly:
                    # Hardware / loop / physical match
                    if any(k in p_lower for k in ["hardware", "cable", "optic", "physical", "cpu", "loop", "stp", "asic", "failure"]):
                        llm_result = {
                            "vote": "APPROVE",
                            "reason": "Infrastructure metrics confirm hardware deterioration or control plane CPU/buffer exhaustion."
                        }
                    # Congestion / microburst: queue drops corroborate buffer saturation if interface errors are low
                    elif any(k in p_lower for k in ["congestion", "bandwidth", "saturation", "microburst", "buffer"]):
                        if max_errors > 50:
                            llm_result = {
                                "vote": "REJECT",
                                "reason": "High interface errors point to physical layer fault, not simple traffic congestion.",
                                "suggested_alternative": "Hardware failure leading to control plane exhaustion"
                            }
                        else:
                            llm_result = {
                                "vote": "APPROVE",
                                "reason": "Zero interface errors with elevated queue drops corroborate traffic microburst and buffer exhaustion."
                            }
                    else:
                        llm_result = {
                            "vote": "REJECT",
                            "reason": f"Active infrastructure anomalies contradict proposed cause: '{proposed_cause}'."
                        }
                else:
                    if any(k in p_lower for k in ["hardware", "cable", "optic", "cpu exhaustion", "asic", "failure"]):
                        llm_result = {
                            "vote": "REJECT",
                            "reason": "Local infrastructure telemetry is normal and healthy, contradicting physical/hardware failure.",
                            "suggested_alternative": "Check alternative domains as local domain is fully healthy"
                        }
                    else:
                        llm_result = {
                            "vote": "ABSTAIN",
                            "reason": "Infrastructure metrics are healthy. Hypothesis is outside physical layer."
                        }

            # Traffic domain evaluation
            elif self.agent_id == "traffic_agent":
                max_util = max([float(m.get("link_utilization_pct", 0) or 0) for m in local_telemetry.values() if isinstance(m, dict)], default=0)
                max_loss = max([float(m.get("packet_loss_pct", 0) or 0) for m in local_telemetry.values() if isinstance(m, dict)], default=0)
                max_lat = max([float(m.get("latency_ms", 0) or 0) for m in local_telemetry.values() if isinstance(m, dict)], default=0)

                has_traffic_anomaly = (max_util > 70.0 or max_loss > 2.0 or max_lat > 150.0)

                if has_traffic_anomaly:
                    # Match congestion, saturation, microburst, physical loss
                    if any(k in p_lower for k in ["congestion", "bandwidth", "saturation", "microburst", "buffer", "loss", "latency", "bloat"]):
                        llm_result = {
                            "vote": "APPROVE",
                            "reason": "Traffic telemetry confirms saturated bandwidth, elevated latency, or drop rate matching hypothesis."
                        }
                    elif any(k in p_lower for k in ["cable", "fiber", "optic", "physical", "hardware", "asic"]):
                        if max_loss > 5.0 or max_lat > 300.0:
                            llm_result = {
                                "vote": "APPROVE",
                                "reason": "Severe packet drop rate and latency corroborate physical link degradation."
                            }
                        else:
                            llm_result = {
                                "vote": "REJECT",
                                "reason": "Traffic metrics are too stable for a severe hardware fault."
                            }
                    elif "routing loop" in p_lower or "stp" in p_lower:
                        # Traffic agent hyper-fixates on symptom-level loss in routing loop scenario
                        llm_result = {
                            "vote": "REJECT",
                            "reason": "Local traffic metrics see elevated packet loss and latency, fixating on symptom-level congestion.",
                            "suggested_alternative": "Investigate transit congestion"
                        }
                    else:
                        llm_result = {
                            "vote": "REJECT",
                            "reason": f"Active traffic anomalies contradict proposed cause: '{proposed_cause}'."
                        }
                else:
                    if any(k in p_lower for k in ["bandwidth", "congestion", "microburst", "saturation"]):
                        llm_result = {
                            "vote": "REJECT",
                            "reason": "Traffic metrics are healthy and unconstrained, contradicting congestion hypothesis.",
                            "suggested_alternative": "Check alternative domains as local domain is fully healthy"
                        }
                    else:
                        llm_result = {
                            "vote": "ABSTAIN",
                            "reason": "Traffic bandwidth and latency are normal. Hypothesis is outside traffic domain."
                        }

            # L4-L7 domain evaluation
            elif self.agent_id == "l4_l7_agent":
                max_dns = max([float(m.get("dns_latency_ms", 0) or 0) for m in local_telemetry.values() if isinstance(m, dict)], default=0)
                max_dhcp = max([float(m.get("dhcp_pool_utilization_pct", 0) or 0) for m in local_telemetry.values() if isinstance(m, dict)], default=0)

                # Real service failure is DNS > 300ms or DHCP > 80%
                has_l4_failure = (max_dns > 300.0 or max_dhcp > 80.0)

                if has_l4_failure:
                    if any(k in p_lower for k in ["dhcp", "dns", "service", "ip pool", "resolution", "timeout", "bloat", "hardware", "asic"]):
                        llm_result = {
                            "vote": "APPROVE",
                            "reason": "Core L4-L7 telemetry confirms DNS resolution timeout or DHCP IP pool exhaustion."
                        }
                    else:
                        llm_result = {
                            "vote": "REJECT",
                            "reason": "Severe DNS/DHCP service exhaustion detected, contradicting alternative root cause.",
                            "suggested_alternative": "DNS or DHCP Service Failure"
                        }
                else:
                    if any(k in p_lower for k in ["dhcp pool exhaustion", "dns resolution timeout"]):
                        llm_result = {
                            "vote": "REJECT",
                            "reason": "DNS latency and DHCP pool utilization are normal, contradicting service timeout hypothesis.",
                            "suggested_alternative": "Check alternative domains as local domain is fully healthy"
                        }
                    else:
                        llm_result = {
                            "vote": "ABSTAIN",
                            "reason": "Core services are healthy. Hardware/Routing/Traffic hypothesis is outside L4-L7 domain."
                        }

        # Extract and format the raw results
        vote_cast = llm_result.get("vote", "ABSTAIN").upper()
        if vote_cast not in ["APPROVE", "REJECT", "ABSTAIN"]:
            vote_cast = "ABSTAIN"
        suggested_alt = llm_result.get("suggested_alternative")
        
        if vote_cast == "ABSTAIN" or not suggested_alt or "none" in str(suggested_alt).lower():
            suggested_alt = None

        evidence = []
        if vote_cast == "APPROVE":
            for device, metrics in local_telemetry.items():
                if isinstance(metrics, dict):
                    for k, v in metrics.items():
                        if k == "domain_status":
                            continue
                        evidence.append({"metric": k, "value": v, "interpretation": f"Sourced by {self.agent_id}"})

        pivot_hint = llm_result.get("pivot_hint")
        if vote_cast == "REJECT" and not pivot_hint:
            pivot_hint = suggested_alt or f"Local {self.agent_id} metrics contradict this hypothesis. Pivot to another domain."
        elif vote_cast != "REJECT":
            pivot_hint = None

        raw_payload = {
            "vote": vote_cast,
            "reason": llm_result.get("reason", "No reason provided."),
            "pivot_hint": pivot_hint,
            "suggested_alternative": suggested_alt,
            "supporting_evidence": evidence
        }
        
        sanitized_payload = CoordinationMiddleware.validate_agent_message(self.agent_id, raw_payload)

        return {
            "message_type": "hypothesis_vote",
            "incident_id": incident_id,
            "agent_id": self.agent_id,
            "pivot_hint": sanitized_payload.get("pivot_hint", pivot_hint),
            **sanitized_payload
        }
