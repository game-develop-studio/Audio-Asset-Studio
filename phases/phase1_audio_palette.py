"""Phase 1: 오디오 팔레트 선택/생성.

사용자 입력의 audio_palette 필드 또는 --reference로 장르 톤을 결정하고,
이후 Phase에서 프롬프트 수식어·후처리 파라미터로 사용할 팔레트를 반환한다.
"""
from __future__ import annotations

import logging
from pathlib import Path

from shared.pipeline_helpers import read_yaml, write_json

log = logging.getLogger(__name__)

# 레퍼런스 게임 → 팔레트 매핑
REFERENCE_MAP = {
    "cookie-clicker": "casual_fantasy",
    "cookie_clicker": "casual_fantasy",
    "idle_heroes": "casual_fantasy",
    "vampire-survivors": "pixel_retro",
    "vampire_survivors": "pixel_retro",
    "shovel_knight": "pixel_retro",
    "2048": "minimalist_zen",
    "monument_valley": "minimalist_zen",
}


def _load_palette(palettes_dir: Path, name: str) -> dict:
    """팔레트 YAML 파일을 로드."""
    path = palettes_dir / f"{name}.yaml"
    if not path.exists():
        available = [p.stem for p in palettes_dir.glob("*.yaml")]
        raise ValueError(
            f"Unknown audio palette '{name}'. Available: {available}"
        )
    return read_yaml(path)


def _default_palette() -> dict:
    """팔레트 미지정 시 기본값."""
    return {
        "name": "default",
        "description": "기본 오디오 팔레트",
        "tone": {"brightness": "neutral", "warmth": "neutral", "attack": "medium", "decay": "medium"},
        "reverb": {"type": "small_room", "wet": 0.1, "decay_sec": 0.5},
        "eq_profile": {"low_cut_hz": 80, "high_shelf_hz": 8000, "high_shelf_db": 0.0},
        "prompt_modifiers": {"global_prefix": "", "sfx_prefix": "", "bgm_prefix": ""},
        "reference_games": [],
    }


def run(
    user_input: dict,
    palettes_dir: Path,
    out_dir: Path,
    reference: str | None = None,
) -> Path:
    """오디오 팔레트를 결정하고 JSON으로 저장.

    Args:
        user_input: 사용자 입력 dict
        palettes_dir: config/audio_palettes/ 경로
        out_dir: 출력 디렉토리
        reference: --reference 옵션 (게임 이름)

    Returns:
        생성된 팔레트 JSON 경로
    """
    palette_input = user_input.get("audio_palette", {})
    palette_name = None

    # 우선순위: --reference > audio_palette.genre > default
    if reference:
        palette_name = REFERENCE_MAP.get(reference.lower())
        if not palette_name:
            log.warning("Unknown reference '%s', falling back to genre or default", reference)

    if not palette_name and palette_input:
        palette_name = palette_input.get("genre")

    if palette_name and palettes_dir.exists():
        try:
            palette = _load_palette(palettes_dir, palette_name)
        except ValueError:
            log.warning("Palette '%s' not found, using default", palette_name)
            palette = _default_palette()
    else:
        palette = _default_palette()

    # 사용자 오버라이드 적용
    if palette_input.get("reverb"):
        palette.setdefault("reverb", {})["type"] = palette_input["reverb"]
    if palette_input.get("master_eq"):
        palette["master_eq_override"] = palette_input["master_eq"]

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "phase1_audio_palette.json"
    write_json(out, palette)
    log.info("Phase 1 done: palette=%s", palette.get("name", "default"))
    return out
