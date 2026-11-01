# Zephyr 2.0 – Test Execution Guide

Run commands from the repository root:

```powershell
cd d:\zephyr2\zephyr2.0
pip install pytest pytest-asyncio
```

## 1. Main Tests – Multi-Agent Benchmark

These tests evaluate the complete multi-agent consensus workflow involving the Infrastructure, Traffic, and L4/L7 agents, along with the Reasoning Engine.

**Default run – first 10 dataset items:**
```bash
python tests/main-evaluator.py
```

**Run a custom number of items:**
```bash
python tests/main-evaluator.py 5
```

**Run the full 50-item benchmark:**
```bash
python tests/main-evaluator.py --full
```

Alternative evaluator:
```bash
python scripts/massive_evaluator.py
```

Both evaluators default to the first 10 items of `data/iit_bbs_benchmark_dataset.json`.

## 2. Unit Tests

Unit tests validate individual components without requiring live LLM inference, including agent sensors, voters, fuzzy logic, memory, persistence, and schema validation.

**Run all unit tests:**
```bash
python -m pytest tests/unit-tests
```

**Run an individual test suite:**

| Component | Command |
|---|---|
| Benchmark Dataset | `python tests/unit-tests/test_benchmark_dataset.py` |
| Infrastructure Agent | `python tests/unit-tests/test_infrastructure.py` |
| Traffic Agent | `python tests/unit-tests/test_traffic.py` |
| L4/L7 Agent | `python tests/unit-tests/test_l4_l7.py` |
| Brain Orchestrator | `python tests/unit-tests/test_brain.py` |
| Fuzzy Logic | `python tests/unit-tests/test_fuzzy.py` |
| LLM Voter | `python tests/unit-tests/test_llm_voter.py` |
| Memory Store | `python tests/unit-tests/test_memory.py` |
| Persistence | `python tests/unit-tests/test_persistence.py` |
| Reasoning Engine | `python tests/unit-tests/test_reasoner.py` |

## 3. Quick Reference

| Test | Command |
|---|---|
| All Unit Tests | `python -m pytest tests/unit-tests` |
| Main Benchmark (10 items) | `python tests/main-evaluator.py` |
| Benchmark (5 items) | `python tests/main-evaluator.py 5` |
| Full Benchmark (50 items) | `python tests/main-evaluator.py --full` |

**Note:** Benchmark evaluators and the benchmark dataset unit test default to the first 10 dataset items.