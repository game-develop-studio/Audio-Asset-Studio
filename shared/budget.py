"""버짓 가드 — 하드/소프트 한도로 과금 방지."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class BudgetState:
    project_id: str = ""
    hard_limit_usd: float = 5.0
    soft_limit_pct: float = 0.8
    spent_usd: float = 0.0
    charges: list[dict] = field(default_factory=list)


class BudgetGuard:
    def __init__(self, path: Path, state: BudgetState | None = None) -> None:
        self.path = path
        if path.exists():
            data = json.loads(path.read_text())
            self.state = BudgetState(**data)
        else:
            self.state = state or BudgetState()

    def check(self, projected_usd: float) -> None:
        after = self.state.spent_usd + projected_usd
        if after > self.state.hard_limit_usd:
            raise RuntimeError(
                f"Budget hard limit exceeded: ${after:.4f} > ${self.state.hard_limit_usd:.2f}"
            )
        soft = self.state.hard_limit_usd * self.state.soft_limit_pct
        if after > soft:
            log.warning(
                "Budget soft limit warning: $%.4f / $%.2f (%.0f%%)",
                after, self.state.hard_limit_usd, after / self.state.hard_limit_usd * 100,
            )

    def charge(self, amount_usd: float, reason: str = "") -> None:
        self.state.spent_usd += amount_usd
        self.state.charges.append({"amount": amount_usd, "reason": reason})
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state.__dict__, indent=2, ensure_ascii=False))
