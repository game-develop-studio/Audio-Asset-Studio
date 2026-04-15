"""마이그레이션 적합성 테스트.

다른 머신으로 리포를 옮겼을 때 돌아가는지 검증.
  · 소스에 하드코딩된 절대 경로 없음
  · 모든 패키지에 __init__.py
  · 선택적 의존성(audiocraft/torch/laion_clap/demucs)은 import-guard 되어있음
  · pyproject.toml 유효성 + requires-python 범위
  · Python 3.9 호환 — 3.10+ 문법을 쓴 모듈은 `from __future__ import annotations` 보호
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

PY_SOURCE_DIRS = ["shared", "phases", "post_process", "dashboard", "scripts"]
PACKAGE_DIRS = ["shared", "phases", "post_process"]  # Python 패키지 (import 대상)
TOP_LEVEL_MODULES = ["audio_studio.py"]


def _iter_py_files():
    for d in PY_SOURCE_DIRS:
        p = ROOT / d
        if p.exists():
            yield from p.rglob("*.py")
    for m in TOP_LEVEL_MODULES:
        p = ROOT / m
        if p.exists():
            yield p


def test_no_hardcoded_user_paths():
    """/Users/..., C:\\Users\\..., /home/<name>/ 등 사용자 절대경로 없음."""
    bad_patterns = [
        re.compile(r"/Users/[a-zA-Z0-9_-]+/"),
        re.compile(r"C:\\\\Users\\\\[a-zA-Z0-9_-]+"),
        re.compile(r"/home/[a-zA-Z0-9_-]+/"),
    ]
    offenders: list[str] = []
    for f in _iter_py_files():
        text = f.read_text(encoding="utf-8", errors="ignore")
        for pat in bad_patterns:
            for m in pat.finditer(text):
                # Path.home() 호출로 대체된 경우는 OK — 리터럴 경로만 잡음
                offenders.append(f"{f.relative_to(ROOT)}: {m.group()}")
    assert not offenders, "하드코딩 경로 발견:\n" + "\n".join(offenders)


def test_all_packages_have_init():
    """Python 패키지 디렉토리(PACKAGE_DIRS)에 __init__.py 존재.

    dashboard/ 는 streamlit 앱 레이아웃이고 scripts/ 는 실행 스크립트이므로 제외.
    """
    missing: list[str] = []
    for d in PACKAGE_DIRS:
        root = ROOT / d
        if not root.exists():
            continue
        for sub in [root, *[p for p in root.rglob("*") if p.is_dir()]]:
            if sub.name.startswith("__"):
                continue
            if not (sub / "__init__.py").exists():
                missing.append(str(sub.relative_to(ROOT)))
    assert not missing, "__init__.py 누락:\n" + "\n".join(missing)


def test_optional_deps_are_import_guarded():
    """선택적 의존성은 top-level import 시 ImportError를 내지 않아야 함.

    audiocraft/torch/laion_clap/demucs/chromadb 를 top-level에서 무방비로 import 하면
    해당 extras 를 설치하지 않은 환경에서 core 기능까지 죽는다.
    """
    guarded_modules = {"audiocraft", "torch", "torchaudio", "laion_clap",
                       "demucs", "chromadb", "stable_audio_tools"}
    offenders: list[str] = []
    for f in _iter_py_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            # 함수/클래스/try 내부 import 는 안전(지연 로딩)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef, ast.Try)):
                for child in ast.walk(node):
                    child._inside_guard = True  # type: ignore[attr-defined]

        for node in ast.walk(tree):
            if getattr(node, "_inside_guard", False):
                continue
            if isinstance(node, ast.Import):
                for a in node.names:
                    top = a.name.split(".")[0]
                    if top in guarded_modules:
                        offenders.append(f"{f.relative_to(ROOT)}:{node.lineno} import {a.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in guarded_modules:
                    offenders.append(f"{f.relative_to(ROOT)}:{node.lineno} from {node.module}")

    assert not offenders, (
        "선택적 의존성이 top-level 에서 import 되고 있습니다 (try/except 또는 함수 내부로 이동 필요):\n"
        + "\n".join(offenders)
    )


def test_pyproject_toml_valid():
    """pyproject.toml 파싱되고 필수 필드 존재."""
    pyproject = ROOT / "pyproject.toml"
    assert pyproject.exists(), "pyproject.toml 없음"

    try:
        import tomllib  # py3.11+
    except ImportError:
        tomllib = None
    if tomllib is None:
        try:
            import tomli as tomllib  # type: ignore
        except ImportError:
            pytest.skip("tomllib/tomli 미설치 — Python 3.11+ 또는 `pip install tomli`")

    with pyproject.open("rb") as f:
        data = tomllib.load(f)

    assert "project" in data
    proj = data["project"]
    assert proj.get("name") == "audio-asset-studio"
    assert "requires-python" in proj
    # 3.9~3.11 지원 명시
    assert ">=3.9" in proj["requires-python"]
    assert "<3.12" in proj["requires-python"]

    extras = proj.get("optional-dependencies", {})
    # 핵심 extras 전부 정의
    for key in ["ml", "tagging", "stems", "server", "dashboard", "dev"]:
        assert key in extras, f"optional-dependencies.{key} 누락"


def test_python_39_compat_future_annotations():
    """3.10+ 문법(X | Y, list[int] 등)을 쓰는 파일은 `from __future__ import annotations` 필수."""
    # 단순 휴리스틱: 주석/문자열 밖에서 등장하는 `X | Y` 패턴
    union_re = re.compile(r"[a-zA-Z_\]\)]\s*\|\s*[a-zA-Z_\[]")
    offenders: list[str] = []
    for f in _iter_py_files():
        text = f.read_text(encoding="utf-8", errors="ignore")
        # 대충 주석 제거
        no_comments = re.sub(r"#.*", "", text)
        if not union_re.search(no_comments):
            continue
        if "from __future__ import annotations" not in text:
            offenders.append(str(f.relative_to(ROOT)))
    assert not offenders, (
        "3.10+ 유니온 문법을 쓰면서 future annotations 가 없음 (Py3.9 에서 런타임 에러):\n"
        + "\n".join(offenders)
    )


def test_doctor_script_exists_and_syntactically_valid():
    """scripts/doctor.py 구문 유효 + main() 진입점 존재."""
    doc = ROOT / "scripts" / "doctor.py"
    assert doc.exists(), "scripts/doctor.py 없음"
    tree = ast.parse(doc.read_text(encoding="utf-8"))
    funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "main" in funcs


def test_launcher_script_has_checks():
    """./studio 런처가 Python/ffmpeg 체크 및 doctor 서브커맨드 포함."""
    launcher = ROOT / "studio"
    assert launcher.exists(), "studio 런처 없음"
    text = launcher.read_text()
    for needle in ["python3", "ffmpeg", "doctor", "3.9", "3.11"]:
        assert needle in text, f"런처에 `{needle}` 체크/언급 없음"


def test_core_imports_without_optional_deps():
    """core deps 만 있으면 주요 패키지가 import 되어야 함.

    optional(torch/audiocraft/laion_clap/demucs/chromadb) 가 없어도 import 가 깨지면 안 됨.
    core deps(pyyaml/pydantic/pydub/librosa 등) 자체가 미설치면 스킵.
    """
    for core in ["yaml", "pydantic", "pydub", "librosa", "numpy", "soundfile"]:
        try:
            __import__(core)
        except ImportError:
            pytest.skip(f"core dep `{core}` 미설치 — `pip install -r requirements.txt` 후 재실행")

    code = (
        "import sys; "
        "sys.path.insert(0, r'" + str(ROOT) + "'); "
        "import shared; "
        "import phases; "
        "import post_process; "
        "from shared.backends import get_backend, GenerationJob; "
        "print('ok')"
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, f"core import 실패:\nSTDOUT:{r.stdout}\nSTDERR:{r.stderr}"
    assert "ok" in r.stdout
