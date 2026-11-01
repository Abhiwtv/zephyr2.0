"""
Zephyr 2.0 / NetCoop AI - Network Operations Center (NOC) Production Backend
=============================================================================
FastAPI backend exposing the live Neuro-Symbolic Multi-Agent AI pipeline
(Sensors -> Brain Reasoning -> Voter Consensus -> Middleware) with zero mocks,
real-time WebSocket debate streaming, and strict Pydantic schemas.
"""

import asyncio
import json
import logging
import uuid
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

import os
import shutil
import subprocess
import threading
from contextlib import asynccontextmanager
from pathlib import Path
import requests
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status, Request, Query, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
import uvicorn

# --- IMPORT LIVE PIPELINE COMPONENTS ---
from agents.infrastructure.sensor import InfrastructureSensor
from agents.traffic.sensor import TrafficSensor
from agents.l4_l7.sensor import L4L7Sensor
from core.config import EngineState, settings
from agents.brain.iterator import AsyncConsensusIterator
from agents.brain.reasoner import ReasoningEngine
from agents.voters.llm_voter import LLMDomainVoter
from core.shared_state import global_state

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("NetCoop-Engine")

# Global state to track engine boot times
ignition_telemetry = {"start_time": None, "last_boot_duration": None}


def listen_to_ntfy():
    """Background thread that listens to the ntfy.sh stream continuously."""
    global ignition_telemetry
    url = "https://ntfy.sh/zephyr-gpu-status-k92a/json"
    print(f"[*] Starting background listener on {url}")
    logger.info(f"[*] Starting background listener on {url}")
    while True:
        try:
            # stream=True keeps the connection open waiting for new pushes
            with requests.get(url, stream=True, timeout=None) as resp:
                for line in resp.iter_lines():
                    if line:
                        data = json.loads(line)
                        if data.get("event") == "message":
                            new_engine_url = (data.get("message") or "").strip().rstrip("/")
                            if new_engine_url and (new_engine_url.startswith("https://") or new_engine_url.startswith("http://")):
                                EngineState.url = new_engine_url
                                os.environ["ENGINE_URL"] = new_engine_url
                                settings.ENGINE_URL = new_engine_url
                                print(f"\n[+] BOOM! Engine URL autonomously updated to: {EngineState.url}\n")
                                logger.info(f"[+] BOOM! Engine URL autonomously updated to: {EngineState.url}")

                                # --- NEW TELEMETRY LOGIC ---
                                if ignition_telemetry.get("start_time"):
                                    elapsed = time.time() - ignition_telemetry["start_time"]
                                    mins = int(elapsed // 60)
                                    secs = int(elapsed % 60)
                                    boot_msg = f"[*] TELEMETRY: GPU Engine boot sequence completed in {mins}m {secs}s."
                                    print(f"\n{boot_msg}\n")
                                    logger.info(boot_msg)
                                    ignition_telemetry["last_boot_duration"] = f"{mins}m {secs}s"
                                    ignition_telemetry["start_time"] = None  # Reset for next run
                                # ---------------------------
        except Exception as e:
            print(f"[!] ntfy.sh stream disconnected, reconnecting in 5s... ({e})")
            logger.warning(f"[!] ntfy.sh stream disconnected, reconnecting in 5s... ({e})")
            time.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fire the ntfy listener on a background thread when FastAPI starts
    listener_thread = threading.Thread(target=listen_to_ntfy, daemon=True)
    listener_thread.start()
    yield

app = FastAPI(
    title="NetCoop Live Engine",
    description="Real-time Neuro-Symbolic Multi-Agent Diagnostic Engine & Debate Stream",
    version="2.0.0",
    lifespan=lifespan
)

# ---------------------------------------------------------------------------
# CORS Configuration (Next.js & Frontend Tooling)
# ---------------------------------------------------------------------------
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "*"  # Fallback for dev environments
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===========================================================================
# Task 1: Pydantic Data Contract Schemas
# ===========================================================================

class TelemetryInput(BaseModel):
    """
    Schema for incoming raw telemetry vectors from network devices.
    Transparently normalizes both flat metric payloads and campus SNMP
    schemas (netcoop.telemetry.v1) into standard metric keys for symbolic sensors.
    """
    timestamp: Optional[str] = Field(
        default=None,
        description="ISO 8601 UTC timestamp of telemetry capture"
    )
    device_id: str = Field(
        default="UNKNOWN_DEVICE",
        description="Unique identifier of target device"
    )
    metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary mapping metric names to floats or values"
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_telemetry(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # If already flattened with explicit device_id and metrics dict
        if "metrics" in data and isinstance(data["metrics"], dict) and "device_id" in data:
            if not data.get("timestamp"):
                data["timestamp"] = datetime.now(timezone.utc).isoformat()
            return data

        # Check for campus / SNMP telemetry format (records, active_probes, snmp_device)
        records = data.get("records", [])
        rec = records[0] if records and isinstance(records[0], dict) else {}

        probes = data.get("active_probes", [])
        probe = probes[0] if probes and isinstance(probes[0], dict) else {}

        snmp_devices = data.get("snmp_device", [])
        snmp = snmp_devices[0] if snmp_devices and isinstance(snmp_devices[0], dict) else {}

        device_id = data.get("device_id") or rec.get("device_id") or snmp.get("device_id") or "CS_DEPT_CORE_SW"
        timestamp = (
            data.get("timestamp")
            or rec.get("timestamp")
            or data.get("collected_at")
            or datetime.now(timezone.utc).isoformat()
        )

        metrics = dict(data.get("metrics") or {})

        # Interface / L2 metrics from records
        if "utilization_out_pct" in rec and "link_utilization_pct" not in metrics:
            metrics["link_utilization_pct"] = float(rec["utilization_out_pct"])
        if "in_errors" in rec and "interface_errors" not in metrics:
            metrics["interface_errors"] = int(rec["in_errors"])
        elif "crc_errors" in rec and "interface_errors" not in metrics:
            metrics["interface_errors"] = int(rec["crc_errors"])
        if "out_discards" in rec and "queue_drops" not in metrics:
            metrics["queue_drops"] = int(rec["out_discards"])
        if "rx_power_dbm" in rec and "rx_power_dbm" not in metrics:
            metrics["rx_power_dbm"] = float(rec["rx_power_dbm"])

        # Probe metrics
        if "latency_ms" in probe and "latency_ms" not in metrics:
            metrics["latency_ms"] = float(probe["latency_ms"])
        if "jitter_ms" in probe and "jitter_ms" not in metrics:
            metrics["jitter_ms"] = float(probe["jitter_ms"])
        if "packet_loss_pct" in probe and "packet_loss_pct" not in metrics:
            metrics["packet_loss_pct"] = float(probe["packet_loss_pct"])
        if "dns_latency_ms" in probe and "dns_latency_ms" not in metrics:
            metrics["dns_latency_ms"] = float(probe["dns_latency_ms"])

        # SNMP device metrics
        if "cpu_util_pct" in snmp and "cpu_utilization_pct" not in metrics:
            metrics["cpu_utilization_pct"] = float(snmp["cpu_util_pct"])
        elif "cpu_utilization_pct" in snmp and "cpu_utilization_pct" not in metrics:
            metrics["cpu_utilization_pct"] = float(snmp["cpu_utilization_pct"])
        if "mem_util_pct" in snmp and "mem_util_pct" not in metrics:
            metrics["mem_util_pct"] = float(snmp["mem_util_pct"])
        if "temperature_c" in snmp and "temperature_c" not in metrics:
            metrics["temperature_c"] = float(snmp["temperature_c"])
        if "dhcp_pool_utilization_pct" in snmp and "dhcp_pool_utilization_pct" not in metrics:
            metrics["dhcp_pool_utilization_pct"] = float(snmp["dhcp_pool_utilization_pct"])

        # Direct flat metrics fallback
        known_keys = {
            "cpu_utilization_pct", "interface_errors", "queue_drops",
            "link_utilization_pct", "packet_loss_pct", "latency_ms",
            "jitter_ms", "dns_latency_ms", "dhcp_pool_utilization_pct"
        }
        for k in known_keys:
            if k in data and k not in metrics:
                metrics[k] = data[k]

        return {
            "timestamp": timestamp,
            "device_id": device_id,
            "metrics": metrics
        }


class DiagnosticReport(BaseModel):
    """
    Exact output contract representing final consensus report produced
    by the Neuro-Symbolic Multi-Agent consensus pipeline. Matches desired JSON.
    """
    incident_id: str
    status: str
    suspected_root_cause: str
    confidence: float
    affected_devices: List[str]
    supporting_evidence: List[Dict[str, Any]]
    alternative_causes: List[str]
    recommended_actions: List[str]
    evidence_sources: List[str]
    limitations: List[str]
    root_cause_label: Optional[str] = None
    fault_category_code: Optional[str] = None


# ===========================================================================
# Task 3: WebSocket Event Emitter (The Real-Time Bridge)
# ===========================================================================

class RealTimeNOCLogger:
    """Manages active WebSocket connections and broadcasts real-time logs."""
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Active connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected.")

    async def emit(self, message: Any):
        async with self._lock:
            connections = list(self.active_connections)

        if not connections:
            return

        if isinstance(message, str):
            text_message = message.lstrip("> ").strip()
        elif isinstance(message, dict) and "agent" in message:
            agent_tag = message["agent"].upper()
            text_message = f"[{agent_tag}] {message.get('message', message.get('text', ''))}"
        else:
            text_message = json.dumps(message)

        dead_connections = []

        for connection in connections:
            try:
                await connection.send_text(text_message)
            except Exception:
                dead_connections.append(connection)

        if dead_connections:
            async with self._lock:
                for dead in dead_connections:
                    if dead in self.active_connections:
                        self.active_connections.remove(dead)

noc_logger = RealTimeNOCLogger()


@app.websocket("/api/v1/debate-stream")
async def debate_stream(websocket: WebSocket):
    await noc_logger.connect(websocket)
    try:
        await websocket.send_text(json.dumps({
            "agent": "SYSTEM",
            "message": "Subscribed to live NetCoop Multi-Agent debate stream.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        noc_logger.disconnect(websocket)
    except Exception as e:
        noc_logger.disconnect(websocket)


# ===========================================================================
# Task 2: Live REST Endpoint (POST /api/v1/diagnose)
# ===========================================================================

def generate_healthy_report(incident_id: str, device_id: str) -> DiagnosticReport:
    """Generates standardized diagnostic report for nominal baseline telemetry."""
    return DiagnosticReport(
        incident_id=incident_id,
        status="diagnosed",
        root_cause_label="NOMINAL_BASELINE",
        fault_category_code="NOMINAL_BASELINE",
        suspected_root_cause="Normal network baseline traffic. All telemetry metrics within nominal thresholds.",
        confidence=1.0,
        affected_devices=[device_id],
        supporting_evidence=[],
        alternative_causes=[],
        recommended_actions=["Continue periodic monitoring"],
        evidence_sources=["deterministic_sensors"],
        limitations=["Filtered by symbolic sensor layer"]
    )


# In-memory incident report store for asynchronous polling
active_diagnoses: Dict[str, Dict[str, Any]] = {}


async def execute_diagnosis_pipeline(incident_id: str, payload: TelemetryInput) -> DiagnosticReport:
    """
    Executes the neuro-symbolic multi-agent diagnosis pipeline:
    1. Ingests raw telemetry into global shared state.
    2. Routes payload through deterministic Symbolic Sensors.
    3. Engages strictly-masked multi-agent consensus swarm.
    4. Packages strictly formatted DiagnosticReport.
    """
    raw_dict = payload.dict() if hasattr(payload, "dict") else payload.model_dump()

    await noc_logger.emit(f"[SYSTEM] Telemetry received for {payload.device_id} ({len(payload.metrics)} metrics). Initiating neuro-symbolic pipeline...")

    # 1. Clear global state to prevent API data leakage across requests, then inject current telemetry
    global_state.device_states.clear()
    global_state.device_states[payload.device_id] = payload.metrics
    if hasattr(global_state, "latest_device"):
        global_state.latest_device = payload.device_id

    # 2. Run Symbolic Sensors
    alerts = []
    
    infra_alert = InfrastructureSensor().process_telemetry(raw_dict)
    if infra_alert.get("anomaly_score", 0.0) > 0 or infra_alert.get("alert_category", "healthy") != "healthy":
        alerts.append(infra_alert)
        await noc_logger.emit(
            f"[INFRASTRUCTURE_AGENT] InfraSensor Anomaly Score: {infra_alert.get('anomaly_score', 0.0)} ({infra_alert.get('alert_category', 'anomaly')})"
        )

    traffic_alert = TrafficSensor().process_telemetry(raw_dict)
    if traffic_alert.get("anomaly_score", 0.0) > 0 or traffic_alert.get("alert_category", "healthy") != "healthy":
        alerts.append(traffic_alert)
        await noc_logger.emit(
            f"[PERFORMANCE_AGENT] TrafficSensor Anomaly Score: {traffic_alert.get('anomaly_score', 0.0)} ({traffic_alert.get('alert_category', 'anomaly')})"
        )

    l4_alert = L4L7Sensor().process_telemetry(raw_dict)
    if l4_alert.get("anomaly_score", 0.0) > 0 or l4_alert.get("alert_category", "healthy") != "healthy":
        alerts.append(l4_alert)
        await noc_logger.emit(
            f"[CONNECTIVITY_AGENT] L4L7Sensor Anomaly Score: {l4_alert.get('anomaly_score', 0.0)} ({l4_alert.get('alert_category', 'anomaly')})"
        )

    # 3. Fast-Path Exit (Healthy)
    if not alerts:
        await noc_logger.emit("[SYSTEM] All metrics healthy. Fast-path nominal exit. Halting execution.")
        return generate_healthy_report(incident_id, payload.device_id)

    # 4. Initialize pipeline with STRICT DATA MASKING to prevent echo chamber
    reasoner = ReasoningEngine()
    voters = [
        LLMDomainVoter(
            "infrastructure_agent", 
            "Layer 1/2 hardware, CPU, and physical interfaces",
            monitored_metrics=["cpu_utilization_pct", "interface_errors", "queue_drops"]
        ),
        LLMDomainVoter(
            "traffic_agent", 
            "L2/L3 bandwidth, latency, and packet loss",
            monitored_metrics=["link_utilization_pct", "packet_loss_pct", "latency_ms", "jitter_ms"]
        ),
        LLMDomainVoter(
            "l4_l7_agent", 
            "DNS, DHCP, and application layer health",
            monitored_metrics=["dns_latency_ms", "dhcp_pool_utilization_pct"]
        )
    ]
    iterator = AsyncConsensusIterator(voter_agents=voters, reasoner=reasoner)

    # 5. Await the LLM inference loop
    await noc_logger.emit(f"[ORCHESTRATOR] Anomaly thresholds exceeded ({len(alerts)} domains). Engaging multi-agent consensus swarm for incident {incident_id}...")
    
    # Use the execution method from iterator.py
    final_report = await iterator.execute_voting_loop(incident_id, alerts)

    await noc_logger.emit(f"[CORRELATION_AGENT] Consensus reached (Confidence: {float(final_report.get('confidence', 0.0)):.2f}) -> {final_report.get('suspected_root_cause')}")
    await noc_logger.emit("[SYSTEM] Consensus achieved. Final diagnostic report packaged.")

    # 6. Format and package strictly into DiagnosticReport schema
    root_cause_label = (
        final_report.get("fault_category_code")
        or final_report.get("root_cause_label")
        or ("PHYSICAL_LAYER_FAULT" if "infrastructure" in [a.get("domain") for a in alerts] else "TRAFFIC_CONGESTION")
    )

    report = DiagnosticReport(
        incident_id=final_report.get("incident_id", incident_id),
        status=final_report.get("status", "diagnosed"),
        root_cause_label=root_cause_label,
        fault_category_code=final_report.get("fault_category_code") or root_cause_label,
        suspected_root_cause=final_report.get("suspected_root_cause", "Unknown network anomaly"),
        confidence=float(final_report.get("confidence", 0.0)),
        affected_devices=final_report.get("affected_devices", [payload.device_id]),
        supporting_evidence=final_report.get("supporting_evidence", []),
        alternative_causes=final_report.get("alternative_causes", []),
        recommended_actions=final_report.get("recommended_actions", ["Manual review required"]),
        evidence_sources=final_report.get("evidence_sources", []),
        limitations=final_report.get("limitations", ["Evaluated via multi-agent consensus"])
    )

    return report


@app.post(
    "/api/v1/diagnose",
    summary="Run Live Neuro-Symbolic Diagnosis",
    tags=["Diagnostics"]
)
async def run_live_diagnosis(
    payload: TelemetryInput,
    request: Request,
    mode: str = Query(default="async", description="Execution mode: 'async' (returns 202 for polling) or 'sync'")
):
    """
    REST endpoint executing the LIVE AI pipeline.
    
    Modes:
    - 'async' (default): Immediately returns HTTP 202 Accepted with an incident_id.
      The diagnosis runs in the background and can be polled via GET /api/v1/diagnose/{incident_id}.
      This prevents serverless and client timeouts while streaming real-time logs over WebSockets.
    - 'sync': Blocks until consensus is reached and returns the final DiagnosticReport directly.
    """
    incident_id = f"INC-{payload.device_id}-{uuid.uuid4().hex[:6]}"

    # Async Request-Reply pattern: Return 202 immediately to prevent serverless/proxy timeouts
    if mode == "async" or request.headers.get("Prefer") == "respond-async":
        active_diagnoses[incident_id] = {
            "status": "processing",
            "incident_id": incident_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "message": "Diagnosis pipeline running in background"
        }

        async def _run_bg():
            try:
                report = await execute_diagnosis_pipeline(incident_id, payload)
                report_dict = report.model_dump()
                active_diagnoses[incident_id] = report_dict
                # Broadcast completion to WebSocket subscribers
                await noc_logger.emit({
                    "event": "DIAGNOSIS_COMPLETE",
                    "incident_id": incident_id,
                    "report": report_dict
                })
            except Exception as e:
                logger.exception(f"Background diagnosis failed for {incident_id}")
                err_report = {
                    "incident_id": incident_id,
                    "status": "error",
                    "message": f"Diagnosis failed: {e}",
                    "suspected_root_cause": "System Error during multi-agent consensus",
                    "confidence": 0.0,
                    "affected_devices": [payload.device_id],
                    "supporting_evidence": [],
                    "alternative_causes": [],
                    "recommended_actions": ["Review backend logs and retry"],
                    "evidence_sources": [],
                    "limitations": [str(e)]
                }
                active_diagnoses[incident_id] = err_report
                await noc_logger.emit(f"[SYSTEM] Pipeline error on {incident_id}: {e}")

        asyncio.create_task(_run_bg())

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "status": "processing",
                "incident_id": incident_id,
                "poll_url": f"/api/v1/diagnose/{incident_id}",
                "message": "Diagnosis pipeline initiated in background"
            }
        )

    # Synchronous mode (legacy / direct scripts)
    report = await execute_diagnosis_pipeline(incident_id, payload)
    active_diagnoses[incident_id] = report.model_dump()
    return report


@app.get(
    "/api/v1/diagnose/{incident_id}",
    summary="Poll Incident Status or Final Report",
    tags=["Diagnostics"]
)
async def get_incident_status(incident_id: str):
    """
    Lightweight polling endpoint:
    Returns 200 with status: 'processing', 'diagnosed' (with full report), or 'error'.
    Execution time < 5ms (completely immune to serverless timeouts).
    """
    if incident_id not in active_diagnoses:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"status": "not_found", "message": f"Incident {incident_id} not found"}
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=active_diagnoses[incident_id]
    )



# ===========================================================================
# Task 4: GPU Engine Automation & Live URL Routing
# ===========================================================================

class EngineURLPayload(BaseModel):
    url: str

def trigger_kaggle_push():
    """Background task to fire the Kaggle batch job with a unique UUID."""
    global ignition_telemetry
    ignition_telemetry["start_time"] = time.time()
    try:
        kaggle_user = os.getenv("KAGGLE_USER", "")
        if not kaggle_user:
            print("[!] KAGGLE_USER not found in environment.")
            return

        # 1. Generate a unique ID to avoid 409 Conflicts
        run_id = uuid.uuid4().hex[:6]
        slug = f"zephyr-engine-{run_id}"

        # 2. Overwrite kernel-metadata.json dynamically
        metadata_path = "/home/ubuntu/zephyr-control/kaggle-runner/kernel-metadata.json"
        metadata = {
            "id": f"{kaggle_user}/{slug}",
            "title": slug,
            "code_file": "runner.py",
            "language": "python",
            "kernel_type": "script",
            "is_private": True,
            "enable_gpu": True,
            "enable_tpu": False,
            "enable_internet": True,
            "machine_shape": "NvidiaTeslaT4"
        }
        
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        print(f"[*] Generated unique Kaggle payload: {slug}")

        # 3. Execute the push
        cmd = [
            "/home/ubuntu/zephyr-control/venv/bin/kaggle", 
            "kernels", 
            "push", 
            "-p", 
            "/home/ubuntu/zephyr-control/kaggle-runner"
        ]
        
        custom_env = os.environ.copy()
        custom_env["KAGGLE_USERNAME"] = kaggle_user
        custom_env["KAGGLE_KEY"] = os.getenv("KAGGLE_KEY", "")
        custom_env["HOME"] = "/home/ubuntu"
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=custom_env)
        print(f"[+] Kaggle push successful for {slug}:\n{result.stdout}")
        
    except subprocess.CalledProcessError as e:
        print(f"[!] Kaggle push failed:\nSTDERR: {e.stderr}\nSTDOUT: {e.stdout}")
    except Exception as ex:
        print(f"[!] Unexpected error in background task: {ex}")

