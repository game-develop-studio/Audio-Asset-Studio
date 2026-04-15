"""Stable Audio Open 어댑터 (선택 의존성)."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from .device import empty_cache, pick_device, torch_dtype

log = logging.getLogger(__name__)


class StableAudioAdapter:
    def __init__(self, variant: str = "stabilityai/stable-audio-open-1.0") -> None:
        self.variant = variant
        self.device = pick_device()
        self._model = None
        self._config = None

    def load(self) -> None:
        if self._model is not None:
            return
        try:
            from stable_audio_tools import get_pretrained_model
        except ImportError as e:
            raise RuntimeError(
                "stable-audio-tools 미설치. `pip install stable-audio-tools` 후 재시도."
            ) from e

        log.info("Loading Stable Audio %s on %s", self.variant, self.device)
        model, config = get_pretrained_model(self.variant)
        self._model = model.to(self.device).to(torch_dtype(self.device))
        self._config = config

    def unload(self) -> None:
        self._model = None
        self._config = None
        empty_cache(self.device)

    def generate(
        self,
        prompt: str,
        duration_ms: int,
        seed: int,
        output_dir: Path,
        prefix: str,
        reference_audio: Path | None = None,  # noqa: ARG002
        cfg_scale: float = 7.0,
        negative_prompt: str | None = None,
    ) -> list[Path]:
        self.load()
        import torch
        import torchaudio
        from stable_audio_tools.inference.generation import generate_diffusion_cond

        assert self._model is not None and self._config is not None
        sample_rate = self._config["sample_rate"]
        sample_size = self._config["sample_size"]

        conditioning = [{
            "prompt": prompt,
            "seconds_start": 0,
            "seconds_total": max(1.0, duration_ms / 1000.0),
        }]
        negative = [{"prompt": negative_prompt}] if negative_prompt else None

        torch.manual_seed(int(seed))
        t0 = time.time()
        out = generate_diffusion_cond(
            self._model,
            steps=100,
            cfg_scale=cfg_scale,
            conditioning=conditioning,
            negative_conditioning=negative,
            sample_size=sample_size,
            sigma_min=0.3,
            sigma_max=500,
            sampler_type="dpmpp-3m-sde",
            device=self.device,
        )
        log.info("  StableAudio %s: %.1fs", prefix, time.time() - t0)

        out = out.to(torch.float32).cpu()
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{prefix}.wav"
        torchaudio.save(str(out_path), out[0], sample_rate)
        return [out_path]
