"""Demucs 기반 stems 분리 + 적응형 BGM 인텐시티 레이어 자동 생성.

intensity_layer 전략:
    low:    bass + other (minus drums, minus vocals)
    medium: + drums (soft)
    high:   full mix (모든 stem)
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def split_stems(
    audio_path: Path,
    output_dir: Path,
    model: str = "htdemucs",
) -> dict[str, Path]:
    """Demucs CLI로 drums/bass/other/vocals 분리.

    Returns:
        {"drums": Path, "bass": Path, "other": Path, "vocals": Path}
    """
    if shutil.which("demucs") is None:
        raise RuntimeError("demucs CLI 미설치. `pip install demucs` 필요")

    output_dir.mkdir(parents=True, exist_ok=True)
    # demucs -n MODEL -o OUT SRC
    subprocess.run(
        ["demucs", "-n", model, "-o", str(output_dir), str(audio_path)],
        check=True,
    )
    # 출력: {output_dir}/{model}/{stem_name}/{basename}.wav
    base = audio_path.stem
    model_dir = output_dir / model / base
    if not model_dir.exists():
        raise RuntimeError(f"demucs 출력 누락: {model_dir}")

    stems: dict[str, Path] = {}
    for f in model_dir.glob("*.wav"):
        stems[f.stem] = f
    return stems


def build_intensity_layers(
    stems: dict[str, Path],
    output_dir: Path,
    base_name: str,
    levels: list[str] | None = None,
) -> dict[str, Path]:
    """stems 조합으로 low/mid/high 인텐시티 레이어 생성."""
    from pydub import AudioSegment

    levels = levels or ["low", "medium", "high"]
    output_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}

    def _mix(parts: list[Path], gains_db: list[float]) -> AudioSegment:
        mixed: AudioSegment | None = None
        for p, g in zip(parts, gains_db):
            seg = AudioSegment.from_file(str(p)).apply_gain(g)
            mixed = seg if mixed is None else mixed.overlay(seg)
        assert mixed is not None
        return mixed

    for level in levels:
        parts: list[Path] = []
        gains: list[float] = []
        if level == "low":
            for k in ("bass", "other"):
                if k in stems:
                    parts.append(stems[k])
                    gains.append(-2.0)
        elif level == "medium":
            for k, g in [("bass", -1.0), ("other", -1.0), ("drums", -4.0)]:
                if k in stems:
                    parts.append(stems[k])
                    gains.append(g)
        elif level == "high":
            for k in stems:
                parts.append(stems[k])
                gains.append(0.0)
        if not parts:
            continue
        mix = _mix(parts, gains)
        out_path = output_dir / f"{base_name}__{level}.wav"
        mix.export(str(out_path), format="wav")
        out[level] = out_path
    return out
