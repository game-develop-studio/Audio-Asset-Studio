"""대시보드에서 파이프라인을 서브프로세스로 실행하고 진행률 스트리밍."""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path
from queue import Empty, Queue


def run_pipeline(
    root: Path,
    project: str,
    input_file: str,
    phases: str | None = None,
    only: list[str] | None = None,
    force: bool = False,
    backend: str = "local",
    engine: str | None = None,
    loudness_target: float | None = None,
) -> subprocess.Popen:
    cmd = [sys.executable, "audio_studio.py",
           "--project", project, "--input", input_file, "--backend", backend]
    if phases:
        cmd += ["--phases", phases]
    if only:
        cmd += ["--only", ",".join(only)]
    if force:
        cmd.append("--force")
    if engine:
        cmd += ["--engine", engine]
    if loudness_target is not None:
        cmd += ["--loudness-target", str(loudness_target)]
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    return subprocess.Popen(
        cmd, cwd=str(root), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )


def stream(proc: subprocess.Popen, queue: Queue) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        queue.put(line.rstrip())
    queue.put(None)


def run_with_log(root: Path, log_callback, **kwargs) -> int:
    """실행하면서 log_callback(line)을 매 줄마다 호출. 종료코드 리턴."""
    proc = run_pipeline(root, **kwargs)
    q: Queue = Queue()
    t = threading.Thread(target=stream, args=(proc, q), daemon=True)
    t.start()
    while True:
        try:
            line = q.get(timeout=0.2)
        except Empty:
            if proc.poll() is not None:
                # drain
                while not q.empty():
                    line = q.get_nowait()
                    if line is not None:
                        log_callback(line)
                break
            continue
        if line is None:
            break
        log_callback(line)
    return proc.wait()


def format_cmd(**kwargs) -> str:
    """UI에서 보여줄 평문 명령."""
    parts = ["python audio_studio.py",
             f"--project {kwargs.get('project')}",
             f"--input {kwargs.get('input_file')}",
             f"--backend {kwargs.get('backend', 'local')}"]
    if kwargs.get("phases"):
        parts.append(f"--phases {kwargs['phases']}")
    if kwargs.get("only"):
        parts.append(f"--only {','.join(kwargs['only'])}")
    if kwargs.get("force"):
        parts.append("--force")
    if kwargs.get("engine"):
        parts.append(f"--engine {kwargs['engine']}")
    return " ".join(parts)
