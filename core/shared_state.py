# A simple thread-safe-ish in-memory store for the hackathon
class StateStore:
    def __init__(self):
        self.device_states = {}

    def update_state(self, device_id, metrics):
        self.device_states[device_id] = metrics

    def get_state(self, device_id):
        return self.device_states.get(device_id, {})

# Singleton instance to be imported by sensors and voters
global_state = StateStore()