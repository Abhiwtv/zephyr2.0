class FuzzyLogicEngine:
    """A first-principles fuzzy logic engine using Triangular Membership Functions (TRIMF)."""
    
    @staticmethod
    def trimf(x, a, b, c):
        if x <= a or x >= c:
            # Handle the edge case where the peak is exactly at the max boundary (e.g., 100%)
            if b == c and x == b:
                return 1.0
            return 0.0
        elif a < x <= b:
            return (x - a) / (b - a)
        elif b < x < c:
            return (c - x) / (c - b)
        return 0.0

    @staticmethod
    def fuzzify_metric(value, normal_params, warning_params, critical_params):
        degrees = {
            "Normal": FuzzyLogicEngine.trimf(value, *normal_params),
            "Warning": FuzzyLogicEngine.trimf(value, *warning_params),
            "Critical": FuzzyLogicEngine.trimf(value, *critical_params)
        }
        dominant_state = max(degrees, key=degrees.get)
        return dominant_state, degrees[dominant_state]