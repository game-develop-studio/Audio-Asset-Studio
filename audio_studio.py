#!/usr/bin/env python3
"""Audio Asset Studio — 게임 오디오 에셋 자동 생성 파이프라인.

Usage:
    python audio_studio.py --project my_clicker --input audio_assets.yaml
    python audio_studio.py --project my_clicker --input audio_assets.yaml --dry-run
    python audio_studio.py --project my_clicker --input audio_assets.yaml --phases 5,6
    python audio_studio.py --project my_clicker --input audio_assets.yaml --preview
    python audio_studio.py --project my_clicker --input audio_assets.yaml --reference cookie-clicker
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from shared.pipeline_helpers import read_yaml
from shared.schemas import validate_audio_input

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("audio_studio")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Audio Asset Studio")
    p.add_argument("--project", required=True, help="프로젝트 ID")
    p.add_argument("--input", required=True, help="입력 YAML/JSON 경로")
    p.add_argument("--dry-run", action="store_true", help="Phase 4 (생성) 스킵")
    p.add_argument("--phases", default=None, help="실행할 phase 번호 (예: 1,2,3 또는 5,6)")
    p.add_argument("--preview", action="store_true", help="프리뷰 모드 (저품질 빠른 생성)")
    p.add_argument("--reference", default=None, help="레퍼런스 게임 (예: cookie-clicker)")
    p.add_argument("--engine", default="unity", choices=["unity", "godot"], help="엔진 (기본: unity)")
    p.add_argument("--output", default=None, help="출력 디렉토리 (기본: output/<project>)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    project_id = args.project
    input_path = Path(args.input)

    if not input_path.exists():
        log.error("Input file not found: %s", input_path)
        sys.exit(1)

    # 입력 로드 + 스키마 검증
    if input_path.suffix in (".yaml", ".yml"):
        user_input = read_yaml(input_path)
    else:
        from shared.pipeline_helpers import read_json
        user_input = read_json(input_path)

    user_input = validate_audio_input(user_input)

    # 출력 디렉토리
    out_dir = Path(args.output) if args.output else ROOT / "output" / project_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # 실행할 phase 결정
    if args.phases:
        phases = set(int(x.strip()) for x in args.phases.split(","))
    else:
        phases = {1, 2, 3, 4, 5, 6}

    if args.dry_run:
        phases.discard(4)

    config_dir = ROOT / "config"
    categories_cfg = config_dir / "categories.yaml"
    palettes_dir = config_dir / "audio_palettes"

    start = time.time()
    log.info("=== Audio Asset Studio: project=%s ===", project_id)

    # Phase 1: 오디오 팔레트
    palette_path = out_dir / "phase1_audio_palette.json"
    if 1 in phases:
        from phases.phase1_audio_palette import run as run_p1
        palette_path = run_p1(
            user_input=user_input,
            palettes_dir=palettes_dir,
            out_dir=out_dir,
            reference=args.reference,
        )

    # Phase 2: 사운드 명세 정규화
    spec_path = out_dir / "phase2_audio_spec.json"
    if 2 in phases:
        if not palette_path.exists():
            log.error("Phase 1 output required. Run Phase 1 first or include it in --phases")
            sys.exit(1)
        from phases.phase2_audio_spec import run as run_p2
        spec_path = run_p2(
            project_id=project_id,
            user_input=user_input,
            palette_path=palette_path,
            out_dir=out_dir,
            categories_cfg_path=categories_cfg,
        )

    # Phase 3: 프롬프트 빌드
    manifest_path = out_dir / "phase3_generation_manifest.json"
    if 3 in phases:
        if not spec_path.exists():
            log.error("Phase 2 output required. Run Phase 2 first or include it in --phases")
            sys.exit(1)
        from phases.phase3_prompt_build import run as run_p3
        manifest_path = run_p3(
            spec_path=spec_path,
            out_dir=out_dir,
        )

    # Phase 4: 로컬 생성
    gen_report_path = out_dir / "phase4_generation_report.json"
    if 4 in phases:
        from phases.phase4_generate import run as run_p4

        # pipeline config (없으면 기본값)
        pipeline_cfg = config_dir / "pipeline.yaml"
        if not pipeline_cfg.exists():
            pipeline_cfg_data = {
                "cache": {"enabled": True, "root": str(out_dir / ".cache")},
                "budget": {"hard_limit_usd": 5.0, "soft_limit_pct": 0.8},
            }
            from shared.pipeline_helpers import write_yaml
            write_yaml(pipeline_cfg, pipeline_cfg_data)

        gen_report_path = run_p4(
            manifest_path=manifest_path,
            pipeline_cfg_path=pipeline_cfg,
            out_dir=out_dir,
        )
    elif 4 not in phases and args.dry_run:
        # dry-run: 빈 리포트 생성
        from shared.pipeline_helpers import write_json
        write_json(gen_report_path, {
            "project_id": project_id,
            "results": [],
            "pod_used": False,
            "note": "dry-run: Phase 4 skipped",
        })
        log.info("Phase 4: skipped (dry-run)")

    # Phase 5: 후처리
    post_report_path = out_dir / "phase5_post_process_report.json"
    if 5 in phases and gen_report_path.exists():
        from phases.phase5_post_process import run as run_p5
        post_report_path = run_p5(
            report_path=gen_report_path,
            manifest_path=manifest_path,
            out_dir=out_dir,
        )

    # Phase 6: 엔진 임포트
    if 6 in phases and post_report_path.exists():
        from phases.phase6_engine_import import run as run_p6
        run_p6(
            post_report_path=post_report_path,
            manifest_path=manifest_path,
            out_dir=out_dir,
            engine=args.engine,
        )

    elapsed = time.time() - start
    log.info("=== Done in %.1fs ===", elapsed)


if __name__ == "__main__":
    main()
