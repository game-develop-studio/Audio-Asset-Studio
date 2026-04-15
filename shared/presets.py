"""디자이너-친화 프리셋 슬라이더 → 내부 파라미터 번역기.

디자이너가 "펀치 8, 밝기 6, 타이트함 7" 로 조정하면 내부에서:
    - 프롬프트 수식어 prepend/append
    - cfg_scale 조정
    - 레이어 구성 자동 결정
    - 포스트 체인 추가
로 변환됨.

카테고리별 슬라이더 축이 다름:
    sfx_impact: punch / brightness / tightness / weight
    sfx_ui:     brightness / tightness
    bgm_loop:   energy / warmth / complexity
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PresetKnobs:
    punch: int | None = None
    brightness: int | None = None
    tightness: int | None = None
    weight: int | None = None
    energy: int | None = None
    warmth: int | None = None
    complexity: int | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


# 각 축 0~10 스케일의 프롬프트 수식어 라이브러리
MODIFIER_LADDERS: dict[str, list[tuple[int, str]]] = {
    "punch": [
        (2, "soft attack"),
        (5, "medium punch, controlled hit"),
        (8, "heavy punch, powerful attack, aggressive transient"),
        (10, "massive impact, bone-crushing, maximum weight"),
    ],
    "brightness": [
        (2, "dark, warm, rolled-off highs"),
        (5, "balanced tone"),
        (8, "bright, crisp highs, airy"),
        (10, "piercing brightness, sparkling top end"),
    ],
    "tightness": [
        (2, "loose, open, reverberant"),
        (5, "medium tail"),
        (8, "tight, dry, short decay"),
        (10, "extremely tight, surgical, no tail"),
    ],
    "weight": [
        (2, "light, delicate"),
        (5, "medium body"),
        (8, "heavy, thick low end, rumbling"),
        (10, "massive sub weight, earth-shaking"),
    ],
    "energy": [
        (2, "calm, relaxed, slow tempo"),
        (5, "steady groove"),
        (8, "driving, energetic, uptempo"),
        (10, "frenetic, intense, maximum energy"),
    ],
    "warmth": [
        (2, "cold, digital, clinical"),
        (5, "natural tone"),
        (8, "warm, analog, rich"),
        (10, "lush, vintage, saturated warmth"),
    ],
    "complexity": [
        (2, "minimal, sparse instrumentation"),
        (5, "moderate arrangement"),
        (8, "dense, layered, rich texture"),
        (10, "maximal arrangement, orchestral complexity"),
    ],
}


def _pick_modifier(axis: str, value: int) -> str | None:
    if axis not in MODIFIER_LADDERS or value is None:
        return None
    ladder = MODIFIER_LADDERS[axis]
    # 가장 가까운 임계 라벨
    best = ladder[0][1]
    for threshold, label in ladder:
        if value >= threshold:
            best = label
    # 3 이하는 '약한' 버전만 쓰고, 그 이하면 무시
    if value < 3 and axis not in ("punch", "weight"):
        return None
    return best


# 카테고리별 허용 축
CATEGORY_AXES: dict[str, list[str]] = {
    "sfx_impact":       ["punch", "weight", "brightness", "tightness"],
    "sfx_ui":           ["brightness", "tightness"],
    "sfx_reward":       ["brightness", "energy"],
    "sfx_ambient":      ["warmth", "complexity"],
    "sfx_character":    ["weight", "brightness"],
    "sfx_notification": ["brightness", "tightness"],
    "bgm_loop":         ["energy", "warmth", "complexity"],
    "bgm_stinger":      ["energy", "brightness"],
    "bgm_adaptive":     ["energy", "complexity"],
}


# 슬라이더가 cfg_scale에 주는 영향 (높을수록 프롬프트에 충실 → 안전한 사운드)
def _cfg_scale_from_knobs(knobs: PresetKnobs) -> float:
    # 극단값이 많을수록 cfg를 살짝 올려 프롬프트 집중
    extremity = sum(
        abs((v or 5) - 5) for v in knobs.to_dict().values()
    )
    return round(3.0 + min(extremity * 0.1, 2.0), 2)


def apply_to_asset(asset: dict, knobs_dict: dict[str, int] | None) -> dict:
    """에셋 dict + 슬라이더 값 → 확장된 에셋 dict.

    `knobs_dict`는 {"punch": 8, "brightness": 6, ...} 형태.
    asset["prompt"]에 수식어를 자연스럽게 주입하고, cfg_scale/layers도 조정.
    """
    if not knobs_dict:
        return asset

    category = asset.get("category", "")
    allowed = CATEGORY_AXES.get(category, list(MODIFIER_LADDERS))
    knobs = PresetKnobs(**{k: v for k, v in knobs_dict.items() if k in allowed})

    modifiers: list[str] = []
    for axis, value in knobs.to_dict().items():
        mod = _pick_modifier(axis, value)
        if mod:
            modifiers.append(mod)

    if modifiers:
        base = asset.get("prompt", "").strip()
        joined = ", ".join(modifiers)
        asset = {**asset, "prompt": f"{base}, {joined}" if base else joined}

    asset["cfg_scale"] = _cfg_scale_from_knobs(knobs)

    # punch 8↑ + weight 6↑ 이면 자동으로 레이어드 SFX 사용
    if category == "sfx_impact" and (knobs.punch or 0) >= 8 and (knobs.weight or 0) >= 6:
        asset.setdefault("layers", ["impact", "sweetener", "tail"])

    # complexity 8↑ bgm_loop → seed_farming 활성
    if category == "bgm_loop" and (knobs.complexity or 0) >= 8:
        asset.setdefault("seed_farming", 4)
        asset.setdefault("seed_farming_keep", 1)

    asset["_knobs"] = knobs.to_dict()
    return asset


def axes_for_category(category: str) -> list[str]:
    return CATEGORY_AXES.get(category, [])


def default_knobs(category: str) -> dict[str, int]:
    return {axis: 5 for axis in axes_for_category(category)}
