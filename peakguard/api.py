"""API HTTP para simulações locais com dados sintéticos."""

import hmac
import ipaddress
import os
from typing import Any, Literal

from fastapi import Request
from fastapi.responses import JSONResponse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .budget import Slo, budget_report
from .scenarios import ALL_SCENARIOS, load_scenario
from .simulator import Config, compare, simulate
from .explanations import explain, evidence


class SimulationConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True)
    tick_minutes: float = Field(1, gt=0, le=1440)
    capacity_docs_per_minute_per_replica: float = Field(100, gt=0, le=1_000_000)
    price_brl_per_replica_hour: float = Field(1.2, ge=0, le=1_000_000)
    min_replicas: int = Field(1, ge=1, le=1000)
    max_replicas: int = Field(10, ge=1, le=1000)
    initial_replicas: int = Field(1, ge=1, le=1000)
    activation_delay_ticks: int = Field(2, ge=0, le=1000)
    cooldown_ticks: int = Field(2, ge=0, le=1000)
    forecast_horizon_ticks: int = Field(3, ge=1, le=1000)
    target_utilization: float = Field(0.8, gt=0, le=1)
    budget_brl: float = Field(10, ge=0, le=1_000_000_000)
    slo_queue_minutes: float = Field(2, gt=0, le=1_000_000)
    base_latency_minutes: float = Field(0.1, ge=0, le=1_000_000)


class ComparisonRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    scenario: Literal[*ALL_SCENARIOS]
    seed: int = Field(42, ge=-(2**63), le=2**63 - 1)
    config: SimulationConfig = Field(default_factory=SimulationConfig)
    risk_appetite: float | None = Field(None, gt=0, lt=1, description='Quantil dos resíduos (ex.: 0.5, 0.8, 0.9); só afeta a política antecipativa.')


class SimulationRequest(ComparisonRequest):
    policy: Literal['reactive', 'anticipatory'] = 'reactive'


class ExplanationRequest(ComparisonRequest):
    use_llm: bool = False


class ErrorBudgetRequest(ComparisonRequest):
    slo_target: float = Field(0.99, gt=0, lt=1)
    slo_window_minutes: float | None = Field(None, gt=0, le=1_000_000)


class SimulationResponse(BaseModel):
    schema_version: int
    scenario: str
    seed: int
    policy: str
    risk_appetite: float | None = None
    data_labels: dict[str, str]
    config: SimulationConfig
    input: dict[str, list[float]]
    ticks: list[dict[str, Any]]
    summary: dict[str, Any]


class ComparisonResponse(BaseModel):
    schema_version: int
    results: dict[str, SimulationResponse]


app = FastAPI(title='PeakGuard AI', description='Simulações sintéticas offline de capacidade e custo.', version='0.2.0')


@app.middleware('http')
async def access_control(request: Request, call_next):
    """Modo local restrito por IP; modo token exige Bearer em toda rota, inclusive /docs."""
    mode = os.getenv('PEAKGUARD_AUTH_MODE', 'local')
    if mode == 'local':
        client_ip = request.client.host if request.client else ''
        if client_ip != 'testclient':
            try:
                if not ipaddress.ip_address(client_ip).is_loopback:
                    return JSONResponse({'detail': 'Acesso externo desabilitado.'}, status_code=403)
            except ValueError:
                return JSONResponse({'detail': 'Cliente não reconhecido.'}, status_code=403)
    elif mode == 'token':
        expected = os.getenv('PEAKGUARD_API_TOKEN', '')
        if len(expected) < 32:
            return JSONResponse({'detail': 'Token de autenticação não configurado.'}, status_code=503)
        scheme, separator, provided = request.headers.get('authorization', '').partition(' ')
        if not separator or scheme.lower() != 'bearer' or not hmac.compare_digest(provided, expected):
            return JSONResponse(
                {'detail': 'Autenticação necessária.'}, status_code=401,
                headers={'WWW-Authenticate': 'Bearer'},
            )
    else:
        return JSONResponse({'detail': 'Modo de autenticação inválido.'}, status_code=503)
    return await call_next(request)



@app.get('/scenarios', response_model=list[str])
def scenarios():
    return list(ALL_SCENARIOS)


def run(request: ComparisonRequest, policy: str | None = None):
    try:
        scenario = load_scenario(request.scenario, request.seed)
        config = Config(**request.config.model_dump())
        return compare(scenario, config, request.risk_appetite) if policy is None else simulate(scenario, policy, config, request.risk_appetite)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post('/simulations', response_model=SimulationResponse)
def simulations(request: SimulationRequest):
    return run(request, request.policy)


@app.post('/comparisons', response_model=ComparisonResponse)
def comparisons(request: ComparisonRequest):
    return run(request)


@app.post('/evidence')
def read_evidence(request: ComparisonRequest):
    """Consulta sem persistência; evidências calculadas pelo motor, nunca pelo cliente."""
    return evidence(run(request))


@app.post('/explanations')
def explanations(request: ExplanationRequest):
    return explain(run(request), use_llm=request.use_llm)


@app.post('/error-budget')
def error_budget_report(request: ErrorBudgetRequest):
    """Error budget, burn rate e custo por minuto preservado; valores estimated sobre dados synthetic."""
    try:
        return budget_report(run(request), Slo(request.slo_target, request.slo_window_minutes))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
