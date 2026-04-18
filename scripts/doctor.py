"""환경 진단 — 다른 머신 마이그레이션 시 실행.

사용:
    python scripts/doctor.py
    ./studio doctor

체크:
  · Python 버전 3.9 ~ 3.11 (audiocraft 호환성)
  · ffmpeg / libsndfile 시스템 바이너리
  · 핵심 Python 패키지
  · GPU/MPS 가용성
  · 디스크 여유 공간 (모델 캐시용 ~20GB 권장)
  · HuggingFace Hub 네트워크
  · 쓰기 가능한 상태 디렉토리
"""
from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ANSI
RESET, GREEN, RED, YELLOW, CYAN, BOLD = (
    "\033[0m", "\033[32m", "\033[31m", "\033[33m", "\033[36m", "\033[1m"
)


def _ok(msg: str) -> None:
    print(f"  {GREEN}✔{RESET}  {msg}")


def _fail(msg: str, hint: str | None = None) -> None:
    print(f"  {RED}✘{RESET}  {msg}")
    if hint:
        print(f"       {YELLOW}→{RESET} {hint}")


def _warn(msg: str, hint: str | None = None) -> None:
    print(f"  {YELLOW}!{RESET}  {msg}")
    if hint:
        print(f"       {hint}")


def _section(title: str) -> None:
    print(f"\n{BOLD}{CYAN}▸ {title}{RESET}")


# ------ checks ------

def check_python() -> bool:
    _section("Python")
    v = sys.version_info
    ver = f"{v.major}.{v.minor}.{v.micro}"
    if (3, 9) <= (v.major, v.minor) <= (3, 11):
        _ok(f"Python {ver}")
        return True
    _fail(
        f"Python {ver} (권장: 3.9 ~ 3.11)",
        "audiocraft/laion-clap이 3.12+에서 빌드 이슈가 있습니다.",
    )
    return False


def check_system_binaries() -> bool:
    _section("System binaries")
    ok = True
    ff = shutil.which("ffmpeg")
    if ff:
        _ok(f"ffmpeg ({ff})")
    else:
        hint = {
            "Darwin": "brew install ffmpeg",
            "Linux": "sudo apt install ffmpeg  /  sudo dnf install ffmpeg",
            "Windows": "choco install ffmpeg  또는 https://www.gyan.dev/ffmpeg/builds/",
        }.get(platform.system(), "시스템 패키지 매니저로 설치")
        _fail("ffmpeg 없음 — pydub/변환이 동작하지 않습니다", hint)
        ok = False
    return ok


def check_python_packages() -> bool:
    _section("Python packages")
    core = [
        ("pyyaml", "yaml"), ("pydantic", "pydantic"), ("pydub", "pydub"),
        ("librosa", "librosa"), ("numpy", "numpy"), ("requests", "requests"),
        ("soundfile", "soundfile"),
    ]
    ml = [
        ("torch", "torch"), ("torchaudio", "torchaudio"),
        ("audiocraft", "audiocraft"), ("pyloudnorm", "pyloudnorm"),
    ]
    optional = [
        ("laion-clap", "laion_clap"), ("demucs", "demucs"),
        ("chromadb", "chromadb"), ("streamlit", "streamlit"),
        ("fastapi", "fastapi"), ("uvicorn", "uvicorn"), ("matplotlib", "matplotlib"),
    ]

    all_ok = True
    for label, group in [("core", core), ("ml", ml), ("optional", optional)]:
        missing = []
        for name, mod in group:
            try:
                __import__(mod)
            except ImportError:
                missing.append(name)
        if missing:
            if label == "core":
                _fail(f"{label}: 누락 {missing}", "pip install -r requirements.txt")
                all_ok = False
            elif label == "ml":
                _warn(f"{label}: 누락 {missing}", "로컬 생성 불가 — pip install 'audio-asset-studio[ml]'")
            else:
                _warn(f"{label}: 누락 {missing} (선택적 기능 제한)")
        else:
            _ok(f"{label}: 전부 설치됨")
    return all_ok


def check_gpu() -> None:
    _section("Inference device")
    try:
        import torch
    except ImportError:
        _warn("torch 미설치 — 로컬 추론 불가")
        return
    if torch.cuda.is_available():
        _ok(f"CUDA: {torch.cuda.get_device_name(0)}  (VRAM {torch.cuda.get_device_properties(0).total_memory/1e9:.1f}GB)")
    elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        _ok("Apple MPS: available")
    else:
        _warn("GPU/MPS 없음 — CPU fallback (느림, 테스트용)")


def check_disk() -> bool:
    _section("Disk space")
    home = Path.home()
    try:
        total, used, free = shutil.disk_usage(str(home))
    except Exception as e:
        _warn(f"디스크 확인 실패: {e}")
        return True
    free_gb = free / 1e9
    if free_gb < 10:
        _fail(f"여유 {free_gb:.1f}GB (권장 20GB+)", "모델 캐시가 수 GB라 실패할 수 있음")
        return False
    if free_gb < 20:
        _warn(f"여유 {free_gb:.1f}GB — MusicGen-large 같은 큰 모델 쓰면 빠듯")
    else:
        _ok(f"여유 {free_gb:.1f}GB")
    return True


def check_writable_dirs() -> bool:
    _section("Writable directories")
    ok = True
    for p in [ROOT / "output", Path.home() / ".audio_asset_studio", Path.home() / ".cache"]:
        try:
            p.mkdir(parents=True, exist_ok=True)
            t = p / ".write_test"
            t.write_text("x"); t.unlink()
            _ok(f"{p}")
        except Exception as e:
            _fail(f"{p} 쓰기 불가", str(e))
            ok = False
    return ok


def check_network() -> None:
    _section("Network (model downloads)")
    try:
        import requests
    except ImportError:
        _warn("requests 미설치 — 스킵")
        return
    for name, url in [
        ("HuggingFace", "https://huggingface.co"),
        ("GitHub", "https://github.com"),
    ]:
        try:
            r = requests.head(url, timeout=5, allow_redirects=True)
            if r.status_code < 500:
                _ok(f"{name}: {r.status_code}")
            else:
                _warn(f"{name}: {r.status_code}")
        except Exception as e:
            _fail(f"{name} 접속 실패", str(e))


def check_project_sanity() -> bool:
    _section("Project sanity")
    must = ["audio_studio.py", "config/categories.yaml", "requirements.txt", "shared", "phases"]
    ok = True
    for m in must:
        if (ROOT / m).exists():
            _ok(m)
        else:
            _fail(f"{m} 없음 (리포 손상 가능)"); ok = False
    return ok


def main() -> int:
    print(f"{BOLD}Audio Asset Studio — environment doctor{RESET}")
    print(f"OS: {platform.system()} {platform.release()} · arch {platform.machine()}")
    print(f"cwd: {ROOT}")

    results = [
        check_python(),
        check_system_binaries(),
        check_python_packages(),
        check_disk(),
        check_writable_dirs(),
        check_project_sanity(),
    ]
    check_gpu()
    check_network()

    print()
    blocking = sum(1 for r in results if r is False)
    if blocking == 0:
        print(f"{GREEN}{BOLD}✔ 모든 블로킹 체크 통과 — 실행 준비 완료{RESET}")
        return 0
    print(f"{RED}{BOLD}✘ {blocking}개 블로킹 이슈 — 위 → 힌트 따라 해결 후 재실행{RESET}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
