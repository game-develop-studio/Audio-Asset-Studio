"""Phase 1~3 통합 테스트."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_phase1_default_palette(tmp_path):
    from phases.phase1_audio_palette import run as run_p1

    user_input = {"assets": []}
    out = run_p1(user_input, ROOT / "config" / "audio_palettes", tmp_path)
    palette = json.loads(out.read_text())
    assert "tone" in palette
    assert "reverb" in palette


def test_phase1_reference_palette(tmp_path):
    from phases.phase1_audio_palette import run as run_p1

    user_input = {"assets": []}
    out = run_p1(user_input, ROOT / "config" / "audio_palettes", tmp_path, reference="cookie-clicker")
    palette = json.loads(out.read_text())
    assert palette["name"] == "casual_fantasy"


def test_phase1_genre_palette(tmp_path):
    from phases.phase1_audio_palette import run as run_p1

    user_input = {"audio_palette": {"genre": "pixel_retro"}, "assets": []}
    out = run_p1(user_input, ROOT / "config" / "audio_palettes", tmp_path)
    palette = json.loads(out.read_text())
    assert palette["name"] == "pixel_retro"


def test_phase2_normalizes_spec(tmp_path):
    from phases.phase1_audio_palette import run as run_p1
    from phases.phase2_audio_spec import run as run_p2

    user_input = {
        "audio_palette": {"genre": "casual_fantasy"},
        "assets": [
            {"asset_id": "click", "category": "sfx_ui", "prompt": "click sound", "variations": 3},
            {"asset_id": "bgm", "category": "bgm_loop", "prompt": "theme", "duration_sec": 30},
        ],
    }
    palette_path = run_p1(user_input, ROOT / "config" / "audio_palettes", tmp_path)
    spec_path = run_p2("test_proj", user_input, palette_path, tmp_path, ROOT / "config" / "categories.yaml")

    spec = json.loads(spec_path.read_text())
    assert spec["project_id"] == "test_proj"
    assert len(spec["assets"]) == 2
    assert spec["assets"][0]["duration_ms"] == 200  # sfx_ui default
    assert spec["assets"][1]["duration_ms"] == 30000  # 30 * 1000
    assert spec["estimated_cost_usd"] >= 0


def test_phase3_builds_jobs(tmp_path):
    from phases.phase1_audio_palette import run as run_p1
    from phases.phase2_audio_spec import run as run_p2
    from phases.phase3_prompt_build import run as run_p3

    user_input = {
        "assets": [
            {"asset_id": "hit", "category": "sfx_impact", "prompt": "punch", "variations": 2, "layers": ["impact", "tail"]},
            {"asset_id": "bgm", "category": "bgm_loop", "prompt": "theme", "variations": 1},
        ],
    }
    palette_path = run_p1(user_input, ROOT / "config" / "audio_palettes", tmp_path)
    spec_path = run_p2("test", user_input, palette_path, tmp_path, ROOT / "config" / "categories.yaml")
    manifest_path = run_p3(spec_path, tmp_path)

    manifest = json.loads(manifest_path.read_text())
    # hit: 2 layers × 2 variations = 4 jobs
    # bgm: 1 × 1 = 1 job
    assert manifest["total_jobs"] == 5
    assert "hit" in manifest["assets_meta"]
    assert manifest["assets_meta"]["hit"]["layers"] == ["impact", "tail"]

    # job prompt에 레이어 힌트가 포함되어야 함
    impact_jobs = [j for j in manifest["jobs"] if "impact" in j["job_id"]]
    assert len(impact_jobs) == 2
    assert "impact" in impact_jobs[0]["prompt"].lower() or "hit" in impact_jobs[0]["prompt"].lower()


def test_phase2_unknown_category(tmp_path):
    from phases.phase1_audio_palette import run as run_p1
    from phases.phase2_audio_spec import run as run_p2

    user_input = {"assets": [{"asset_id": "x", "category": "nonexistent_cat"}]}
    palette_path = run_p1(user_input, ROOT / "config" / "audio_palettes", tmp_path)
    with pytest.raises(ValueError, match="Unknown audio category"):
        run_p2("test", user_input, palette_path, tmp_path, ROOT / "config" / "categories.yaml")
