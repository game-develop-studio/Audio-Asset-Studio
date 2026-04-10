"""포맷 변환 — WAV→OGG/MP3, 샘플레이트/비트뎁스."""
from __future__ import annotations

import logging
from pathlib import Path

from pydub import AudioSegment

log = logging.getLogger(__name__)

FORMAT_PARAMS = {
    "ogg": {"codec": "libvorbis", "parameters": ["-q:a", "6"]},
    "mp3": {"codec": "libmp3lame", "parameters": ["-q:a", "2"]},
    "wav": {},
    "flac": {},
}


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
    params = FORMAT_PARAMS.get(target_format, {})
    audio.export(str(out), format=target_format, **params)
    log.info(
        "Converted %s → %s (%d Hz, %d ch)",
        audio_path.name, out.name, sample_rate, audio.channels,
    )
    return out
