import pytest
from evaluator import NetCoopEvaluator

def test_evaluator_benchmark_suite():
    """
    End-to-end empirical benchmark evaluation suite test.
    Validates noise filtering specificity, fault detection recall,
    and single-round consensus termination across all 10 evaluation scenarios.
    """
    evaluator = NetCoopEvaluator()
    summary = evaluator.run_evaluation_suite()
    
    assert summary["overall_accuracy_pct"] == 100.0, (
        f"Expected 100.0% accuracy, got {summary['overall_accuracy_pct']}%"
    )
    assert summary["passed_tests"] == summary["total_tests"], (
        f"Failed {summary['total_tests'] - summary['passed_tests']} tests out of {summary['total_tests']}"
    )
    assert summary["noise_filtering_specificity_pct"] == 100.0, (
        f"Noise filtering specificity is {summary['noise_filtering_specificity_pct']}%, expected 100%"
    )
    assert summary["fault_detection_sensitivity_pct"] == 100.0, (
        f"Fault detection sensitivity is {summary['fault_detection_sensitivity_pct']}%, expected 100%"
    )
    assert summary["average_debate_rounds"] == 1.0, (
        f"Expected mean debate rounds to be 1.0 (breaking in Round 1 via dynamic severity multipliers), got {summary['average_debate_rounds']}"
    )

if __name__ == "__main__":
    test_evaluator_benchmark_suite()
