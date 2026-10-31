import json
import threading

class IncidentMemory:
    def __init__(self):
        # Maps incident_id -> dict of rounds -> round_data
        self.incidents = {}
        self._lock = threading.Lock()  # <-- ADDED MUTEX LOCK

    def _init_incident(self, incident_id):
        # Internal helper: lock is acquired by the caller
        if incident_id not in self.incidents:
            self.incidents[incident_id] = {"rounds": {}}

    def record_hypothesis(self, incident_id, round_num, proposed_cause):
        with self._lock:               # <-- LOCK
            self._init_incident(incident_id)
            if round_num not in self.incidents[incident_id]["rounds"]:
                self.incidents[incident_id]["rounds"][round_num] = {"hypothesis": proposed_cause, "votes": {}}
            else:
                self.incidents[incident_id]["rounds"][round_num]["hypothesis"] = proposed_cause

    def record_vote(self, incident_id, round_num, agent_id, vote, reason, alternative=None, question=None):
        with self._lock:               # <-- LOCK
            self._init_incident(incident_id)
            if round_num not in self.incidents[incident_id]["rounds"]:
                 self.incidents[incident_id]["rounds"][round_num] = {"hypothesis": "UNKNOWN", "votes": {}}
                 
            self.incidents[incident_id]["rounds"][round_num]["votes"][agent_id] = {
                "vote": vote,
                "reason": reason,
                "alternative": alternative,
                "question": question
            }

    def get_reasoner_context(self, incident_id):
        """Builds a strict text summary of past rounds to inject into the Brain LLM prompt."""
        with self._lock:               # <-- LOCK
            if incident_id not in self.incidents or not self.incidents[incident_id]["rounds"]:
                return "No previous rounds. This is Round 1."

            context = "HISTORY OF PREVIOUS ROUNDS:\n"
            rounds = self.incidents[incident_id]["rounds"]
            
            for r_num in sorted(rounds.keys()):
                r_data = rounds[r_num]
                context += f"--- Round {r_num} ---\n"
                context += f"Your Hypothesis: {r_data['hypothesis']}\n"
                context += "Agent Feedback:\n"
                
                for agent, v_data in r_data["votes"].items():
                    context += f"- {agent} voted {v_data['vote']}. Reason: {v_data['reason']}\n"
                    if v_data.get('alternative'):
                        context += f"  Suggested Alternative: {v_data['alternative']}\n"
                    if v_data.get('question'):
                        context += f"  Targeted Question from Agent: {v_data['question']}\n"
                context += "\n"
                
            context += "INSTRUCTION: You must NOT propose a hypothesis that was rejected in previous rounds. Use the Agent Feedback AND answer any Targeted Questions to formulate a precise new hypothesis."
            return context
    
    def get_voter_context(self, incident_id, agent_id):
        """Builds a summary of the agent's own past votes to prevent LLM flip-flopping."""
        with self._lock:               # <-- LOCK
            if incident_id not in self.incidents or not self.incidents[incident_id]["rounds"]:
                return "You have no previous votes for this incident."

            context = f"YOUR PREVIOUS VOTES FOR INCIDENT {incident_id}:\n"
            rounds = self.incidents[incident_id]["rounds"]
            has_history = False

            for r_num in sorted(rounds.keys()):
                r_data = rounds[r_num]
                if agent_id in r_data["votes"]:
                    has_history = True
                    v_data = r_data["votes"][agent_id]
                    context += f"- Round {r_num}: Brain proposed '{r_data['hypothesis']}'. "
                    context += f"You voted {v_data['vote']} because: {v_data['reason']}\n"

            if not has_history:
                return "You have no previous votes for this incident."
                
            context += "\nINSTRUCTION: Maintain logical consistency with your previous votes unless new telemetry justifies a change."
            return context

    def clear_incident(self, incident_id):
        with self._lock:               # <-- LOCK
            if incident_id in self.incidents:
                del self.incidents[incident_id]

# Singleton for the hackathon
shared_memory = IncidentMemory()