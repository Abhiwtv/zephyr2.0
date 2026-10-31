from pydantic import BaseModel, Field, ValidationError
from typing import Optional, List, Dict, Any

class AgentVoteSchema(BaseModel):
    """Strict schema definition for agent inter-communication"""
    vote: str = Field(pattern="^(APPROVE|REJECT|ABSTAIN)$", description="Must be an exact match")
    reason: str = Field(min_length=5, description="Agent must provide a justification")
    # THE UPGRADE: A specific channel for constructive feedback
    pivot_hint: Optional[str] = Field(
        default=None, 
        description="Mandatory if voting REJECT. Suggests a new direction for the Brain."
    )
    suggested_alternative: Optional[str] = None
    supporting_evidence: List[Dict[str, Any]] = []

class CoordinationMiddleware:
    @staticmethod
    def validate_agent_message(agent_id: str, raw_llm_output: dict) -> dict:
        """
        Intercepts raw LLM JSON and validates it against the strict Pydantic schema.
        Prevents Semantic Drift and hallucinated keys from crashing the consensus engine.
        """
        try:
            # 1. Force the output through the strict Pydantic validator
            validated_data = AgentVoteSchema(**raw_llm_output)
            return validated_data.model_dump()
            
        except ValidationError as e:
            # 2. If the LLM hallucinates a bad schema, the middleware intercepts it,
            # suppresses the crash, and forces a safe fallback state.
            print(f"\n[MIDDLEWARE ALERT] Intercepted malformed response from {agent_id}. Enforcing safe fallback.")
            print(f"Validation Error: {e.errors()[0]['msg']}")
            
            return {
                "vote": "ABSTAIN",
                "reason": "Middleware intercept: Agent generated malformed JSON schema.",
                "pivot_hint": None,
                "suggested_alternative": None,
                "supporting_evidence": []
            }
