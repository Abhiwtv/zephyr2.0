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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# --- IMPORT LIVE PIPELINE COMPONENTS ---
from core.sensors import InfrastructureSensor, TrafficSensor, L4L7Sensor
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

app = FastAPI(
    title="NetCoop Live Engine",
    description="Real-time Neuro-Symbolic Multi-Agent Diagnostic Engine & Debate Stream",
    version="2.0.0"
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
    """Schema for incoming raw telemetry vectors from network devices."""
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
    device_id: str = Field(..., description="Unique identifier of target device")
    metrics: Dict[str, Any] = Field(..., description="Dictionary mapping metric names to floats")

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

        text_message = message if isinstance(message, str) else json.dumps(message)
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
            "event": "CONNECTION_ESTABLISHED",
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
        suspected_root_cause="Normal network baseline traffic. All telemetry metrics within nominal thresholds.",
        confidence=1.0,
        affected_devices=[device_id],
        supporting_evidence=[],
        alternative_causes=[],
        recommended_actions=["Continue periodic monitoring"],
        evidence_sources=["deterministic_sensors"],
        limitations=["Filtered by symbolic sensor layer"]
    )


@app.post(
    "/api/v1/diagnose",
    response_model=DiagnosticReport,
    status_code=status.HTTP_200_OK,
    summary="Run Live Neuro-Symbolic Diagnosis"
)
async def run_live_diagnosis(payload: TelemetryInput) -> DiagnosticReport:
    """
    Synchronous REST endpoint executing the LIVE AI pipeline:
    1. Ingests raw telemetry into global shared state.
    2. Routes payload through deterministic Symbolic Sensors.
    3. Engages strictly-masked multi-agent consensus swarm.
    4. Returns strictly formatted JSON DiagnosticReport.
    """
    incident_id = f"INC-{payload.device_id}-{uuid.uuid4().hex[:6]}"
    raw_dict = payload.dict() if hasattr(payload, "dict") else payload.model_dump()

    await noc_logger.emit(f"> [SYSTEM] Telemetry received for {payload.device_id}. Initiating neuro-symbolic pipeline...")

    # 1. FIX: Clear global state to prevent API data leakage across requests, then inject current telemetry
    global_state.device_states.clear()
    global_state.device_states[payload.device_id] = payload.metrics
    if hasattr(global_state, "latest_device"):
        global_state.latest_device = payload.device_id

    # 2. Run Symbolic Sensors
    alerts = []
    
    infra_alert = InfrastructureSensor().process_telemetry(raw_dict)
    if infra_alert.get("anomaly_score", 0.0) > 0:
        alerts.append(infra_alert)

    traffic_alert = TrafficSensor().process_telemetry(raw_dict)
    if traffic_alert.get("anomaly_score", 0.0) > 0:
        alerts.append(traffic_alert)

    l4_alert = L4L7Sensor().process_telemetry(raw_dict)
    if l4_alert.get("anomaly_score", 0.0) > 0:
        alerts.append(l4_alert)

    # 3. Fast-Path Exit (Healthy)
    if not alerts:
        await noc_logger.emit("> [SYSTEM] All metrics healthy. Filtering payload. Halting execution.")
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
    await noc_logger.emit(f"> [ITERATOR] Engaging local multi-agent consensus swarm for incident {incident_id}...")
    
    # Use the correct execution method from our rewritten iterator.py
    final_report = await iterator.execute_voting_loop(incident_id, alerts)

    await noc_logger.emit("> [ITERATOR] Consensus achieved. Terminating pipeline.")

    # 6. Format and package strictly into DiagnosticReport schema
    report = DiagnosticReport(
        incident_id=final_report.get("incident_id", incident_id),
        status=final_report.get("status", "diagnosed"),
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


if __name__ == "__main__":
    logger.info("Starting NetCoop Live Engine on http://0.0.0.0:8000 ...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)