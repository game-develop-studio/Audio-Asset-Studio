"""버짓 가드 테스트."""
import pytest
from shared.budget import BudgetGuard, BudgetState


def test_budget_check_ok(tmp_path):
    bg = BudgetGuard(tmp_path / "budget.json", BudgetState(hard_limit_usd=5.0))
    bg.check(1.0)  # should not raise


def test_budget_check_exceeded(tmp_path):
    bg = BudgetGuard(tmp_path / "budget.json", BudgetState(hard_limit_usd=1.0))
    with pytest.raises(RuntimeError, match="Budget hard limit"):
        bg.check(2.0)


def test_budget_charge(tmp_path):
    bg = BudgetGuard(tmp_path / "budget.json", BudgetState(hard_limit_usd=5.0))
    bg.charge(0.5, reason="test")
    assert bg.state.spent_usd == 0.5
    assert len(bg.state.charges) == 1
    assert (tmp_path / "budget.json").exists()
