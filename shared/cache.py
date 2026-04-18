"""해시 캐시 — 동일 파라미터 재실행 시 생성 스킵."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


def hash_params(params: dict[str, Any]) -> str:
    raw = json.dumps(params, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class AssetCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _key_dir(self, key: str) -> Path:
        return self.root / key

    def has(self, key: str) -> bool:
        d = self._key_dir(key)
        return d.exists() and any(d.iterdir())

    def restore(self, key: str, dest: Path) -> list[Path] | None:
        d = self._key_dir(key)
        if not d.exists():
            return None
        files = list(d.iterdir())
        if not files:
            return None
        dest.mkdir(parents=True, exist_ok=True)
        restored: list[Path] = []
        for f in files:
            target = dest / f.name
            shutil.copy2(f, target)
            restored.append(target)
        return restored

    def put(self, key: str, files: list[Path]) -> None:
        d = self._key_dir(key)
        d.mkdir(parents=True, exist_ok=True)
        for f in files:
            shutil.copy2(f, d / f.name)

    def invalidate(self, key: str) -> bool:
        d = self._key_dir(key)
        if not d.exists():
            return False
        shutil.rmtree(d)
        return True

    def invalidate_many(self, keys: list[str]) -> int:
        return sum(1 for k in keys if self.invalidate(k))
