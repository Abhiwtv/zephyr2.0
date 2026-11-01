#!/usr/bin/env python3
"""
=============================================================================
Zephyr 2.0 / NetCoop AI - Headless Kaggle GPU Batch Runner (VERBOSE + TELEMETRY)
=============================================================================
Deploys high-throughput Ollama serving Qwen2.5-14B on Kaggle GPU (T4 / P100),
emits real-time boot and model download telemetry to the FastAPI backend,
and establishes an encrypted Cloudflare Tunnel back to the Oracle VM Control Plane.
"""

import subprocess
import time
import os
import re
import sys
import json
import urllib.request
import urllib.error
from typing import Optional

MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")
CLOUDFLARE_LOG = "cloudflared.log"
OLLAMA_LOG = "ollama.log"
API_URL = os.environ.get("ZEPHYR_TELEMETRY_URL", "https://zephyr.sslip.io/api/v1/engine/telemetry")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "https://ntfy.sh/zephyr-gpu-status-k92a")

def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def broadcast_status(msg: str, prog: Optional[float] = None):
    """Pushes telemetry events outward to the FastAPI backend without crashing on network error."""
    try:
        payload = {"message": msg}
        if prog is not None:
            payload["progress"] = float(prog)
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            API_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            pass
    except Exception:
        # Fire and forget; never crash the runner if telemetry network delivery fails
        pass

def sh(cmd: str, check: bool = False, stream: bool = True) -> subprocess.CompletedProcess:
    log(f"[EXEC] {cmd}")
    if stream:
        r = subprocess.run(cmd, shell=True, stdout=sys.stdout, stderr=sys.stderr)
    else:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if r.returncode != 0:
            log(f"[!] Command failed (Code {r.returncode}): {cmd}")
            log(f"[STDOUT]\n{r.stdout[-1000:]}")
            log(f"[STDERR]\n{r.stderr[-1000:]}")
            if check:
                sys.exit(1)
    return r

def setup_environment():
    log("=== 1. Checking GPU Environment ===")
    broadcast_status("Checking GPU hardware and driver status...")
    r = subprocess.run("nvidia-smi -L", shell=True, capture_output=True, text=True)
    gpus = r.stdout.strip().splitlines()
    if not gpus:
        log("[WARNING] No GPU detected! Ensure GPU accelerator is enabled in Kaggle settings.")
        broadcast_status("Warning: No GPU detected in container.")
    else:
        log(f"GPUs found ({len(gpus)}):")
        for g in gpus:
            log(f"  -> {g}")
        broadcast_status(f"GPU detected: {gpus[0]}")

    log("=== 2. Installing System Dependencies ===")
    broadcast_status("Installing system dependencies (zstd, pciutils, lshw)...")
    sh("sudo apt-get update -qq && sudo apt-get install -y -qq zstd pciutils lshw curl wget")

    log("=== 3. Installing Ollama & Cloudflared ===")
    broadcast_status("Installing Ollama engine and Cloudflare tunnel client...")
    sh("curl -fsSL https://ollama.com/install.sh | sh")
    if not os.path.exists("cloudflared"):
        log("[INFO] Downloading cloudflared binary...")
        sh("wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared && chmod +x cloudflared")
    else:
        log("[INFO] cloudflared already exists.")
    broadcast_status("Environment dependencies ready.")

