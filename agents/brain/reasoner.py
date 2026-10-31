import os
import json
import aiohttp
from google import genai
from google.genai import types

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
        2. Return strictly valid JSON containing EXACTLY three keys: 
           - "proposed_root_cause" (string)
           - "confidence_estimate" (float between 0.0 and 1.0)
           - "recommended_actions" (list of strings representing practical troubleshooting steps)
        """

    async def generate_hypothesis(self, incident_id, aggregated_alerts, memory_context):
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
            # Replaced blocking requests.post with asynchronous aiohttp
            timeout = aiohttp.ClientTimeout(total=45)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.api_url, json=payload) as response:
                    response.raise_for_status()
                    result = await response.json()
                    raw_text = result.get("response", "{}")
                    
                    # Strip Markdown code blocks to prevent JSON parsing crashes
                    raw_text = raw_text.strip()
                    if raw_text.startswith("```json"):
                        raw_text = raw_text[7:]
                    if raw_text.endswith("```"):
                        raw_text = raw_text[:-3]
                        
                    llm_result = json.loads(raw_text.strip())

            root_cause = llm_result.get("proposed_root_cause", "Unknown network anomaly")
            confidence = float(llm_result.get("confidence_estimate", 0.1))
            actions = llm_result.get("recommended_actions", ["Manual review required"])

        except Exception as e:
            print(f"Reasoner Error: {e}")
            root_cause = "Unknown network anomaly"
            confidence = 0.1
            actions = ["Manual review required"]

        return {
            "message_type": "hypothesis_broadcast",
            "incident_id": incident_id,
            "proposed_root_cause": root_cause,
            "confidence_estimate": confidence,
            "recommended_actions": actions,
            "target_devices": devices
        }