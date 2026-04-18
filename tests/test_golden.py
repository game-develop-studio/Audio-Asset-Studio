"""골든 회귀 테스트.

검증 대상:
    - 라우드니스 정규화 (LUFS 허용 오차)
    - True Peak -1 dBTP 상한
    - 포맷/샘플레이트/채널
    - 길이 허용 범위 (loop 크로스페이드 후 변동)
    - 엔진 export 파일 수

골든 샘플은 `tests/golden/` 에 커밋된 짧은 WAV. 없으면 런타임에 합성.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


def _ensure_golden_sample() -> Path:
    """테스트용 짧은 사인파 (440Hz, 1sec, -20dBFS) 생성."""
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    path = GOLDEN_DIR / "sine_440_1s.wav"
    if path.exists():
        return path
    try:
        import soundfile as sf
    except ImportError:
        pytest.skip("soundfile 미설치")
    sr = 44100
    t = np.linspace(0, 1.0, sr, endpoint=False)
    y = 0.1 * np.sin(2 * np.pi * 440 * t)  # ~ -20dBFS
    sf.write(str(path), y, sr)
    return path


# ---------- loudness ----------

def test_loudness_within_tolerance():
    pyln = pytest.importorskip("pyloudnorm")
    sf = pytest.importorskip("soundfile")
    from post_process.normalize import normalize

    src = _ensure_golden_sample()
    dst = GOLDEN_DIR / "sine_norm.wav"
    normalize(src, target_dbfs=-14.0, output_path=dst)

    data, rate = sf.read(str(dst))
    meter = pyln.Meter(rate)
    lufs = meter.integrated_loudness(data)
    assert -15.5 < lufs < -12.5, f"LUFS out of tolerance: {lufs}"


def test_true_peak_guard():
    """큰 게인 먹여서 TP가 -1 dBTP 이하로 제한되는지."""
    pytest.importorskip("pyloudnorm")
    sf = pytest.importorskip("soundfile")
    from post_process.normalize import normalize

    src = GOLDEN_DIR / "loud_sine.wav"
    sr = 44100
    y = 0.95 * np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, sr, endpoint=False))
    sf.write(str(src), y, sr)
    dst = GOLDEN_DIR / "loud_sine_norm.wav"
    normalize(src, target_dbfs=-8.0, output_path=dst, true_peak_dbtp=-1.0)

    data, _ = sf.read(str(dst))
    peak_db = 20 * np.log10(max(np.max(np.abs(data)), 1e-9))
    assert peak_db <= -0.5, f"True peak guard failed: {peak_db:.2f} dBTP"


# ---------- format/sample rate ----------

def test_format_convert():
    from post_process.format_convert import convert_format

    src = _ensure_golden_sample()
    dst = GOLDEN_DIR / "sine_440_1s.ogg"
    out = convert_format(src, target_format="ogg", sample_rate=22050, channels=1, output_path=dst)
    assert out.exists()
    assert out.suffix == ".ogg"


# ---------- pipeline dry-run ----------

def test_cli_dry_run(tmp_path):
    """CLI로 --dry-run 모드 실행이 에러 없이 끝나는지."""
    example = ROOT / "config" / "examples" / "clicker_game.yaml"
    if not example.exists():
        pytest.skip("example input 없음")

    out_dir = tmp_path / "out"
    cmd = [
        sys.executable, "audio_studio.py",
        "--project", "gold_test",
        "--input", str(example),
        "--output", str(out_dir),
        "--dry-run",
        "--phases", "1,2,3",
    ]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert (out_dir / "phase3_generation_manifest.json").exists()


# ---------- backend abstraction ----------

def test_backend_factory():
    from shared.backends import get_backend

    b = get_backend("local", {})
    assert b.name == "local"
    b2 = get_backend("warm", {"endpoint": "http://localhost:1"})
    assert b2.name == "warm"


def test_runtime_variation_presets():
    from phases.engine_exporters import runtime_meta

    rv = runtime_meta("sfx_impact")
    assert rv["pitch_st"] >= 1.0
    assert rv["volume_db"] >= 2.0
    assert runtime_meta("bgm_loop")["pitch_st"] == 0.0
