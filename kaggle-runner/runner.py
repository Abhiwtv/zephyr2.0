#!/usr/bin/env python3
"""
=============================================================================
Zephyr 2.0 / NetCoop AI - Headless Kaggle GPU Batch Runner
=============================================================================
Deploys high-throughput Ollama / vLLM serving Qwen3-14B on Kaggle GPU (T4 / P100)
and establishes an encrypted Cloudflare Tunnel back to the Oracle VM Control Plane.
"""

import subprocess
import time
import os
import re
import sys
import urllib.request
import urllib.error

MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:14b")
CLOUDFLARE_LOG = "cloudflared.log"
OLLAMA_LOG = "ollama.log"

def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def sh(cmd: str, check: bool = False) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0 and check:
        log(f"[!] Command failed: {cmd}\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    return r

def setup_environment():
    log("=== 1. Checking GPU Environment ===")
    gpus = sh("nvidia-smi -L").stdout.strip().splitlines()
    if not gpus:
        log("[WARNING] No GPU detected! Ensure GPU accelerator is enabled in Kaggle settings.")
    else:
        log(f"GPUs found ({len(gpus)}):\n" + "\n".join(f"  - {g}" for g in gpus))

    log("=== 2. Installing System Dependencies ===")
    sh("sudo apt-get update -qq && sudo apt-get install -y -qq zstd pciutils lshw curl wget")

    log("=== 3. Installing Ollama & Cloudflared ===")
    sh("curl -fsSL https://ollama.com/install.sh | sh")
    if not os.path.exists("cloudflared"):
        sh("wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared && chmod +x cloudflared")

def start_ollama_service():
    log("=== 4. Launching Ollama Engine ===")
    env = os.environ.copy()
    env["OLLAMA_HOST"] = "0.0.0.0:11434"
    env["OLLAMA_ORIGINS"] = "*"
    env["OLLAMA_KEEP_ALIVE"] = "24h"
    env["OLLAMA_NUM_PARALLEL"] = "4"
    env["OLLAMA_FLASH_ATTENTION"] = "1"

    ollama_proc = subprocess.Popen(
        ["ollama", "serve"],
        stdout=open(OLLAMA_LOG, "w"),
        stderr=subprocess.STDOUT,
        env=env
    )
    time.sleep(3)

    # Health check
    for _ in range(15):
        try:
            with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as resp:
                if resp.status == 200:
                    log("Ollama engine online at http://localhost:11434")
                    break
        except Exception:
            time.sleep(1)
    else:
        log("[!] Ollama failed to start cleanly. Check logs:")
        if os.path.exists(OLLAMA_LOG):
            print(open(OLLAMA_LOG).read()[-1000:])
        sys.exit(1)

    log(f"=== 5. Pulling Model: {MODEL} ===")
    pull_proc = subprocess.run(["ollama", "pull", MODEL], capture_output=True, text=True)
    if pull_proc.returncode != 0:
        log(f"[!] Failed to pull {MODEL}. Trying fallback qwen2.5:14b...")
        subprocess.run(["ollama", "pull", "qwen2.5:14b"], check=False)

def start_cloudflare_tunnel() -> str:
    log("=== 6. Establishing Cloudflare Tunnel ===")
    cf_proc = subprocess.Popen(
        ["./cloudflared", "tunnel", "--url", "http://localhost:11434", "--no-autoupdate"],
        stdout=open(CLOUDFLARE_LOG, "w"),
        stderr=subprocess.STDOUT
    )

    tunnel_url = None
    pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    
    # Wait for tunnel URL in log
    for _ in range(30):
        time.sleep(1)
        if os.path.exists(CLOUDFLARE_LOG):
            content = open(CLOUDFLARE_LOG, "r", errors="ignore").read()
            matches = pattern.findall(content)
            if matches:
                tunnel_url = matches[0]
                break

    if tunnel_url:
        log(f"\n" + "=" * 70)
        log(f"TUNNEL ESTABLISHED SUCCESSFULLY:")
        log(f"ENGINE_URL={tunnel_url}")
        log(f"Copy this into your Zephyr 2.0 .env file as ENGINE_URL")
        log(f"=" * 70 + "\n")
    else:
        log("[!] Warning: Could not auto-detect Cloudflare URL. Check cloudflared.log")
        if os.path.exists(CLOUDFLARE_LOG):
            print(open(CLOUDFLARE_LOG).read()[-1000:])

    return tunnel_url

def keep_alive():
    log("=== 7. Service Running - Standing By for Inference Requests ===")
    try:
        while True:
            time.sleep(60)
            # Periodic heartbeat check
            try:
                with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
                    if r.status != 200:
                        log("[WARNING] Ollama heartbeat failed.")
            except Exception as e:
                log(f"[WARNING] Heartbeat error: {e}")
    except KeyboardInterrupt:
        log("Shutting down Kaggle runner...")

if __name__ == "__main__":
    setup_environment()
    start_ollama_service()
    start_cloudflare_tunnel()
    keep_alive()
