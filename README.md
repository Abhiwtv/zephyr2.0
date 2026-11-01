# Zephyr 2.0 (NetCoop AI)

Autonomous Multi-Agent Network Telemetry Consensus, Anomaly Detection, and Fault Localization Engine for Campus & Enterprise Networks.

---

## 🌟 Overview

**Zephyr 2.0** is a distributed multi-agent system designed for real-time automated diagnosis and root-cause localization of complex network faults. It combines deterministic edge sensor filtering, Pydantic-enforced semantic middleware validation, dynamic severity-weighted debate iterations, persistent episodic incident memory, and LLM reasoning.

Key capabilities:
- **Zero-False-Positive Sensor Pipeline**: Lightweight domain sensors (`infrastructure`, `traffic`, `l4_l7`) drop normal baseline telemetry at wire speed, ensuring 0% unnecessary LLM compute waste.
- **Dynamic Severity Multipliers**: Heuristic consensus weighting proportional to physical fault severity; high-impact anomalies terminate debate in a single round.
- **Pydantic Middleware Firewall**: Guarantees zero semantic drift and validates strict schema adherence across all agent ballots, requiring constructive `pivot_hint` guidance upon vote rejection.
- **Thread-Safe Episodic Incident Memory**: Persistent incident history stored with atomic disk flushes (`data/incident_memory.json`) and recursive locks (`RLock`) to prevent deadlocks.
- **Decoupled Cloud & Batch Runners**: Full deployment support with Caddy reverse-proxy configurations, systemd services, and headless GPU batch runners for Kaggle / Ollama inference.

---

## 📁 Repository Structure

```text
C:.
   .gitignore
   .env.example
   README.md
   requirements.txt
   pytest.ini
   main.py
   
+---agents/
       __init__.py
     brain/
       iterator.py          # Asynchronous consensus loop & severity tallying
       orchestrator.py      # Incident lifecycle management
       reasoner.py          # Hypothesis generation engine with fast socket probes
     infrastructure/
       sensor.py            # Layer 1/2 hardware metrics sensor
       voter.py             # Infrastructure domain heuristic voter
     l4_l7/
       sensor.py            # Core network services sensor (DNS, DHCP)
       voter.py             # L4/L7 service voter
     traffic/
       sensor.py            # Bandwidth & QoS metrics sensor
       voter.py             # Traffic congestion & buffer voter
     voters/
       llm_voter.py         # Isolated domain LLM voter with evidence validation
       
+---core/
       __init__.py
       config.py            # Centralized environment settings via Pydantic & dotenv
       fuzzy.py             # Fuzzy matching & similarity algorithms
       memory.py            # Thread-safe persistent incident memory
       middleware.py        # Semantic validation firewall & ballot schema
       output_store.py      # Output artifact persistence & formatting
       shared_state.py      # Global state with thread-safe RLock
       
+---data/
       benchmark_dataset.jsonl          # 10 Ground-Truth Empirical Scenarios
       evaluation_results.jsonl         # Empirical test results log
       iit_bbs_benchmark_dataset.json   # IIT Bhubaneswar campus scenarios
       incident_memory.json             # Persistent episodic incident history
       
+---deploy/                  # Cloud & Infrastructure Automation
     caddy/
       Caddyfile            # Production reverse proxy with WebSocket support
     systemd/
       zephyr-control.service # Systemd service unit for Oracle Cloud / Linux VM
       
+---kaggle-runner/           # Headless GPU Batch Package (Kaggle / RunPod)
       kernel-metadata.json # Kaggle notebook metadata
       runner.py            # Headless Ollama + Cloudflare Tunnel orchestration
       
+---scripts/                 # Operational, Stress & Evaluation Scripts
       __init__.py
       evaluator.py         # Empirical 10-scenario ground-truth evaluation runner
       massive_evaluator.py # Campus-wide batch stress benchmark
       generate_telemetry.py # Synthetic telemetry generator
       stress_test.py       # Async cascading failure test
       stress_test_shi.py   # Multi-switch campus stress simulator
       
+---tests/                   # Pytest Test Suites
       test_brain.py
       test_evaluator.py
       test_fuzzy.py
       test_infrastructure.py
       test_l4_l7.py
       test_llm_voter.py
       test_memory.py
       test_persistence.py
       test_reasoner.py
       test_traffic.py
```

---

## 🚀 Quick Start

### 1. Installation

Clone the repository and install dependencies:
```bash
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configuration

Copy `.env.example` to `.env` and adjust your settings:
```bash
cp .env.example .env
```

Key environment variables:
- `ENGINE_URL`: LLM inference endpoint (e.g., local Ollama `http://localhost:11434` or Cloudflare tunnel `https://<tunnel-id>.trycloudflare.com`).
- `OLLAMA_MODEL`: LLM model name (default: `qwen3:14b` or `qwen2.5:7b`).
- `HOST` / `PORT`: Server bind address and port (default: `0.0.0.0:8000`).
- `DATA_DIR`: Path to the data directory (default: `data`).

### 3. Start the API Server

```bash
python main.py
```
The server exposes:
- `POST /telemetry`: Ingest raw device metrics.
- `GET /incidents`: Query active and diagnosed incidents.
- `GET /health`: Engine status and LLM connectivity probe.
- `WS /ws/telemetry`: Real-time streaming WebSocket feed.

---

## 🧪 Testing & Evaluation

### Run Pytest Test Suite
All unit and regression tests reside strictly in `tests/`:
```bash
pytest
```

### Run Empirical Ground-Truth Evaluator
Validates noise filtering specificity, fault detection recall, and single-round consensus termination across all 10 ground truth scenarios:
```bash
python scripts/evaluator.py
```

### Run Campus Stress Benchmark
Executes end-to-end multi-fault stress testing:
```bash
python scripts/massive_evaluator.py
python scripts/stress_test.py
python scripts/stress_test_shi.py
```

---

## ☁️ Deployment

### Oracle Cloud / Linux VM via Systemd
1. Copy `deploy/systemd/zephyr-control.service` to `/etc/systemd/system/zephyr-control.service`.
2. Reload daemon and start service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now zephyr-control.service
   ```

### Reverse Proxy via Caddy
1. Configure `deploy/caddy/Caddyfile` with your domain.
2. Start or reload Caddy:
   ```bash
   sudo caddy reload --config deploy/caddy/Caddyfile
   ```

### Kaggle / Colab GPU Headless Runner
To run Ollama with Cloudflare Tunneling on a free GPU instance:
1. Navigate to `kaggle-runner/`.
2. Push or execute `runner.py` inside the Kaggle environment to establish an Ollama tunnel.
3. Update `ENGINE_URL` in your `.env` with the generated Cloudflare URL.
