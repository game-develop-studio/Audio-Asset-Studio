"""MusicGen / MusicGen-Melody 어댑터 (audiocraft)."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from .device import empty_cache, pick_device, torch_dtype

log = logging.getLogger(__name__)


class MusicGenAdapter:
    """Lazy-load MusicGen. generate() 첫 호출 시 모델 로드."""

    def __init__(self, variant: str = "facebook/musicgen-medium") -> None:
        self.variant = variant
        self.device = pick_device()
        self._model = None

    # ---- lifecycle ----
    def load(self) -> None:
        if self._model is not None:
            return
        log.info("Loading MusicGen %s on %s", self.variant, self.device)
        from audiocraft.models import MusicGen

        name = self.variant.replace("facebook/", "")
        model = MusicGen.get_pretrained(name, device=self.device)
        self._model = model

    def unload(self) -> None:
        self._model = None
        empty_cache(self.device)

    # ---- generation ----
    def generate(
        self,
        prompt: str,
        duration_ms: int,
        seed: int,
        output_dir: Path,
        prefix: str,
        reference_audio: Path | None = None,
        cfg_scale: float = 3.0,
        negative_prompt: str | None = None,  # noqa: ARG002  MusicGen은 negative 지원 X
    ) -> list[Path]:
        self.load()
        import torch
        import torchaudio

        assert self._model is not None
        model = self._model

        duration_sec = max(1.0, duration_ms / 1000.0)
        model.set_generation_params(
            duration=duration_sec,
            cfg_coef=cfg_scale,
            use_sampling=True,
            top_k=250,
        )

        # 시드 고정
        torch.manual_seed(int(seed))
        if self.device == "cuda":
            torch.cuda.manual_seed_all(int(seed))

        t0 = time.time()
        if reference_audio and "melody" in self.variant:
            wav, sr = torchaudio.load(str(reference_audio))
            wav = wav.to(self.device)
            out = model.generate_with_chroma([prompt], wav[None], sr, progress=False)
        else:
            out = model.generate([prompt], progress=False)
        log.info("  MusicGen %s: %.1fs", prefix, time.time() - t0)

        sample_rate = model.sample_rate
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{prefix}.wav"

        wav = out[0].detach().cpu().float()
        torchaudio.save(str(out_path), wav, sample_rate)
        return [out_path]
