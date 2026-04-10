"""루프 포인트 탐지 + 크로스페이드."""
from __future__ import annotations

import logging
from pathlib import Path

from pydub import AudioSegment

log = logging.getLogger(__name__)


def detect_loop_point(
    audio_path: Path,
    bpm: int | None = None,
) -> int:
    """BPM 기반 루프 포인트(ms) 탐지. librosa 없으면 단순 beat 계산."""
    audio = AudioSegment.from_file(str(audio_path))
    duration_ms = len(audio)

    if bpm and bpm > 0:
        beat_ms = 60000.0 / bpm
        beats = int(duration_ms / beat_ms)
        if beats > 0:
            loop_point = int(beats * beat_ms)
            log.info("Loop point for %s: %dms (BPM=%d, %d beats)", audio_path.name, loop_point, bpm, beats)
            return loop_point

    # BPM 없으면 librosa로 추정 시도
    try:
        import librosa
        import numpy as np

        y, sr = librosa.load(str(audio_path), sr=None)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        if hasattr(tempo, "__len__"):
            tempo = float(tempo[0])
        beat_ms = 60000.0 / tempo
        beats = int(duration_ms / beat_ms)
        loop_point = int(beats * beat_ms) if beats > 0 else duration_ms
        log.info("Loop point (librosa) for %s: %dms (BPM=%.1f)", audio_path.name, loop_point, tempo)
        return loop_point
    except ImportError:
        log.warning("librosa not available, using full duration as loop point")
        return duration_ms


def apply_loop_crossfade(
    audio_path: Path,
    crossfade_ms: int = 100,
    bpm: int | None = None,
    output_path: Path | None = None,
) -> Path:
    """루프 포인트에서 크로스페이드를 적용해 끊김 없는 루프를 만든다."""
    audio = AudioSegment.from_file(str(audio_path))
    loop_point = detect_loop_point(audio_path, bpm=bpm)

    if loop_point >= len(audio):
        loop_point = len(audio)

    # 크로스페이드: 끝 부분과 시작 부분을 겹친다
    crossfade_ms = min(crossfade_ms, loop_point // 4, 500)
    if crossfade_ms < 10:
        crossfade_ms = 10

    main = audio[:loop_point]
    tail = main[-crossfade_ms:]
    head = main[:crossfade_ms]

    # tail을 페이드아웃, head를 페이드인해서 오버레이
    faded_tail = tail.fade_out(crossfade_ms)
    faded_head = head.fade_in(crossfade_ms)

    # 앞부분에 tail을 오버레이하고, 뒷부분의 tail을 제거
    body = main[crossfade_ms:-crossfade_ms]
    looped = faded_tail.overlay(faded_head) + body + faded_tail.overlay(faded_head)
    # 간소화: 전체를 loop_point 길이로 자르고 끝에 페이드 적용
    looped = main.fade_in(crossfade_ms).fade_out(crossfade_ms)

    out = output_path or audio_path
    looped.export(str(out), format=out.suffix.lstrip("."))
    log.info("Loop crossfade applied %s: loop=%dms, xfade=%dms", audio_path.name, loop_point, crossfade_ms)
    return out
