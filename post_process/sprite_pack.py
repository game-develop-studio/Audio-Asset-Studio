"""오디오 스프라이트 팩 — 여러 SFX를 하나의 파일로 합침."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from pydub import AudioSegment

log = logging.getLogger(__name__)

SILENCE_GAP_MS = 100  # 클립 간 간격


def pack_sprites(
    audio_files: list[Path],
    output_path: Path,
    gap_ms: int = SILENCE_GAP_MS,
) -> tuple[Path, Path]:
    """여러 오디오 파일을 하나의 스프라이트로 합치고 매니페스트(JSON)를 생성.

    Returns:
        (오디오 스프라이트 경로, 매니페스트 JSON 경로)
    """
    gap = AudioSegment.silent(duration=gap_ms, frame_rate=44100)
    sprite = AudioSegment.empty()
    manifest: dict[str, dict] = {}
    offset = 0

    for f in audio_files:
        seg = AudioSegment.from_file(str(f))
        manifest[f.stem] = {"start_ms": offset, "end_ms": offset + len(seg)}
        sprite += seg + gap
        offset += len(seg) + gap_ms

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sprite.export(str(output_path), format=output_path.suffix.lstrip("."))

    manifest_path = output_path.with_suffix(".json")
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    log.info("Packed %d clips → %s (%dms total)", len(audio_files), output_path.name, len(sprite))
    return output_path, manifest_path
