"""
Interactive WebSocket & Live REST Tester for NetCoop / Zephyr Backend
======================================================================
Usage:
    python test_stream.py

This script:
1. Connects to ws://localhost:8000/api/v1/debate-stream.
2. Listens for live multi-agent debate events.
3. Sends an anomalous telemetry payload to POST /api/v1/diagnose.
4. Streams the real-time token trace and prints the final DiagnosticReport.
"""

import asyncio
import json
import urllib.request
import websockets

WS_URL = "ws://localhost:8000/api/v1/debate-stream"
REST_URL = "http://localhost:8000/api/v1/diagnose"

TEST_PAYLOAD = {
    "timestamp": "2026-11-01T04:30:00Z",
    "device_id": "CS_DEPT_CORE_SW",
    "metrics": {
        "cpu_utilization_pct": 100.0,
        "interface_errors": 0.0,
        "queue_drops": 45000.0,
        "link_utilization_pct": 85.0,
        "packet_loss_pct": 18.0,
        "latency_ms": 950.0,
        "jitter_ms": 400.0,
        "dns_latency_ms": 250.0,
        "dhcp_pool_utilization_pct": 60.0
    }
}

async def main():
    print(f"[*] Connecting to WebSocket: {WS_URL} ...")
    
    async with websockets.connect(WS_URL) as ws:
        print("[+] WebSocket Connected! Listening for live debate logs...\n")
        
        # Receive welcome / handshake frame
        handshake = await ws.recv()
        print(f"[Handshake] {handshake}\n")

        # Function to trigger the POST request after 0.5s delay
        async def trigger_post():
            await asyncio.sleep(0.5)
            print("[*] Dispatching POST /api/v1/diagnose with anomalous telemetry...")
            data_bytes = json.dumps(TEST_PAYLOAD).encode("utf-8")
            req = urllib.request.Request(
                REST_URL,
                data=data_bytes,
                headers={"Content-Type": "application/json"}
            )
            # Run blocking urllib call in thread pool to not block asyncio loop
            loop = asyncio.get_running_loop()
            resp_bytes = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req).read())
            report = json.loads(resp_bytes.decode("utf-8"))
            return report

        # Launch REST request as background task
        post_task = asyncio.create_task(trigger_post())

        # Listen for real-time WebSocket frames until consensus finalized
        while True:
            try:
                # 3-second timeout for next frame once post completes
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                print(f"[LIVE WS] {msg}")
                if "FINALIZED" in msg or "Consensus achieved" in msg:
                    break
            except asyncio.TimeoutError:
                if post_task.done():
                    break

        report = await post_task
        print("\n" + "=" * 60)
        print("[*] FINAL REST DIAGNOSTIC REPORT RETURNED:")
        print("=" * 60)
        print(json.dumps(report, indent=2))
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
