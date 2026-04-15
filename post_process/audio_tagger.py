"""CLAP 기반 자동 태깅 + 카테고리 매칭 검증.

생성된 오디오가 의도한 카테고리(예: sfx_impact)에 부합하는지 판별.
미스매치 시 phase4 리드라이브 트리거.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


# 카테고리 → 검증용 텍스트 프롬프트 (CLAP 텍스트 앵커)
CATEGORY_ANCHORS: dict[str, list[str]] = {
    "sfx_ui": [
        "short UI button click sound",
        "menu navigation beep",
        "clean interface feedback tone",
    ],
    "sfx_reward": [
        "coin pickup sound",
        "reward chime, positive feedback",
        "level up fanfare",
    ],
    "sfx_impact": [
        "heavy impact hit",
        "punch thud slam",
        "weapon impact sound effect",
    ],
    "sfx_ambient": [
        "ambient environment loop",
        "nature background sound",
        "atmospheric drone",
    ],
    "sfx_character": [
        "character voice grunt",
        "footstep sound",
        "creature vocalization",
    ],
    "sfx_notification": [
        "notification ping alert",
        "message received sound",
    ],
    "bgm_loop": [
        "looping background music",
        "instrumental music track",
        "game soundtrack melody",
    ],
    "bgm_stinger": [
        "short musical stinger",
        "cinematic hit sting",
    ],
    "bgm_adaptive": [
        "adaptive dynamic music layer",
    ],
}


def tag_audio(audio_path: Path, top_k: int = 5) -> list[tuple[str, float]]:
    """전체 카테고리 앵커와의 유사도 top-k."""
    from shared.scoring import clap_audio_embed, clap_text_embed

    labels: list[str] = []
    texts: list[str] = []
    for cat, anchors in CATEGORY_ANCHORS.items():
        for a in anchors:
            labels.append(cat)
            texts.append(a)

    audio_emb = clap_audio_embed([audio_path])[0]
    text_emb = clap_text_embed(texts)
    sims = (text_emb @ audio_emb) / (
        np.linalg.norm(text_emb, axis=1) * (np.linalg.norm(audio_emb) or 1e-9)
    )
    # 카테고리별 max 집계
    by_cat: dict[str, float] = {}
    for lbl, s in zip(labels, sims):
        by_cat[lbl] = max(by_cat.get(lbl, -1.0), float(s))
    ranked = sorted(by_cat.items(), key=lambda x: x[1], reverse=True)
    return ranked[:top_k]


def matches_category(audio_path: Path, category: str, threshold: float = 0.0) -> tuple[bool, float, list[tuple[str, float]]]:
    """카테고리 매칭 여부 + 점수 + 상위 랭킹 리턴.

    threshold: 해당 카테고리 점수가 이 값 이상이고 top1이어야 통과.
    """
    ranked = tag_audio(audio_path, top_k=5)
    top_cat, top_score = ranked[0]
    target_score = dict(ranked).get(category, -1.0)
    passed = (top_cat == category) and (target_score >= threshold)
    return passed, target_score, ranked


def batch_tag(paths: list[Path]) -> dict[str, list[tuple[str, float]]]:
    return {str(p): tag_audio(p) for p in paths}
