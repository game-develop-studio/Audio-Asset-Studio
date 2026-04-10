"""입력 스키마 검증 (Pydantic)."""
from __future__ import annotations

from typing import Any, Literal

try:
    from pydantic import BaseModel, Field, ValidationError, field_validator
except ImportError:
    BaseModel = object  # type: ignore
    ValidationError = Exception  # type: ignore

    def Field(*a, **k):  # type: ignore
        return None

    def field_validator(*a, **k):  # type: ignore
        def _d(f):
            return f
        return _d


class AudioAssetModel(BaseModel):
    asset_id: str
    category: str
    prompt: str | None = None
    variations: int = Field(default=1, ge=1, le=32)
    duration_ms: int | None = Field(default=None, ge=50, le=300000)
    duration_sec: int | None = Field(default=None, ge=1, le=300)
    format: str = "ogg"
    loop: bool = False
    bpm: int | None = Field(default=None, ge=30, le=300)
    layers: list[str] | None = None
    intensity_layers: list[dict] | None = None
    post_process: list[str] | None = None

    @field_validator("format")
    @classmethod
    def _fmt(cls, v: str) -> str:
        allowed = {"wav", "ogg", "mp3", "flac"}
        if v.lower() not in allowed:
            raise ValueError(f"format must be one of {allowed}")
        return v.lower()


class AudioPaletteModel(BaseModel):
    genre: str | None = None
    reverb: str | None = None
    master_eq: str | None = None


class AudioInputModel(BaseModel):
    project: str | None = None
    audio_palette: AudioPaletteModel | None = None
    assets: list[AudioAssetModel]


def validate_audio_input(data: dict) -> dict:
    """검증 실패 시 ValueError 발생. 성공 시 정규화된 dict 반환."""
    try:
        model = AudioInputModel(**data)
    except ValidationError as e:
        raise ValueError(f"Audio input schema invalid:\n{e}") from e
    return model.model_dump(exclude_none=True)