def pull_model_with_telemetry(model_name: str):
    log(f"=== 5. Pulling Model: {model_name} ===")
    log("[INFO] Streaming pull progress to backend and console...")
    broadcast_status(f"Starting download of {model_name}...", 0.0)

    pct_pattern = re.compile(r"(\d+)%")
    last_reported_pct = -1

    def handle_line(line: str):
        nonlocal last_reported_pct
        match = pct_pattern.search(line)
        if match:
            pct = int(match.group(1))
            if pct != last_reported_pct:
                last_reported_pct = pct
                broadcast_status(f"Downloading {model_name}: {pct}%", float(pct))
        elif any(kw in line.lower() for kw in ["manifest", "verifying", "writing", "success"]):
            broadcast_status(f"{model_name}: {line}")

    proc = subprocess.Popen(
        ["ollama", "pull", model_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    buffer = ""
    while True:
        char = proc.stdout.read(1)
        if not char and proc.poll() is not None:
            break
        if not char:
            continue
        if char in ("\r", "\n"):
            line = buffer.strip()
            buffer = ""
            if line:
                print(f"\r[OLLAMA] {line}", end="", flush=True)
                handle_line(line)
        else:
            buffer += char

    if buffer.strip():
        handle_line(buffer.strip())

    proc.wait()
    print()

    if proc.returncode == 0:
        log(f"✅ Successfully pulled {model_name}")
        broadcast_status(f"Model {model_name} downloaded successfully.", 100.0)
    else:
        log(f"[!] Failed to pull {model_name} (code {proc.returncode}). Trying fallback qwen2.5:14b...")
        broadcast_status(f"Failed to pull {model_name}, trying fallback qwen2.5:14b...")
        fallback_proc = subprocess.Popen(
            ["ollama", "pull", "qwen2.5:14b"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        buffer = ""
        while True:
            char = fallback_proc.stdout.read(1)
            if not char and fallback_proc.poll() is not None:
                break
            if not char:
                continue
            if char in ("\r", "\n"):
                line = buffer.strip()
                buffer = ""
                if line:
                    print(f"\r[OLLAMA FALLBACK] {line}", end="", flush=True)
                    handle_line(line)
            else:
                buffer += char
        fallback_proc.wait()
        print()
        if fallback_proc.returncode == 0:
            broadcast_status("Fallback model qwen2.5:14b downloaded successfully.", 100.0)

def start_ollama_service():
    log("=== 4. Launching Ollama Engine ===")
    broadcast_status("Launching Ollama daemon...")
    env = os.environ.copy()
    env["OLLAMA_HOST"] = "0.0.0.0:11434"
    env["OLLAMA_ORIGINS"] = "*"
    env["OLLAMA_KEEP_ALIVE"] = "24h"
    env["OLLAMA_NUM_PARALLEL"] = "4"
    env["OLLAMA_FLASH_ATTENTION"] = "1"
    env["OLLAMA_DEBUG"] = "1"

    log(f"[INFO] Starting 'ollama serve' in background. Logs routed to {OLLAMA_LOG}")
    ollama_proc = subprocess.Popen(
        ["ollama", "serve"],
        stdout=open(OLLAMA_LOG, "w"),
        stderr=subprocess.STDOUT,
        env=env
    )
    time.sleep(3)

    log("[INFO] Polling Ollama health endpoint...")
    broadcast_status("Awaiting Ollama health check response...")
    for i in range(15):
        try:
            with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as resp:
                if resp.status == 200:
                    log("✅ Ollama engine online at http://localhost:11434")
                    broadcast_status("Ollama engine online.")
                    break
        except Exception as e:
            log(f"[WAIT] Health check {i+1}/15 failed: {e}")
            time.sleep(1)
    else:
        log("❌ Ollama failed to start cleanly. Dumping last 30 lines of ollama.log:")
        broadcast_status("Ollama failed to start.")
        if os.path.exists(OLLAMA_LOG):
            sh(f"tail -n 30 {OLLAMA_LOG}")
        sys.exit(1)

    pull_model_with_telemetry(MODEL)

def start_cloudflare_tunnel() -> str:
    log("=== 6. Establishing Cloudflare Tunnel ===")
    broadcast_status("Establishing Cloudflare tunnel...")
    log(f"[INFO] Starting cloudflared tunnel. Logs routed to {CLOUDFLARE_LOG}")
    cf_proc = subprocess.Popen(
        ["./cloudflared", "tunnel", "--url", "http://localhost:11434", "--no-autoupdate"],
        stdout=open(CLOUDFLARE_LOG, "w"),
        stderr=subprocess.STDOUT
    )

    tunnel_url = None
    pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    
    log("[INFO] Scanning cloudflared.log for generated URL...")
    for i in range(30):
        time.sleep(1)
        if os.path.exists(CLOUDFLARE_LOG):
            content = open(CLOUDFLARE_LOG, "r", errors="ignore").read()
            matches = pattern.findall(content)
            if matches:
                tunnel_url = matches[0]
                log(f"[INFO] URL detected on attempt {i+1}")
                break

    if tunnel_url:
        log(f"\n" + "=" * 70)
        log(f"✅ TUNNEL ESTABLISHED SUCCESSFULLY:")
        log(f"ENGINE_URL={tunnel_url}")
        log(f"=" * 70 + "\n")
        
        broadcast_status(f"Cloudflare tunnel online: {tunnel_url}", 100.0)

        log("[INFO] Formatting POST request to ntfy.sh...")
        try:
            req = urllib.request.Request(
                NTFY_TOPIC, 
                data=tunnel_url.encode('utf-8'), 
                method="POST"
            )
            log(f"[INFO] Firing webhook to {NTFY_TOPIC} with payload: {tunnel_url}")
            with urllib.request.urlopen(req, timeout=10) as response:
                log(f"✅ Successfully broadcasted tunnel URL! HTTP Status: {response.status}")
        except urllib.error.URLError as e:
            log(f"❌ Failed to broadcast URL (Network/HTTP Error): {e}")
        except Exception as e:
            log(f"❌ Failed to broadcast URL (Unknown Error): {e}")
            
    else:
        log("❌ Warning: Could not auto-detect Cloudflare URL. Dumping cloudflared.log:")
        broadcast_status("Warning: Could not auto-detect Cloudflare URL.")
        if os.path.exists(CLOUDFLARE_LOG):
            sh(f"cat {CLOUDFLARE_LOG}")

    return tunnel_url

def keep_alive():
    log("=== 7. Service Running - Standing By for Inference Requests ===")
    broadcast_status("Kaggle GPU runner ready and standing by for inference.")
    try:
        checks = 0
        while True:
            time.sleep(60)
            checks += 1
            if checks % 5 == 0:
                log(f"[HEARTBEAT] Runner active for {checks} minutes.")
            
            try:
                with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
                    if r.status != 200:
                        log(f"[WARNING] Ollama heartbeat returned abnormal status: {r.status}")
            except Exception as e:
                log(f"[WARNING] Heartbeat connection error: {e}")
                
    except KeyboardInterrupt:
        log("Shutting down Kaggle runner...")

if __name__ == "__main__":
    setup_environment()
    start_ollama_service()
    start_cloudflare_tunnel()
    keep_alive()
