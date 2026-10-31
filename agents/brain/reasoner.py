
import os
import json
from google import genai
from google.genai import types
import requests

class ReasoningEngine:
    """Ollama-driven logic engine running local Qwen 7B."""
    def __init__(self):
        self.api_url = "http://localhost:11434/api/generate"
        self.model_name = "qwen2.5:7b-instruct"

        self.system_prompt = """
        You are the central Fault Correlation Agent (Brain) for a university campus network.
        Analyze telemetry alerts and propose a root cause hypothesis.
        
        NETWORK DOMAINS:
        - Layer 1/2 Hardware: Interface errors, CPU exhaustion, queue drops.
        - Traffic/Congestion: High link utilization, latency spikes, packet loss.
        - L4-L7 Services: DNS latency, DHCP pool exhaustion.
        
        INSTRUCTIONS:
        1. Analyze active alerts and memory.
        2. Return strictly valid JSON containing EXACTLY two keys: "proposed_root_cause" (string) and "confidence_estimate" (float between 0.0 and 1.0).
        """

    def generate_hypothesis(self, incident_id, aggregated_alerts, memory_context):
        devices = list(set(alert["device_id"] for alert in aggregated_alerts))
        
        prompt = f"""
        {self.system_prompt}
        
        INCIDENT ID: {incident_id}
        ACTIVE ALERTS: {json.dumps(aggregated_alerts)}
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
            
            # Ollama returns the generated text in the 'response' key
            raw_text = response.json().get("response", "{}")
            llm_result = json.loads(raw_text)

            root_cause = llm_result.get("proposed_root_cause", "Unknown network anomaly")
            confidence = float(llm_result.get("confidence_estimate", 0.1))

        except Exception as e:
            print(f"Reasoner Error: {e}")
            root_cause = "Unknown network anomaly"
            confidence = 0.1

        return {
            "message_type": "hypothesis_broadcast",
            "incident_id": incident_id,
            "proposed_root_cause": root_cause,
            "confidence_estimate": confidence,
            "target_devices": devices
        }
