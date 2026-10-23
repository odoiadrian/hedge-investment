"""Validated intake and report contracts. Money is represented in integer cents."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

BUDGET_CENTS = 10_000_000


class ClientProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    reference: str = Field(min_length=1, max_length=100)
    age: int | None = Field(default=None, ge=0, le=120, strict=True)
    horizon_weeks: int = Field(ge=1, le=26, strict=True)
    risk_appetite: int = Field(ge=1, le=5, strict=True)
    max_loss_pct: float = Field(ge=0.5, le=60)
    max_single_holding_pct: float = Field(ge=1, le=100)
    objective: Literal["preserve_capital", "income", "balanced_growth", "max_growth"] = "balanced_growth"
    min_cash_pct: float = Field(default=0, ge=0, le=100)
    min_sellable_2day_pct: float = Field(default=90, ge=0, le=100)
    target_return_pct: float | None = Field(default=None, ge=-50, le=100)
    objectives: str = Field(default="", max_length=2000)
    values: str = Field(default="", max_length=3000)
    exclusions: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=3000)


class Allocation(BaseModel):
    asset_id: str
    instrument: str
    asset_class: str
    amount_cents: int = Field(gt=0, strict=True)
    financial_reason: str = Field(min_length=1)
    client_reason: str = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)


class PortfolioOption(BaseModel):
    id: Literal["A", "B", "C"]
    label: str
    allocations: list[Allocation]
    metrics: dict
    tightest_rules: list[str]
    note: str | None = None
    resampled: bool

    @model_validator(mode="after")
    def full_budget(self):
        if sum(a.amount_cents for a in self.allocations) != BUDGET_CENTS:
            raise ValueError("Allocations must sum to the entire budget")
        return self


class PortfolioDashboard(BaseModel):
    status: Literal["ready", "needs_clarification", "infeasible"]
    client_reference: str
    currency: Literal["USD"] = "USD"
    budget_cents: Literal[10_000_000] = BUDGET_CENTS
    message: str = ""
    questions: list[str] = Field(default_factory=list)
    recommended_option: Literal["A", "B", "C"] | None = None
    options: list[PortfolioOption] = Field(default_factory=list)
    client_assessment: str = ""
    financial_assessment: str = ""
    ai_status: Literal["generated", "unavailable", "not_run"] = "not_run"
    ai_summary: str = ""
    model_name: str = ""
    tokens_used: int = 0
    data_mode: str = ""
    data_as_of: str = ""
    data_sources: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    applied_profile: dict = Field(default_factory=dict)
    assumptions: dict = Field(default_factory=dict)
    target_return: dict | None = None
    horizon_trading_days: int = 0

    @model_validator(mode="after")
    def complete_report(self):
        if self.status == "ready":
            if {o.id for o in self.options} != {"A", "B", "C"} or len(self.options) != 3:
                raise ValueError("A complete report needs all three options")
            if self.recommended_option is None or not self.client_assessment or not self.financial_assessment:
                raise ValueError("A complete report needs a recommendation and both analyses")
        elif self.options:
            raise ValueError("Unresolved profiles must not contain allocations")
        return self
