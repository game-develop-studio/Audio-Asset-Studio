"""AudioGen 어댑터 — 짧은 SFX 특화."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from .device import empty_cache, pick_device

log = logging.getLogger(__name__)


class AudioGenAdapter:
    def __init__(self, variant: str = "facebook/audiogen-medium") -> None:
        self.variant = variant
        self.device = pick_device()
        self._model = None

    def load(self) -> None:
        if self._model is not None:
            return
        log.info("Loading AudioGen %s on %s", self.variant, self.device)
        from audiocraft.models import AudioGen

        name = self.variant.replace("facebook/", "")
        self._model = AudioGen.get_pretrained(name, device=self.device)

    def unload(self) -> None:
        self._model = None
        empty_cache(self.device)

    def generate(
        self,
        prompt: str,
        duration_ms: int,
        seed: int,
        output_dir: Path,
        prefix: str,
        reference_audio: Path | None = None,  # noqa: ARG002
        cfg_scale: float = 3.0,
        negative_prompt: str | None = None,   # noqa: ARG002
    ) -> list[Path]:
        self.load()
        import torch
        import torchaudio

        assert self._model is not None
        model = self._model

        duration_sec = max(0.5, duration_ms / 1000.0)
        model.set_generation_params(
            duration=duration_sec,
            cfg_coef=cfg_scale,
            use_sampling=True,
            top_k=250,
        )
        torch.manual_seed(int(seed))

        t0 = time.time()
        out = model.generate([prompt], progress=False)
        log.info("  AudioGen %s: %.1fs", prefix, time.time() - t0)

        sr = model.sample_rate
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{prefix}.wav"
        torchaudio.save(str(out_path), out[0].detach().cpu().float(), sr)
        return [out_path]
