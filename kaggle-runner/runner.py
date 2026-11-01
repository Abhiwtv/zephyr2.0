#!/usr/bin/env python3
"""
=============================================================================
Zephyr 2.0 / NetCoop AI - Headless Kaggle GPU Batch Runner (VERBOSE)
=============================================================================
Deploys high-throughput Ollama serving Qwen2.5-14B on Kaggle GPU (T4 / P100)
and establishes an encrypted Cloudflare Tunnel back to the Oracle VM Control Plane.
"""

import subprocess
import time
import os
import re
import sys
import urllib.request
import urllib.error

MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")
CLOUDFLARE_LOG = "cloudflared.log"
OLLAMA_LOG = "ollama.log"

def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def sh(cmd: str, check: bool = False, stream: bool = True) -> subprocess.CompletedProcess:
    log(f"[EXEC] {cmd}")
    if stream:
        # Streams directly to Kaggle's console so you can watch progress live
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
    # Capture output for parsing, but print it verbosely
    r = subprocess.run("nvidia-smi -L", shell=True, capture_output=True, text=True)
    gpus = r.stdout.strip().splitlines()
    if not gpus:
        log("[WARNING] No GPU detected! Ensure GPU accelerator is enabled in Kaggle settings.")
    else:
        log(f"GPUs found ({len(gpus)}):")
        for g in gpus:
            log(f"  -> {g}")

    log("=== 2. Installing System Dependencies ===")
    sh("sudo apt-get update -qq && sudo apt-get install -y -qq zstd pciutils lshw curl wget")

    log("=== 3. Installing Ollama & Cloudflared ===")
    sh("curl -fsSL https://ollama.com/install.sh | sh")
    if not os.path.exists("cloudflared"):
        log("[INFO] Downloading cloudflared binary...")
        sh("wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared && chmod +x cloudflared")
    else:
        log("[INFO] cloudflared already exists.")

def start_ollama_service():
    log("=== 4. Launching Ollama Engine ===")
    env = os.environ.copy()
    env["OLLAMA_HOST"] = "0.0.0.0:11434"
    env["OLLAMA_ORIGINS"] = "*"
    env["OLLAMA_KEEP_ALIVE"] = "24h"
    env["OLLAMA_NUM_PARALLEL"] = "4"
    env["OLLAMA_FLASH_ATTENTION"] = "1"
    env["OLLAMA_DEBUG"] = "1"  # Force verbose Ollama internal logs

    log(f"[INFO] Starting 'ollama serve' in background. Logs routed to {OLLAMA_LOG}")
    ollama_proc = subprocess.Popen(
        ["ollama", "serve"],
        stdout=open(OLLAMA_LOG, "w"),
        stderr=subprocess.STDOUT,
        env=env
    )
    time.sleep(3)

    log("[INFO] Polling Ollama health endpoint...")
    for i in range(15):
        try:
            with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as resp:
                if resp.status == 200:
                    log("✅ Ollama engine online at http://localhost:11434")
                    break
        except Exception as e:
            log(f"[WAIT] Health check {i+1}/15 failed: {e}")
            time.sleep(1)
    else:
        log("❌ Ollama failed to start cleanly. Dumping last 30 lines of ollama.log:")
        if os.path.exists(OLLAMA_LOG):
            sh(f"tail -n 30 {OLLAMA_LOG}")
        sys.exit(1)

    log(f"=== 5. Pulling Model: {MODEL} ===")
    log("[INFO] Streaming pull progress to console. This may take a few minutes...")
    # stream=True ensures you see the download progress bar live in Kaggle logs
    pull_proc = sh(f"ollama pull {MODEL}", stream=True)
    if pull_proc.returncode != 0:
        log(f"[!] Failed to pull {MODEL}. Trying fallback qwen2.5:14b...")
        sh("ollama pull qwen2.5:14b", stream=True)

def start_cloudflare_tunnel() -> str:
    log("=== 6. Establishing Cloudflare Tunnel ===")
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
        
        log("[INFO] Formatting POST request to ntfy.sh...")
        try:
            req = urllib.request.Request(
                "https://ntfy.sh/zephyr-gpu-status-k92a", 
                data=tunnel_url.encode('utf-8'), 
                method="POST"
            )
            log(f"[INFO] Firing webhook to https://ntfy.sh/zephyr-gpu-status-k92a with payload: {tunnel_url}")
            with urllib.request.urlopen(req, timeout=10) as response:
                log(f"✅ Successfully broadcasted tunnel URL! HTTP Status: {response.status}")
        except urllib.error.URLError as e:
            log(f"❌ Failed to broadcast URL (Network/HTTP Error): {e}")
        except Exception as e:
            log(f"❌ Failed to broadcast URL (Unknown Error): {e}")
            
    else:
        log("❌ Warning: Could not auto-detect Cloudflare URL. Dumping cloudflared.log:")
        if os.path.exists(CLOUDFLARE_LOG):
            sh(f"cat {CLOUDFLARE_LOG}")

    return tunnel_url

def keep_alive():
    log("=== 7. Service Running - Standing By for Inference Requests ===")
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