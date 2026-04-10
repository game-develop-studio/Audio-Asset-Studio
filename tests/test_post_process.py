"""후처리 모듈 테스트."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pydub = pytest.importorskip("pydub")
from pydub import AudioSegment
from pydub.generators import Sine


def _make_test_wav(path: Path, duration_ms: int = 500, freq: int = 440) -> Path:
    """테스트용 WAV 파일 생성."""
    tone = Sine(freq).to_audio_segment(duration=duration_ms)
    tone.export(str(path), format="wav")
    return path


def test_normalize(tmp_path):
    from post_process.normalize import normalize

    wav = _make_test_wav(tmp_path / "test.wav")
    result = normalize(wav, target_dbfs=-20.0)
    audio = AudioSegment.from_file(str(result))
    assert abs(audio.dBFS - (-20.0)) < 1.0


def test_trim_silence(tmp_path):
    from post_process.trim import trim_silence

    # 앞뒤에 무음 추가
    silence = AudioSegment.silent(duration=500)
    tone = Sine(440).to_audio_segment(duration=300)
    audio = silence + tone + silence
    path = tmp_path / "silence.wav"
    audio.export(str(path), format="wav")

    result = trim_silence(path)
    trimmed = AudioSegment.from_file(str(result))
    assert len(trimmed) < len(audio)


def test_fade(tmp_path):
    from post_process.fade import apply_fade

    wav = _make_test_wav(tmp_path / "test.wav", duration_ms=1000)
    result = apply_fade(wav, fade_in_ms=50, fade_out_ms=100)
    assert result.exists()


def test_format_convert(tmp_path):
    from post_process.format_convert import convert_format

    wav = _make_test_wav(tmp_path / "test.wav")
    result = convert_format(wav, target_format="wav", sample_rate=22050)
    audio = AudioSegment.from_file(str(result))
    assert audio.frame_rate == 22050


def test_layer_mix(tmp_path):
    from post_process.layer_mix import mix_layers

    impact = _make_test_wav(tmp_path / "impact.wav", freq=200)
    sweet = _make_test_wav(tmp_path / "sweetener.wav", freq=800)
    tail = _make_test_wav(tmp_path / "tail.wav", freq=400)

    out = tmp_path / "mixed.wav"
    result = mix_layers(
        {"impact": impact, "sweetener": sweet, "tail": tail},
        out,
    )
    assert result.exists()
    audio = AudioSegment.from_file(str(result))
    assert len(audio) > 0


def test_sprite_pack(tmp_path):
    from post_process.sprite_pack import pack_sprites

    files = []
    for i in range(3):
        f = _make_test_wav(tmp_path / f"clip_{i}.wav", duration_ms=200)
        files.append(f)

    out = tmp_path / "sprite.wav"
    audio_path, manifest_path = pack_sprites(files, out)
    assert audio_path.exists()
    assert manifest_path.exists()

    import json
    manifest = json.loads(manifest_path.read_text())
    assert len(manifest) == 3
    assert "clip_0" in manifest
