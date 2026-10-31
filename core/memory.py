import os
import json
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from core.output_store import save_output_json

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MEMORY_FILE = os.path.join(REPO_ROOT, "data", "incident_memory.json")

class IncidentMemory:
    """
    Thread-safe and persistent incident memory store for the multi-agent consensus system.
    Persists incident debate rounds, hypotheses, agent feedback, pivot hints, and final diagnostic reports to disk.
    Survives restarts and prevents state bleed while keeping long-term audit history.
    """
    def __init__(self, persistence_file: str = DEFAULT_MEMORY_FILE, auto_save: bool = True):
        self.persistence_file = persistence_file
        self.auto_save = auto_save
        self._lock = threading.Lock()

        # Active in-memory incidents currently in debate: incident_id -> dict
        self.incidents: Dict[str, Any] = {}
        # Historical / completed incidents: incident_id -> dict
        self.history: Dict[str, Any] = {}

        # Automatically load existing persistent memory if present
        self.load_from_disk()

    def _ensure_dir(self):
        if self.persistence_file:
            directory = os.path.dirname(self.persistence_file)
            if directory and not os.path.exists(directory):
                try:
                    os.makedirs(directory, exist_ok=True)
                except Exception:
                    pass

    def load_from_disk(self):
        """Loads historical and active incident records from disk."""
        with self._lock:
            if not self.persistence_file or not os.path.exists(self.persistence_file):
                return

            try:
                with open(self.persistence_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, dict):
                    loaded_active = data.get("active_incidents", {})
                    loaded_history = data.get("history", {})

                    # Handle legacy format where entire dict was incidents
                    if not loaded_active and not loaded_history and data:
                        loaded_history = data

                    # Normalize round numbers to int (JSON keys are always strings)
                    self.incidents = self._normalize_rounds_map(loaded_active)
                    self.history = self._normalize_rounds_map(loaded_history)
            except Exception as e:
                print(f"[MEMORY WARNING] Could not load persistence file {self.persistence_file}: {e}")

    def save_to_disk(self):
        """Thread-safe and atomic file persistence to disk."""
        if not self.auto_save or not self.persistence_file:
            return

        with self._lock:
            try:
                self._ensure_dir()
                payload = {
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "active_incidents": self.incidents,
                    "history": self.history
                }

                temp_file = f"{self.persistence_file}.tmp"
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)

                if os.path.exists(self.persistence_file):
                    os.replace(temp_file, self.persistence_file)
                else:
                    os.rename(temp_file, self.persistence_file)
            except Exception as e:
                # In sandbox or permission-restricted environments, fail gracefully
                pass

    def _normalize_rounds_map(self, incident_dict: dict) -> dict:
        result = {}
        for inc_id, inc_data in incident_dict.items():
            normalized = dict(inc_data)
            if "rounds" in normalized and isinstance(normalized["rounds"], dict):
                normalized["rounds"] = {
                    (int(k) if str(k).isdigit() else k): v
                    for k, v in normalized["rounds"].items()
                }
            result[inc_id] = normalized
        return result

    def _init_incident(self, incident_id: str):
        # Caller must hold self._lock
        if incident_id not in self.incidents:
            now = datetime.now(timezone.utc).isoformat()
            self.incidents[incident_id] = {
                "incident_id": incident_id,
                "created_at": now,
                "updated_at": now,
                "status": "in_progress",
                "rounds": {},
                "feedback": [],
                "final_report": None
            }

    def record_hypothesis(self, incident_id: str, round_num: int, proposed_cause: str):
        """Records Brain hypothesis for a specific round and persists to disk."""
        with self._lock:
            self._init_incident(incident_id)
            self.incidents[incident_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
            if round_num not in self.incidents[incident_id]["rounds"]:
                self.incidents[incident_id]["rounds"][round_num] = {
                    "hypothesis": proposed_cause,
                    "votes": {}
                }
            else:
                self.incidents[incident_id]["rounds"][round_num]["hypothesis"] = proposed_cause

        self.save_to_disk()

    def record_vote(
        self,
        incident_id: str,
        round_num: int,
        agent_id: str,
        vote: str,
        reason: str,
        alternative: Optional[str] = None,
        question: Optional[str] = None,
        pivot_hint: Optional[str] = None
    ):
        """Records an agent's vote and pivot hint for a specific round and persists to disk."""
        with self._lock:
            self._init_incident(incident_id)
            self.incidents[incident_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
            if round_num not in self.incidents[incident_id]["rounds"]:
                self.incidents[incident_id]["rounds"][round_num] = {"hypothesis": "UNKNOWN", "votes": {}}

            self.incidents[incident_id]["rounds"][round_num]["votes"][agent_id] = {
                "vote": vote,
                "reason": reason,
                "alternative": alternative,
                "question": question,
                "pivot_hint": pivot_hint
            }

        self.save_to_disk()

    def add_failed_round(self, incident_id: str, proposed_cause: str, feedback: str):
        """Appends failed round feedback to working memory and persists to disk."""
        with self._lock:
            self._init_incident(incident_id)
            if "feedback" not in self.incidents[incident_id]:
                self.incidents[incident_id]["feedback"] = []
            self.incidents[incident_id]["feedback"].append(feedback)

        self.save_to_disk()

    def record_final_report(self, incident_id: str, report: dict):
        """Records the final diagnostic report in persistent memory."""
        with self._lock:
            self._init_incident(incident_id)
            self.incidents[incident_id]["final_report"] = report
            self.incidents[incident_id]["status"] = report.get("status", "diagnosed")
            self.incidents[incident_id]["updated_at"] = datetime.now(timezone.utc).isoformat()

        self.save_to_disk()

    def get_reasoner_context(self, incident_id: str) -> str:
        """Builds a strict text summary of past rounds to inject into the Brain LLM prompt."""
        with self._lock:
            inc_data = self.incidents.get(incident_id)
            if not inc_data or not inc_data.get("rounds"):
                return "No previous rounds. This is Round 1."

            context = "HISTORY OF PREVIOUS ROUNDS:\n"
            rounds = inc_data["rounds"]

            for r_num in sorted(rounds.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
                r_data = rounds[r_num]
                context += f"--- Round {r_num} ---\n"
                context += f"Your Hypothesis: {r_data.get('hypothesis', 'UNKNOWN')}\n"
                context += "Agent Feedback:\n"

                for agent, v_data in r_data.get("votes", {}).items():
                    context += f"- {agent} voted {v_data.get('vote')}. Reason: {v_data.get('reason')}\n"
                    if v_data.get('pivot_hint'):
                        context += f"  CRITICAL PIVOT HINT: {v_data['pivot_hint']}\n"
                    if v_data.get('alternative'):
                        context += f"  Suggested Alternative: {v_data['alternative']}\n"
                    if v_data.get('question'):
                        context += f"  Targeted Question from Agent: {v_data['question']}\n"
                context += "\n"

            if inc_data.get("feedback"):
                context += "FEEDBACK FROM FAILED ROUNDS:\n"
                for fb in inc_data["feedback"]:
                    context += f"{fb}\n"

            context += "INSTRUCTION: You must NOT propose a hypothesis that was rejected in previous rounds. Use the Agent Feedback AND answer any Targeted Questions or CRITICAL PIVOT HINTS to formulate a precise new hypothesis."
            return context

    def get_voter_context(self, incident_id: str, agent_id: str) -> str:
        """Builds a summary of the agent's own past votes to prevent LLM flip-flopping."""
        with self._lock:
            inc_data = self.incidents.get(incident_id)
            if not inc_data or not inc_data.get("rounds"):
                return "You have no previous votes for this incident."

            context = f"YOUR PREVIOUS VOTES FOR INCIDENT {incident_id}:\n"
            rounds = inc_data["rounds"]
            has_history = False

            for r_num in sorted(rounds.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
                r_data = rounds[r_num]
                votes = r_data.get("votes", {})
                if agent_id in votes:
                    has_history = True
                    v_data = votes[agent_id]
                    context += f"- Round {r_num}: Brain proposed '{r_data.get('hypothesis', 'UNKNOWN')}'. "
                    context += f"You voted {v_data.get('vote')} because: {v_data.get('reason')}\n"

            if not has_history:
                return "You have no previous votes for this incident."

            context += "\nINSTRUCTION: Maintain logical consistency with your previous votes unless new telemetry justifies a change."
            return context

    def clear_incident(self, incident_id: str, archive: bool = True):
        """
        Clears the incident from active working memory to prevent state bleed,
        while archiving it into long-term persistent storage (disk) by default.
        """
        with self._lock:
            if incident_id in self.incidents:
                if archive:
                    self.incidents[incident_id]["status"] = self.incidents[incident_id].get("status", "archived")
                    self.incidents[incident_id]["archived_at"] = datetime.now(timezone.utc).isoformat()
                    self.history[incident_id] = self.incidents[incident_id]
                del self.incidents[incident_id]

        self.save_to_disk()

    def get_incident(self, incident_id: str) -> Optional[dict]:
        """Retrieves an incident by ID from active or archived persistence memory."""
        with self._lock:
            if incident_id in self.incidents:
                return self.incidents[incident_id]
            if incident_id in self.history:
                return self.history[incident_id]
            return None

    def get_all_incidents(self) -> Dict[str, dict]:
        """Returns all incidents ever recorded across active and historical persistence."""
        with self._lock:
            combined = dict(self.history)
            combined.update(self.incidents)
            return combined

    def save_output(self, report_data: Any, filepath: str = "output.json", append_mode: bool = False) -> str:
        """Helper to save generated output directly to a JSON file in exact OUTPUT format."""
        return save_output_json(report_data, filepath=filepath, append_mode=append_mode)


# Singleton instance for application-wide shared memory
shared_memory = IncidentMemory()
