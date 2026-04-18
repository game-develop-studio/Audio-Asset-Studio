"""대시보드 공용 세션/읽기 유틸."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path


def _rel_time(ts: float) -> str:
    now = dt.datetime.now().timestamp()
    delta = int(now - ts)
    if delta < 60:
        return f"{delta}초 전"
    if delta < 3600:
        return f"{delta // 60}분 전"
    if delta < 86400:
        return f"{delta // 3600}시간 전"
    return f"{delta // 86400}일 전"


def _count_statuses(report_path: Path) -> dict[str, int]:
    counts = {"generated": 0, "cached": 0, "failed": 0}
    if not report_path.exists():
        return counts
    try:
        data = json.loads(report_path.read_text())
        for r in data.get("results", []):
            s = r.get("status")
            if s in counts:
                counts[s] += 1
    except Exception:
        pass
    return counts


def load_projects(root: Path) -> list[dict]:
    out_dir = root / "output"
    if not out_dir.exists():
        return []
    projects: list[dict] = []
    for p in sorted(out_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if not p.is_dir():
            continue
        counts = _count_statuses(p / "phase4_generation_report.json")
        budget = None
        bf = p / "budget.json"
        if bf.exists():
            try:
                budget = float(json.loads(bf.read_text()).get("spent_usd", 0.0))
            except Exception:
                pass
        meta_palette = None
        pf = p / "phase1_audio_palette.json"
        if pf.exists():
            try:
                meta_palette = json.loads(pf.read_text()).get("palette", {}).get("name")
            except Exception:
                pass
        projects.append({
            "name": p.name,
            "path": str(p),
            "generated": counts["generated"],
            "cached": counts["cached"],
            "failed": counts["failed"],
            "budget_spent": budget,
            "mtime": p.stat().st_mtime,
            "mtime_rel": _rel_time(p.stat().st_mtime),
            "meta": {"palette": meta_palette},
        })
    return projects


def recent_activity(root: Path, limit: int = 10) -> list[dict]:
    items: list[dict] = []
    out_dir = root / "output"
    if not out_dir.exists():
        return items
    for p in out_dir.iterdir():
        if not p.is_dir():
            continue
        rp = p / "phase4_generation_report.json"
        if not rp.exists():
            continue
        try:
            data = json.loads(rp.read_text())
            when = _rel_time(rp.stat().st_mtime)
        except Exception:
            continue
        for r in data.get("results", [])[:limit]:
            items.append({
                "project": p.name,
                "asset_id": r.get("asset_id", "?"),
                "status": r.get("status", "?"),
                "when": when,
                "mtime": rp.stat().st_mtime,
            })
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items[:limit]


def daemon_badge() -> str:
    try:
        from shared.daemon import status
    except Exception:
        return "🔸 daemon: unknown"
    s = status()
    icon = "🟢" if s["running"] else "⚪"
    state = "running" if s["running"] else "idle"
    return f"{icon} model_server: **{state}**"


def project_dir(root: Path, name: str) -> Path:
    return root / "output" / name


def load_report(project_path: Path) -> dict | None:
    f = project_path / "phase4_generation_report.json"
    return json.loads(f.read_text()) if f.exists() else None


def load_manifest(project_path: Path) -> dict | None:
    f = project_path / "phase3_generation_manifest.json"
    return json.loads(f.read_text()) if f.exists() else None


def load_post_report(project_path: Path) -> dict | None:
    f = project_path / "phase5_post_process_report.json"
    return json.loads(f.read_text()) if f.exists() else None
