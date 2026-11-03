"""Regras declarativas do validador (YAML), carregadas e validadas na importação."""

from importlib.resources import files
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, frozen=True)


class Replicas(_Strict):
    min: int = Field(ge=1)
    max: int = Field(ge=1)

    @model_validator(mode="after")
    def ordered(self):
        if self.min > self.max:
            raise ValueError("replicas.min não pode exceder replicas.max")
        return self


class Slo(_Strict):
    violation_minutes_max: float = Field(ge=0)


class EvidenceRule(_Strict):
    min_policy_claims: int = Field(ge=1, le=20)


class Rules(_Strict):
    version: int = Field(ge=1, le=1)
    replicas: Replicas
    budget_brl_max: float = Field(ge=0)
    slo: Slo
    evidence: EvidenceRule


def load_rules(path: Path | None = None) -> Rules:
    """Qualquer erro de leitura, sintaxe ou esquema vira ValueError (falha rápida, sem regra implícita)."""
    try:
        text = Path(path).read_text(encoding="utf-8") if path else files("peakguard").joinpath("rules.yaml").read_text(encoding="utf-8")
        return Rules.model_validate(yaml.safe_load(text))
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ValueError(f"Regras inválidas: {error}") from error


RULES = load_rules()
