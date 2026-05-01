"""Daily Work recording bridge for Audio Asset Studio."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DAILY_WORK_SCRIPT = Path(
    os.getenv(
        "DAILY_WORK_LOGGER_SCRIPT",
        str(Path.home() / "slack-claude-bot" / "scripts" / "record-daily-work.js"),
    )
)


def _node_bin() -> str:
    configured = os.getenv("DAILY_WORK_NODE")
    if configured:
        return configured
    homebrew_node = Path("/opt/homebrew/bin/node")
    return str(homebrew_node) if homebrew_node.exists() else "node"


def _disabled() -> bool:
    return os.getenv("DAILY_WORK_LOG_DISABLE", "").lower() in {"1", "true", "yes", "on"}


def record_daily_work_event(
    summary: str,
    *,
    detail: str = "",
    tag: str = "프로젝트- 게임",
    event_type: str = "audio_asset",
    repo_path: str | Path = ROOT,
) -> bool:
    if _disabled():
        return False

    script = Path(os.getenv("DAILY_WORK_LOGGER_SCRIPT", str(DEFAULT_DAILY_WORK_SCRIPT))).expanduser()
    if not script.exists():
        return False

    cmd = [
        _node_bin(),
        str(script),
        "--summary",
        summary,
        "--tag",
        tag,
        "--repo",
        str(repo_path),
        "--event-type",
        event_type,
        "--quiet",
    ]
    if detail:
        cmd.extend(["--detail", detail])

    try:
        completed = subprocess.run(
            cmd,
            check=False,
            timeout=20,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return False
    return completed.returncode == 0