@app.post(
    "/api/v1/engine/ignite",
    summary="Ignite Kaggle GPU Engine",
    tags=["Engine"]
)
async def ignite_gpu_engine(background_tasks: BackgroundTasks):
    """Fired by your Next.js dashboard button to boot the GPU."""
    background_tasks.add_task(trigger_kaggle_push)
    return {"status": "success", "message": "Kaggle GPU provisioning initiated."}

@app.post(
    "/api/v1/engine/set-url",
    summary="Set Dynamic Engine URL",
    tags=["Engine"]
)
async def set_engine_url(payload: EngineURLPayload):
    """Updates the active routing URL in memory without restarting the server."""
    clean_url = payload.url.strip().rstrip("/")
    if not (clean_url.startswith("https://") or clean_url.startswith("http://")):
        raise HTTPException(status_code=400, detail="Invalid Cloudflare URL")

    EngineState.url = clean_url
    os.environ["ENGINE_URL"] = clean_url
    settings.ENGINE_URL = clean_url
    print(f"[+] Engine URL dynamically updated to: {EngineState.url}")
    logger.info(f"[+] Engine URL dynamically updated to: {EngineState.url}")
    return {"status": "success", "active_engine": EngineState.url}

@app.get(
    "/api/v1/engine/status",
    summary="Get Active Engine Status",
    tags=["Engine"]
)
async def get_engine_status():
    """Returns current active LLM engine URL and configuration."""
    return {
        "status": "online" if EngineState.url else "offline",
        "active_engine": EngineState.url,
        "model": settings.OLLAMA_MODEL,
        "boot_in_progress": ignition_telemetry.get("start_time") is not None,
        "last_boot_duration": ignition_telemetry.get("last_boot_duration")
    }


# ---------------------------------------------------------------------------
# Health & Status Endpoint
# ---------------------------------------------------------------------------

@app.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    tags=["System"]
)
async def health_check():
    """Returns operational status and active WebSocket subscriber count."""
    return {
        "status": "healthy",
        "service": "Zephyr NOC Multi-Agent Live Engine",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "active_ws_clients": len(noc_logger.active_connections)
    }


if __name__ == "__main__":
    logger.info("Starting NetCoop Live Engine on http://0.0.0.0:8000 ...")
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)