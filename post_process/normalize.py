"""라우드니스 정규화 (LUFS 기반 + True Peak 가드).

플랫폼별 타겟:
    mobile:  -14 LUFS (YouTube/Spotify급, 모바일 게임 표준)
    console: -16 LUFS (PS/Xbox 권장)
    pc:      -18 LUFS (여유 있는 헤드룸)
    broadcast: -23 LUFS (EBU R128)

True Peak: -1.0 dBTP 상한 (인터샘플 피크 방지) — 초과 시 자동 감쇠.
pyloudnorm 설치 시 정확한 ITU-R BS.1770 측정, 미설치 시 pydub dBFS 폴백.
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_TARGET_LUFS = -14.0
DEFAULT_TRUE_PEAK_DBTP = -1.0

PLATFORM_PRESETS: dict[str, float] = {
    "mobile": -14.0,
    "console": -16.0,
    "pc": -18.0,
    "broadcast": -23.0,
    "youtube": -14.0,
    "spotify": -14.0,
}


def _measure_lufs(data, rate: int) -> float:
    import pyloudnorm as pyln

    meter = pyln.Meter(rate)
    return float(meter.integrated_loudness(data))


def _measure_true_peak(data, rate: int) -> float:
    """True Peak (dBTP) — 4배 오버샘플링 후 피크."""
    import numpy as np

    # 4x upsample (naive zero-insert + lowpass via FFT)
    try:
        from scipy.signal import resample_poly

        up = resample_poly(data, 4, 1, axis=0 if data.ndim > 1 else -1)
    except ImportError:
        up = np.repeat(data, 4, axis=0 if data.ndim > 1 else -1)
    peak = float(np.max(np.abs(up)))
    if peak <= 0:
        return -120.0
    return 20.0 * float(np.log10(peak))


def normalize(
    audio_path: Path,
    target_dbfs: float = DEFAULT_TARGET_LUFS,   # 이름 유지 (하위 호환), 의미는 LUFS
    output_path: Path | None = None,
    true_peak_dbtp: float = DEFAULT_TRUE_PEAK_DBTP,
    platform: str | None = None,
) -> Path:
    """LUFS 타겟 + True Peak 가드로 정규화.

    Args:
        target_dbfs: 타겟 LUFS (e.g. -14). 하위호환 위해 이름은 dbfs.
        platform: 지정 시 PLATFORM_PRESETS 우선 적용.
    """
    target = PLATFORM_PRESETS[platform] if platform in PLATFORM_PRESETS else target_dbfs
    out = output_path or audio_path

    try:
        import soundfile as sf
        import numpy as np

        data, rate = sf.read(str(audio_path))
        current_lufs = _measure_lufs(data, rate)
        gain_db = target - current_lufs
        gain_lin = 10 ** (gain_db / 20.0)
        out_data = data * gain_lin

        # True Peak 가드
        tp = _measure_true_peak(out_data, rate)
        if tp > true_peak_dbtp:
            extra = tp - true_peak_dbtp
            out_data *= 10 ** (-extra / 20.0)
            log.info("TP guard: -%.2f dB (tp %.2f → %.2f)", extra, tp, true_peak_dbtp)

        sf.write(str(out), out_data, rate, subtype="PCM_16" if out.suffix == ".wav" else None)
        log.info(
            "Normalized %s: %.1f LUFS → %.1f LUFS (platform=%s)",
            audio_path.name, current_lufs, target, platform or "custom",
        )
        return out

    except ImportError:
        # 폴백: pydub dBFS (정확도 낮음)
        from pydub import AudioSegment
        audio = AudioSegment.from_file(str(audio_path))
        audio = audio.apply_gain(target - audio.dBFS)
        audio.export(str(out), format=out.suffix.lstrip("."))
        log.warning("pyloudnorm 미설치 — pydub dBFS 폴백 (%s: → %.1f dBFS)", audio_path.name, target)
        return out
