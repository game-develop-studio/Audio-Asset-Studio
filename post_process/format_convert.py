"""포맷 변환 — WAV→OGG/MP3, 샘플레이트/비트뎁스."""
from __future__ import annotations

import functools
import logging
import shutil
import subprocess
from pathlib import Path

from pydub import AudioSegment

log = logging.getLogger(__name__)

FORMAT_PARAMS = {
    "ogg": {"codec": "libvorbis", "parameters": ["-q:a", "6"]},
    "mp3": {"codec": "libmp3lame", "parameters": ["-q:a", "2"]},
    "wav": {},
    "flac": {},
}

CODEC_FALLBACKS = {
    "ogg": ["libvorbis", "libopus", "vorbis"],
    "mp3": ["libmp3lame"],
}


@functools.lru_cache(maxsize=1)
def _available_encoders() -> set[str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return set()
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception as exc:
        log.warning("Failed to inspect ffmpeg encoders: %s", exc)
        return set()

    encoders: set[str] = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("A"):
            encoders.add(parts[1])
    return encoders


def _resolve_params(target_format: str) -> dict:
    params = dict(FORMAT_PARAMS.get(target_format, {}))
    codec = params.get("codec")
    if not codec:
        return params

    available = _available_encoders()
    if not available or codec in available:
        return params

    for candidate in CODEC_FALLBACKS.get(target_format, []):
        if candidate in available:
            params["codec"] = candidate
            if candidate == "libopus":
                params["parameters"] = ["-b:a", "96k"]
            if candidate == "vorbis":
                params["parameters"] = ["-strict", "-2", *params.get("parameters", [])]
            log.info("Using ffmpeg codec fallback for %s: %s", target_format, candidate)
            return params

    log.warning("No preferred codec available for %s; falling back to ffmpeg default", target_format)
    params.pop("codec", None)
    return params


def convert_format(
    audio_path: Path,
    target_format: str = "ogg",
    sample_rate: int = 44100,
    channels: int | None = None,
    output_path: Path | None = None,
) -> Path:
    """오디오 파일을 target_format으로 변환."""
    audio = AudioSegment.from_file(str(audio_path))

    # 샘플레이트 변환
    if audio.frame_rate != sample_rate:
        audio = audio.set_frame_rate(sample_rate)

    # 채널 변환
    if channels:
        audio = audio.set_channels(channels)

    out = output_path or audio_path.with_suffix(f".{target_format}")
    params = _resolve_params(target_format)
    audio.export(
        str(out),
        format=target_format,
        codec=params.get("codec"),
        parameters=params.get("parameters"),
    )
    log.info(
        "Converted %s → %s (%d Hz, %d ch)",
        audio_path.name, out.name, sample_rate, audio.channels,
    )
    return out
