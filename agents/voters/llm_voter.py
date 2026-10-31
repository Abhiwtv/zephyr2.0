import os
import json
from google import genai
from google.genai import types
from core.shared_state import global_state
from core.memory import shared_memory
from core.middleware import CoordinationMiddleware
import json
import requests
from core.shared_state import global_state
from core.memory import shared_memory

class LLMDomainVoter:
    def __init__(self, agent_id, domain_expertise, monitored_metrics):
        self.agent_id = agent_id
        self.domain_expertise = domain_expertise
        self.monitored_metrics = monitored_metrics
        self.api_url = "http://localhost:11434/api/generate"
        self.model_name = "qwen2.5:7b-instruct"
        
    def evaluate_hypothesis(self, hypothesis_broadcast):
        incident_id = hypothesis_broadcast.get("incident_id")
        target_devices = hypothesis_broadcast.get("target_devices", [])
        proposed_cause = hypothesis_broadcast.get("proposed_root_cause")
        
        local_telemetry = {}
        for device in target_devices:
            full_state = global_state.get_state(device) or {}
            filtered = {k: v for k, v in full_state.items() if k in self.monitored_metrics}
            
            # THE FIX: Don't pass empty {} to Qwen. Tell it explicitly.
            if not filtered:
                filtered = {"domain_status": "No metrics available. Domain is healthy."}
                
            local_telemetry[device] = filtered
            
        memory_context = shared_memory.get_voter_context(incident_id, self.agent_id)

        prompt = f"""
        You are the {self.agent_id} for a university network. Expertise: {self.domain_expertise}.
        Evaluate the Brain's hypothesis STRICTLY through your own metrics.
        
        CRITICAL INSTRUCTIONS FOR LOCAL LLM:
        You must ignore the "root cause" of the hypothesis (e.g., "bad cable", "routing loop", "CPU failure"). That is not your job.
        Your ONLY job is to check if your metrics match the SYMPTOMS (the effects) described.

        VOTING LOGIC TREE:
        1. If the hypothesis describes symptoms (e.g., latency, packet loss, queue drops) that MATCH your anomalous metrics -> Vote APPROVE.
        2. If your metrics are completely normal/healthy, OR the hypothesis discusses things totally outside your domain -> Vote ABSTAIN.
        3. If your metrics explicitly PROVE the hypothesis is mathematically impossible -> Vote REJECT.
        
        OUTPUT FORMAT:
        Return strictly JSON with keys: 
        "vote" (string: APPROVE, REJECT, or ABSTAIN), 
        "reason" (string), 
        "suggested_alternative" (string, optional), 
        "targeted_question" (string, optional).

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

        try:
            response = requests.post(self.api_url, json=payload)
            response.raise_for_status()
            raw_text = response.json().get("response", "{}")
            llm_result = json.loads(raw_text)
        except Exception as e:
            print(f"[{self.agent_id}] Ollama Error: {e}")
            llm_result = {"vote": "ABSTAIN", "reason": f"Local LLM Failure: {e}"}

        # Extract and format the raw results (your existing code)
        vote_cast = llm_result.get("vote", "ABSTAIN").upper()
        suggested_alt = llm_result.get("suggested_alternative")
        
        if vote_cast == "ABSTAIN" or not suggested_alt or "none" in suggested_alt.lower():
            suggested_alt = None

        evidence = []
        if vote_cast == "APPROVE":
            for device, metrics in local_telemetry.items():
                for k, v in metrics.items():
                    if k == "domain_status":
                        continue
                    evidence.append({"metric": k, "value": v, "interpretation": f"Sourced by {self.agent_id}"})

        # --- THE MIDDLEWARE INJECTION ---
        raw_payload = {
            "vote": vote_cast,
            "reason": llm_result.get("reason", "No reason provided."),
            "suggested_alternative": suggested_alt,
            "supporting_evidence": evidence
        }
        
        # The firewall sanitizes the payload before releasing it to the Iterator
        sanitized_payload = CoordinationMiddleware.validate_agent_message(self.agent_id, raw_payload)

        return {
            "message_type": "hypothesis_vote",
            "incident_id": incident_id,
            "agent_id": self.agent_id,
            **sanitized_payload
        }