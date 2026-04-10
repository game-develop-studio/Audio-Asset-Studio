"""스키마 검증 테스트."""
import pytest
from shared.schemas import validate_audio_input


def test_valid_minimal():
    data = {"assets": [{"asset_id": "click", "category": "sfx_ui"}]}
    result = validate_audio_input(data)
    assert result["assets"][0]["asset_id"] == "click"
    assert result["assets"][0]["category"] == "sfx_ui"
    assert result["assets"][0]["format"] == "ogg"


def test_valid_full():
    data = {
        "project": "test",
        "audio_palette": {"genre": "casual_fantasy"},
        "assets": [
            {
                "asset_id": "bgm_main",
                "category": "bgm_loop",
                "prompt": "cheerful theme",
                "duration_sec": 60,
                "loop": True,
                "bpm": 120,
                "format": "ogg",
                "variations": 2,
            }
        ],
    }
    result = validate_audio_input(data)
    assert result["assets"][0]["loop"] is True
    assert result["assets"][0]["bpm"] == 120


def test_invalid_format():
    data = {"assets": [{"asset_id": "x", "category": "sfx_ui", "format": "aac"}]}
    with pytest.raises(ValueError):
        validate_audio_input(data)


def test_invalid_duration():
    data = {"assets": [{"asset_id": "x", "category": "sfx_ui", "duration_ms": 0}]}
    with pytest.raises(ValueError):
        validate_audio_input(data)


def test_layers():
    data = {
        "assets": [{
            "asset_id": "hit",
            "category": "sfx_impact",
            "layers": ["impact", "sweetener", "tail"],
        }]
    }
    result = validate_audio_input(data)
    assert result["assets"][0]["layers"] == ["impact", "sweetener", "tail"]
