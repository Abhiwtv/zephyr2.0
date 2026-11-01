import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient
from main import app, noc_logger

def test_runner_telemetry_with_progress():
    client = TestClient(app)
    payload = {
        "message": "Downloading qwen2.5:14b: 45%",
        "progress": 45.0
    }
    response = client.post("/api/v1/engine/telemetry", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "received"}

    status_response = client.get("/api/v1/engine/status")
    assert status_response.status_code == 200
    data = status_response.json()
    assert "latest_telemetry" in data
    assert data["latest_telemetry"]["message"] == "Downloading qwen2.5:14b: 45%"
    assert data["latest_telemetry"]["progress"] == 45.0

def test_runner_telemetry_without_progress():
    client = TestClient(app)
    payload = {
        "message": "Cloudflare tunnel online: https://example.trycloudflare.com"
    }
    response = client.post("/api/v1/engine/telemetry", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "received"}

    status_response = client.get("/api/v1/engine/status")
    assert status_response.status_code == 200
    data = status_response.json()
    assert data["latest_telemetry"]["message"] == "Cloudflare tunnel online: https://example.trycloudflare.com"
    assert data["latest_telemetry"]["progress"] is None

def test_runner_telemetry_websocket_broadcast():
    client = TestClient(app)
    with client.websocket_connect("/api/v1/debate-stream") as websocket:
        # Initial greeting from debate stream
        greeting = websocket.receive_text()
        assert "SYSTEM" in greeting

        # Trigger telemetry post
        post_response = client.post(
            "/api/v1/engine/telemetry",
            json={"message": "Model download complete.", "progress": 100.0}
        )
        assert post_response.status_code == 200

        # Receive streamed telemetry log over WebSocket
        ws_msg = websocket.receive_text()
        assert "[KAGGLE_RUNNER] Model download complete. (100.0%)" in ws_msg

def test_engine_initial_offline_state_and_online_transition():
    from core.config import EngineState
    client = TestClient(app)
    
    # Ensure offline initially
    EngineState.url = None
    status_response = client.get("/api/v1/engine/status")
    assert status_response.status_code == 200
    data = status_response.json()
    assert data["status"] == "offline"
    assert data["active_engine"] is None

    # Update URL via set-url
    set_resp = client.post("/api/v1/engine/set-url", json={"url": "https://test-tunnel.trycloudflare.com"})
    assert set_resp.status_code == 200
    assert set_resp.json()["active_engine"] == "https://test-tunnel.trycloudflare.com"

    # Status should now be online with active_engine
    status_response = client.get("/api/v1/engine/status")
    assert status_response.status_code == 200
    data = status_response.json()
    assert data["status"] == "online"
    assert data["active_engine"] == "https://test-tunnel.trycloudflare.com"

    # Reset back to offline
    EngineState.url = None

if __name__ == "__main__":
    test_engine_initial_offline_state_and_online_transition()
    test_runner_telemetry_with_progress()
    test_runner_telemetry_without_progress()
    test_runner_telemetry_websocket_broadcast()
    print("All engine telemetry tests passed successfully!")
