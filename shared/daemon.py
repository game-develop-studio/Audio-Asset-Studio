"""model_server 자동 라이프사이클.

- 이미 running이면 재사용
- 없으면 background로 기동 후 /health poll
- pidfile: ~/.audio_asset_studio/model_server.pid
- idle timeout(기본 30분)로 자동 종료 옵션

디자이너가 터미널 2개 안 띄우도록, CLI 첫 호출 시 알아서 시작.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger(__name__)

STATE_DIR = Path(os.environ.get(
    "AAS_STATE_DIR",
    str(Path.home() / ".audio_asset_studio"),
))
STATE_DIR.mkdir(parents=True, exist_ok=True)
PID_FILE = STATE_DIR / "model_server.pid"
LOG_FILE = STATE_DIR / "model_server.log"

DEFAULT_HOST = os.environ.get("MODEL_SERVER_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("MODEL_SERVER_PORT", "8765"))


def _endpoint(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    return f"http://{host}:{port}"


def is_running(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = 2.0) -> bool:
    try:
        import requests
    except ImportError:
        return False
    try:
        r = requests.get(f"{_endpoint(host, port)}/health", timeout=timeout)
        return r.ok
    except Exception:
        return False


def _read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return None


def _proc_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def ensure_running(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    warm_models: list[str] | None = None,
    wait_ready_sec: int = 120,
) -> str:
    """서버가 없으면 background로 기동, 있으면 재사용. endpoint 리턴."""
    if is_running(host, port):
        log.info("model_server already running at %s:%d", host, port)
        if warm_models:
            _warm(host, port, warm_models)
        return _endpoint(host, port)

    log.info("Starting model_server on %s:%d (background)", host, port)
    env = {**os.environ, "MODEL_SERVER_HOST": host, "MODEL_SERVER_PORT": str(port)}
    with open(LOG_FILE, "ab") as log_f:
        p = subprocess.Popen(
            [sys.executable, "-m", "shared.model_server"],
            stdout=log_f, stderr=log_f,
            env=env,
            start_new_session=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
    PID_FILE.write_text(str(p.pid))

    # ready-wait
    t0 = time.time()
    while time.time() - t0 < wait_ready_sec:
        if is_running(host, port, timeout=1.0):
            log.info("model_server ready (pid=%d) after %.1fs", p.pid, time.time() - t0)
            if warm_models:
                _warm(host, port, warm_models)
            return _endpoint(host, port)
        if p.poll() is not None:
            break
        time.sleep(0.5)

    raise RuntimeError(
        f"model_server 기동 실패. 로그: {LOG_FILE}\n"
        f"직접 실행해서 에러 확인: python -m shared.model_server"
    )


def _warm(host: str, port: int, models: list[str]) -> None:
    import requests

    try:
        requests.post(f"{_endpoint(host, port)}/warm", json={"models": models}, timeout=600)
    except Exception as e:
        log.warning("warm 실패: %s", e)


def stop(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, grace_sec: int = 5) -> bool:
    pid = _read_pid()
    if not pid or not _proc_alive(pid):
        if PID_FILE.exists():
            PID_FILE.unlink()
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    t0 = time.time()
    while time.time() - t0 < grace_sec:
        if not _proc_alive(pid):
            break
        time.sleep(0.3)
    if _proc_alive(pid):
        os.kill(pid, signal.SIGKILL)
    if PID_FILE.exists():
        PID_FILE.unlink()
    return True


def status() -> dict:
    pid = _read_pid()
    running = is_running()
    return {
        "running": running,
        "pid": pid,
        "endpoint": _endpoint(),
        "log_file": str(LOG_FILE),
    }
