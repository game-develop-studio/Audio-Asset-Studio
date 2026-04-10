"""Phase 6: 엔진별 오디오 폴더 + 설정 임포트.

Unity: Assets/Audio/{sfx,bgm}/ + .meta
Godot: audio/{sfx,bgm}/ + .import
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import uuid
from pathlib import Path

from shared.pipeline_helpers import read_json, write_json

log = logging.getLogger(__name__)

# Unity .meta 템플릿 (AudioImporter)
UNITY_META_TEMPLATE = """\
fileFormatVersion: 2
guid: {guid}
AudioImporter:
  externalObjects: {{}}
  serializedVersion: 7
  defaultSettings:
    loadType: {load_type}
    sampleRateSetting: 0
    sampleRateOverride: 44100
    compressionFormat: {compression}
    quality: 0.7
    conversionMode: 0
  forceToMono: {force_mono}
  normalize: 0
  preloadAudioData: {preload}
  loadInBackground: {load_bg}
  ambisonic: 0
  3D: 0
  userData:
  assetBundleName:
  assetBundleVariant:
"""

GODOT_IMPORT_TEMPLATE = """\
[remap]
importer="ogg_vorbis"
type="AudioStreamOGGVorbis"
path="res://.import/{filename}-{hash}.oggstr"

[params]
loop={loop}
loop_offset=0.0
"""


def _unity_guid() -> str:
    return uuid.uuid4().hex


def _export_unity(
    processed_files: list[dict],
    manifest: dict,
    export_dir: Path,
) -> list[str]:
    """Unity 폴더 구조로 에셋 복사 + .meta 생성."""
    exported: list[str] = []
    assets_meta = manifest.get("assets_meta", {})

    for entry in processed_files:
        fpath = Path(entry.get("processed") or entry.get("output", ""))
        if not fpath.exists():
            continue

        asset_id = entry["asset_id"]
        meta = assets_meta.get(asset_id, {})
        cat = meta.get("category", "sfx_ui")

        # sfx_ → sfx/, bgm_ → bgm/
        subdir = "sfx" if cat.startswith("sfx_") else "bgm"
        dest_dir = export_dir / "Assets" / "Audio" / subdir
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest = dest_dir / fpath.name
        shutil.copy2(fpath, dest)

        # .meta 생성
        is_sfx = cat.startswith("sfx_")
        meta_content = UNITY_META_TEMPLATE.format(
            guid=_unity_guid(),
            load_type=0 if is_sfx else 1,  # 0=DecompressOnLoad, 1=CompressedInMemory
            compression=1,  # Vorbis
            force_mono=1 if is_sfx else 0,
            preload=1 if is_sfx else 0,
            load_bg=0 if is_sfx else 1,
        )
        (dest_dir / f"{fpath.name}.meta").write_text(meta_content)
        exported.append(str(dest))

    return exported


def _export_godot(
    processed_files: list[dict],
    manifest: dict,
    export_dir: Path,
) -> list[str]:
    """Godot 폴더 구조로 에셋 복사 + .import 설정."""
    exported: list[str] = []
    assets_meta = manifest.get("assets_meta", {})

    for entry in processed_files:
        fpath = Path(entry.get("processed") or entry.get("output", ""))
        if not fpath.exists():
            continue

        asset_id = entry["asset_id"]
        meta = assets_meta.get(asset_id, {})
        cat = meta.get("category", "sfx_ui")

        subdir = "sfx" if cat.startswith("sfx_") else "bgm"
        dest_dir = export_dir / "audio" / subdir
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest = dest_dir / fpath.name
        shutil.copy2(fpath, dest)

        # .import 생성
        h = hashlib.md5(fpath.name.encode()).hexdigest()[:8]
        import_content = GODOT_IMPORT_TEMPLATE.format(
            filename=fpath.stem,
            hash=h,
            loop="true" if meta.get("loop") else "false",
        )
        (dest_dir / f"{fpath.name}.import").write_text(import_content)
        exported.append(str(dest))

    return exported


def run(
    post_report_path: Path,
    manifest_path: Path,
    out_dir: Path,
    engine: str = "unity",
) -> Path:
    """후처리 리포트를 받아 엔진별 폴더 구조로 export.

    Returns:
        phase6_engine_import_report.json 경로
    """
    report = read_json(post_report_path)
    manifest = read_json(manifest_path)

    processed_files = [
        r for r in report.get("results", [])
        if r.get("status") == "processed"
    ]
    # 레이어 믹스 결과도 포함
    processed_files.extend(report.get("layer_mixes", []))

    export_dir = out_dir / f"export_{engine}"
    export_dir.mkdir(parents=True, exist_ok=True)

    if engine == "unity":
        exported = _export_unity(processed_files, manifest, export_dir)
    elif engine == "godot":
        exported = _export_godot(processed_files, manifest, export_dir)
    else:
        raise ValueError(f"Unsupported engine: {engine}. Use 'unity' or 'godot'")

    out = out_dir / "phase6_engine_import_report.json"
    write_json(out, {
        "project_id": report.get("project_id", ""),
        "engine": engine,
        "exported_files": exported,
        "total": len(exported),
    })
    log.info("Phase 6 done: %d files exported to %s (%s)", len(exported), export_dir, engine)
    return out
