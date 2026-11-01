import os
import json
import socket
import time
import urllib.request
import urllib.error
from core.shared_state import global_state
from core.memory import shared_memory
from core.middleware import CoordinationMiddleware
from core.config import settings

OLLAMA_BASE_URL = settings.ENGINE_URL



# Change this to match your Kaggle vLLM model argument
DEFAULT_MODEL = settings.OLLAMA_MODEL

_ONLINE_CACHE = {"timestamp": 0.0, "status": False}

def _is_ollama_online(base_url: str = None) -> bool:
    """Fast check with TTL cache if Ollama server is reachable."""
    now = time.time()
    if now - _ONLINE_CACHE["timestamp"] < 30.0:
        return _ONLINE_CACHE["status"]

    url = (base_url or OLLAMA_BASE_URL).rstrip("/")
    if url.endswith("/v1/chat/completions"):
        url = url.replace("/v1/chat/completions", "")
    elif url.endswith("/api/generate"):
        url = url.replace("/api/generate", "")

    is_online = False
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        sock = socket.create_connection((host, port), timeout=0.5)
        sock.close()

        req = urllib.request.Request(f"{url}/api/tags", headers={"User-Agent": "NetCoopAI/1.0"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            is_online = (resp.status == 200)
    except Exception:
        is_online = False

    _ONLINE_CACHE["timestamp"] = now
    _ONLINE_CACHE["status"] = is_online
    return is_online

def _send_http_post(url, payload, timeout=None):
    timeout = timeout or settings.VOTER_TIMEOUT_SECONDS
    """Sends JSON POST using httpx to enforce strict Cloudflare network timeouts."""
    import httpx
    # 5 seconds to connect to Cloudflare, 30 seconds total for GPU to generate
    limits = httpx.Timeout(timeout, connect=5.0)
    with httpx.Client(timeout=limits) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        return r.json()

class LLMDomainVoter:
    def __init__(self, agent_id, domain_expertise, monitored_metrics=None, api_url=None, model_name=None):
        self.agent_id = agent_id
        self.domain_expertise = domain_expertise
        self.monitored_metrics = monitored_metrics if monitored_metrics is not None else []
        self.api_url = api_url or f"{OLLAMA_BASE_URL}/v1/chat/completions"
        self.model_name = model_name or DEFAULT_MODEL

    # STEP 2: Added anomaly_score to signature for Context-Aware Prompting
    def evaluate_hypothesis(self, incident_or_payload, proposed_cause_param=None, target_devices_param=None, anomaly_score: float = 0.0):
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

        # ==========================================
        # STEP 2: CONTEXT-AWARE PROMPT ARCHITECTURE
        # ==========================================
        is_bleeding = anomaly_score > 0.0
        
        if is_bleeding:
            state_directive = """
            YOUR STATE: BLEEDING (Anomaly Detected)
            Your metrics show active issues. Check if the Brain's hypothesis correctly identifies the root cause of YOUR specific broken metrics.
            - If it does, populate 'supporting_evidence' with the specific metric names and values.
            - CRITICAL: Do NOT populate 'contradicting_evidence' just because some of your *other* metrics are normal. (e.g., A normal CPU during a physical cable fault is expected, not a contradiction).
            - ONLY populate 'contradicting_evidence' if the Brain explicitly claims a specific metric is broken, but your telemetry shows it is perfectly healthy.
            - If the Brain correctly diagnoses a DIFFERENT domain and your metrics are just secondary symptoms, return empty arrays.
            - CRITICAL: If the Brain's hypothesis is vague, generic, or states "Unknown network anomaly", you MUST return completely empty arrays for both supporting and contradicting evidence. Do not attempt to support an unknown cause.
            """
        else:
            state_directive = """
            YOUR STATE: HEALTHY (No Anomalies)
            Your metrics are 100% normal. Your ONLY job is Falsification.
            - CRITICAL: You MUST NEVER populate 'supporting_evidence'. Healthy metrics cannot support a failure hypothesis. Leave it empty [].
            - ONLY populate 'contradicting_evidence' if the Brain explicitly claims a specific metric in YOUR domain is broken, but your telemetry shows it is perfectly healthy.
            - Do NOT contradict the Brain over generic phrasing (e.g., if the Brain says "traffic issues" but blames a hardware switch, ignore it). 
            - If the Brain's hypothesis is correctly localized to a different domain, or if the Brain says "Unknown network anomaly", return completely empty arrays for both fields.
            """

        prompt = f"""
        You are the {self.agent_id} for a university network. Expertise: {self.domain_expertise}.
        
        {state_directive}

        CRITICAL: Output ONLY valid JSON. Do not output <think> tags, do not explain your steps, and do not include markdown formatting outside the JSON block.

        OUTPUT FORMAT (Strict JSON):
        {{
            "supporting_evidence": ["metric A confirms X", "metric B confirms Y"],
            "contradicting_evidence": [] 
        }}
        NOTE: If there is no evidence for a category, you MUST return a literal empty array []. Do not output ["none"] or ["empty"].

        INCIDENT: {incident_id}
        HYPOTHESIS: "{proposed_cause}"
        YOUR METRICS: {json.dumps(local_telemetry)}
        """

        # OpenAI / vLLM strictly requires the 'messages' array and 'response_format'
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "You are a deterministic logic agent. Output strictly valid JSON."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
            "max_tokens": 300,
            "chat_template_kwargs": {"enable_thinking": False}  # Voter thinking disabled
        }

        llm_result = None
        if _is_ollama_online(self.api_url):
            try:
                res_json = _send_http_post(self.api_url, payload, timeout=30)
                raw_text = res_json.get("choices", [{}])[0].get("message", {}).get("content", "{}")

                # Robust JSON Extractor: Strips any markdown or stray text
                import re
                match = re.search(r'\{.*\}', raw_text, re.DOTALL)
                if match:
                    llm_result = json.loads(match.group(0))
                else:
                    llm_result = json.loads(raw_text)
            except Exception as e:
                print(f"[vLLM NETWORK ALERT] Voter generation failed: {e}")
                llm_result = None

        if llm_result is None:
            p_lower = proposed_cause.lower()
            if is_bleeding:
                is_cascading = any(k in p_lower for k in ["hardware", "asic", "catastrophic", "switch", "chassis"])
                domain_matches = False
                if self.agent_id == "infrastructure_agent" and any(k in p_lower for k in ["cable", "optic", "fiber", "hardware", "cpu", "stp", "loop", "routing loop", "layer 1", "buffer", "chassis"]):
                    domain_matches = True
                elif self.agent_id == "traffic_agent" and any(k in p_lower for k in ["bandwidth", "congestion", "microburst", "saturation", "latency", "packet loss", "transit", "wi-fi", "wifi", "cable", "optic", "fiber", "physical", "layer 1", "crimp"]):
                    domain_matches = True
                elif self.agent_id == "l4_l7_agent" and any(k in p_lower for k in ["dhcp", "dns", "service", "pool", "exhaustion", "timeout", "wi-fi", "wifi", "hardware", "asic"]):
                    domain_matches = True
                
                if domain_matches or is_cascading:
                    supp = []
                    for dev, metrics in local_telemetry.items():
                        if isinstance(metrics, dict):
                            for k, v in metrics.items():
                                if k != "domain_status":
                                    supp.append(f"{k} ({v}) confirms anomaly")
                    llm_result = {"supporting_evidence": supp, "contradicting_evidence": []}
                else:
                    llm_result = {"supporting_evidence": [], "contradicting_evidence": [f"{self.agent_id} anomaly contradicts proposed cause"]}
            else:
                contradicts = False
                if self.agent_id == "infrastructure_agent" and any(k in p_lower for k in ["hardware failure", "cable degradation", "optic"]):
                    contradicts = True
                elif self.agent_id == "traffic_agent" and any(k in p_lower for k in ["traffic microburst", "bandwidth saturation"]):
                    contradicts = True
                elif self.agent_id == "l4_l7_agent" and any(k in p_lower for k in ["dhcp pool exhaustion", "dns resolution timeout"]):
                    contradicts = True
                
                if contradicts:
                    llm_result = {"supporting_evidence": [], "contradicting_evidence": [f"{self.agent_id} metrics are completely healthy, contradicting hypothesis"]}
                else:
                    llm_result = {"supporting_evidence": [], "contradicting_evidence": []}

        # Extract Evidence Arrays
        # Extract Evidence Arrays
        supporting_raw = llm_result.get("supporting_evidence", [])
        contradicting_raw = llm_result.get("contradicting_evidence", [])
        
        # SANITIZER: Scrub literal LLM hallucinations like "none", "empty", etc.
        def clean_array(arr):
            if not isinstance(arr, list): return []
            bad_words = ["", "none", "n/a", "null", "empty", "empty list", "or empty list"]
            return [x for x in arr if isinstance(x, str) and x.strip().lower() not in bad_words]

        supporting_strings = clean_array(supporting_raw)
        contradicting = clean_array(contradicting_raw)
        
        # Debug print so we can actually see the LLM's brain!
        print(f"    [{self.agent_id}] Supp: {supporting_strings} | Contra: {contradicting}")
        
        # FIX: Middleware requires a List of Dictionaries, but LLM outputs Strings.
        supporting = [{"evidence_extracted": item} for item in supporting_strings]
        
        # Temporary compatibility bridge for CoordinationMiddleware until Step 3
        mapped_vote = "ABSTAIN"
        pivot_hint = None
        suggested_alt = None
        if len(contradicting) > 0:
            mapped_vote = "REJECT"
            pivot_hint = f"Metrics in {self.agent_id} contradict '{proposed_cause}'. Pivot investigation to alternative domain."
            suggested_alt = pivot_hint
        elif len(supporting) > 0:
            mapped_vote = "APPROVE"
        
        raw_payload = {
            "vote": mapped_vote,
            "reason": "Evaluated via Context-Aware Evidence Engine",
            "pivot_hint": pivot_hint,
            "suggested_alternative": suggested_alt,
            "supporting_evidence": supporting
        }

        # Validate through middleware
        sanitized_payload = CoordinationMiddleware.validate_agent_message(self.agent_id, raw_payload)

        # Inject contradicting_evidence (not in middleware schema yet) so iterator can use it
        sanitized_payload["contradicting_evidence"] = contradicting

        return {
            "message_type": "hypothesis_vote",
            "incident_id": incident_id,
            "agent_id": self.agent_id,
            **sanitized_payload
        }