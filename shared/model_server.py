"""Model warm-pool 데몬.

사용:
    python -m shared.model_server                   # 기본 8765
    MODEL_SERVER_PORT=9000 python -m shared.model_server
    AUDIO_DEVICE=mps python -m shared.model_server

모델을 메모리에 상주시키고 HTTP로 generate 요청을 받음. 파이프라인 재실행 시
콜드스타트(수십 초 모델 로드)를 건너뛰어 iteration이 즉각적이 됨.

M4 Max 36GB에서 MusicGen-medium + AudioGen-medium 동시 상주 가능 (~12GB).
large 까지 올리려면 AUDIO_UNLOAD_POLICY=lru 로 동적 교체.
"""
from __future__ import annotations

import base64
import logging
import os
import tempfile
import threading
from pathlib import Path

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
    import uvicorn
except ImportError as e:
    raise SystemExit(
        "fastapi/uvicorn/pydantic 미설치. `pip install -r requirements.txt`"
    ) from e

from .backends.local.registry import load_adapter, MODEL_REGISTRY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] model_server: %(message)s",
)
log = logging.getLogger("model_server")


class GenerateRequest(BaseModel):
    job_id: str
    model: str
    prompt: str
    duration_ms: int
    seed: int = 0
    cfg_scale: float = 3.0
    negative_prompt: str | None = None
    prefix: str = "gen"
    reference_audio_b64: str | None = None


# ------- adapter pool -------
_ADAPTERS: dict[str, object] = {}
_LOCK = threading.Lock()
_UNLOAD_POLICY = os.environ.get("AUDIO_UNLOAD_POLICY", "keep").lower()
_MAX_LOADED = int(os.environ.get("AUDIO_MAX_LOADED", "3"))
_LRU: list[str] = []


def _get_adapter(model: str):
    with _LOCK:
        if model in _ADAPTERS:
            if model in _LRU:
                _LRU.remove(model)
            _LRU.append(model)
            return _ADAPTERS[model]

        if _UNLOAD_POLICY == "lru" and len(_ADAPTERS) >= _MAX_LOADED:
            evict = _LRU.pop(0)
            log.info("LRU evict: %s", evict)
            try:
                _ADAPTERS[evict].unload()  # type: ignore[attr-defined]
            except Exception as e:
                log.warning("unload failed: %s", e)
            _ADAPTERS.pop(evict, None)

        log.info("Loading adapter: %s", model)
        adapter = load_adapter(model)
        adapter.load()  # type: ignore[attr-defined]
        _ADAPTERS[model] = adapter
        _LRU.append(model)
        return adapter


def create_app() -> FastAPI:
    app = FastAPI(title="Audio Asset Studio — Model Server")

    @app.get("/health")
    def health() -> dict:
        return {
            "ok": True,
            "loaded": sorted(_ADAPTERS),
            "available": sorted(MODEL_REGISTRY),
            "policy": _UNLOAD_POLICY,
        }

    @app.post("/warm")
    def warm(body: dict) -> dict:
        """미리 모델을 로드 (첫 generate 대기 제거)."""
        models = body.get("models", [])
        for m in models:
            _get_adapter(m)
        return {"loaded": sorted(_ADAPTERS)}

    @app.post("/unload")
    def unload(body: dict) -> dict:
        model = body.get("model")
        with _LOCK:
            ad = _ADAPTERS.pop(model, None)
            if model in _LRU:
                _LRU.remove(model)
        if ad is not None:
            try:
                ad.unload()  # type: ignore[attr-defined]
            except Exception:
                pass
        return {"loaded": sorted(_ADAPTERS)}

    @app.post("/generate")
    def generate(req: GenerateRequest) -> dict:
        try:
            adapter = _get_adapter(req.model)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            ref_path: Path | None = None
            if req.reference_audio_b64:
                ref_path = tmp_dir / "reference.wav"
                ref_path.write_bytes(base64.b64decode(req.reference_audio_b64))

            try:
                files = adapter.generate(  # type: ignore[attr-defined]
                    prompt=req.prompt,
                    duration_ms=req.duration_ms,
                    seed=req.seed,
                    output_dir=tmp_dir,
                    prefix=req.prefix,
                    reference_audio=ref_path,
                    cfg_scale=req.cfg_scale,
                    negative_prompt=req.negative_prompt,
                )
            except Exception as e:
                log.exception("generate failed")
                raise HTTPException(status_code=500, detail=str(e))

            encoded: dict[str, str] = {}
            for f in files:
                encoded[f.name] = base64.b64encode(f.read_bytes()).decode()
            return {"job_id": req.job_id, "files": encoded}

    return app


def main() -> None:
    port = int(os.environ.get("MODEL_SERVER_PORT", "8765"))
    host = os.environ.get("MODEL_SERVER_HOST", "127.0.0.1")
    log.info("Starting model_server on %s:%d (policy=%s, max_loaded=%d)",
             host, port, _UNLOAD_POLICY, _MAX_LOADED)
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
