import threading

class StateStore:
    """A thread-safe in-memory store for network telemetry."""
    def __init__(self):
        self.device_states = {}
        self.latest_device = None
        self._lock = threading.Lock() # <-- ADDED MUTEX LOCK

    def update_state(self, device_id, metrics):
        with self._lock:              # <-- ACQUIRE LOCK BEFORE WRITING
            self.device_states[device_id] = metrics
            self.latest_device = device_id

    def get_state(self, device_id):
        with self._lock:              # <-- ACQUIRE LOCK BEFORE READING
            return self.device_states.get(device_id, {})

# Singleton instance to be imported by sensors and voters
global_state = StateStore()
