"""CLAP 임베딩 기반 오디오-텍스트 유사도 + 라우드니스 점수.

CLAP 로드는 무겁기 때문에 프로세스 내 싱글톤으로 유지.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_clap():
    """laion-clap 모델 싱글톤 로드."""
    import laion_clap

    model = laion_clap.CLAP_Module(enable_fusion=False, amodel="HTSAT-base")
    model.load_ckpt()
    return model


def clap_text_embed(texts: list[str]) -> np.ndarray:
    model = _get_clap()
    emb = model.get_text_embedding(texts, use_tensor=False)
    return np.asarray(emb)


def clap_audio_embed(paths: list[Path]) -> np.ndarray:
    model = _get_clap()
    emb = model.get_audio_embedding_from_filelist([str(p) for p in paths], use_tensor=False)
    return np.asarray(emb)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1e-9
    return float(np.dot(a, b) / denom)


def similarity_to_prompt(audio_path: Path, prompt: str) -> float:
    """-1..1 범위 cosine."""
    a = clap_audio_embed([audio_path])[0]
    t = clap_text_embed([prompt])[0]
    return _cosine(a, t)


def loudness_score(audio_path: Path, target_lufs: float = -14.0) -> float:
    """LUFS 타겟과의 근접도 0..1. 타겟 ±1 LUFS 안이면 만점에 가깝게."""
    try:
        import pyloudnorm as pyln
        import soundfile as sf

        data, rate = sf.read(str(audio_path))
        meter = pyln.Meter(rate)
        lufs = meter.integrated_loudness(data)
        if np.isinf(lufs) or np.isnan(lufs):
            return 0.0
        return float(max(0.0, 1.0 - abs(lufs - target_lufs) / 10.0))
    except Exception as e:
        log.warning("loudness_score failed for %s: %s", audio_path, e)
        return 0.5


def combined_score(
    audio_path: Path,
    prompt: str,
    target_lufs: float = -14.0,
    w_sim: float = 0.75,
    w_loud: float = 0.25,
) -> dict:
    sim = similarity_to_prompt(audio_path, prompt)
    loud = loudness_score(audio_path, target_lufs)
    # cosine을 0..1 로 스쿼시
    sim_01 = (sim + 1.0) / 2.0
    total = w_sim * sim_01 + w_loud * loud
    return {"similarity": sim, "loudness_score": loud, "total": total}


def pick_best(
    candidates: list[Path],
    prompt: str,
    target_lufs: float = -14.0,
) -> tuple[Path, dict]:
    """후보 중 최고 스코어 리턴."""
    if not candidates:
        raise ValueError("candidates empty")
    scored = [(p, combined_score(p, prompt, target_lufs)) for p in candidates]
    scored.sort(key=lambda x: x[1]["total"], reverse=True)
    return scored[0]


def cluster_embeddings(embeddings: np.ndarray, k: int = 3) -> np.ndarray:
    """sklearn 없이 간단 k-means (오디오 후보 N개 → 대표 k개 그룹)."""
    if len(embeddings) <= k:
        return np.arange(len(embeddings))
    rng = np.random.default_rng(0)
    idx = rng.choice(len(embeddings), k, replace=False)
    centers = embeddings[idx]
    for _ in range(20):
        dists = np.linalg.norm(embeddings[:, None] - centers[None], axis=-1)
        assign = dists.argmin(axis=1)
        new_centers = np.stack([
            embeddings[assign == i].mean(axis=0) if (assign == i).any() else centers[i]
            for i in range(k)
        ])
        if np.allclose(new_centers, centers):
            break
        centers = new_centers
    return assign


def cluster_and_pick(
    candidates: list[Path],
    prompt: str,
    k: int = 3,
    target_lufs: float = -14.0,
) -> list[tuple[Path, dict]]:
    """N개 후보를 k 클러스터로 묶고 각 클러스터 대표 리턴."""
    if len(candidates) <= k:
        return [(p, combined_score(p, prompt, target_lufs)) for p in candidates]
    emb = clap_audio_embed(candidates)
    assign = cluster_embeddings(emb, k)
    picks: list[tuple[Path, dict]] = []
    for cid in range(k):
        members = [p for p, a in zip(candidates, assign) if a == cid]
        if not members:
            continue
        best, score = pick_best(members, prompt, target_lufs)
        picks.append((best, score))
    return picks
