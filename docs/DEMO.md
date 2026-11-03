# Roteiro de demonstração — até cinco minutos

Antes da entrevista: seguir README, manter API e dashboard ativos, preparar `/docs`, `docs/ARCHITECTURE.md` e arquivos de benchmark. Não criar Kind nem instalar dependências durante os cinco minutos. A evidência P6 é histórica e identificada como tal.

| Tempo | Ação e argumento técnico |
| --- | --- |
| 0:00–0:30 | Abrir o dashboard. Dados sintéticos, custos estimados, nenhuma alteração de infraestrutura. Seed 42. |
| 0:30–1:15 | Cenário **Fiscal: DAS dia 20** ([captura](p14-fiscal.png)): a reativa acumula 898 documentos e viola o SLO por 2 min (R$ 1,52); a antecipativa não viola (R$ 1,10). A previsão do calendário fiscal é declarada, não aprendida: o ganho depende dela. Números em `evidence/p14/results.json`. |
| 1:15–2:00 | **Pareto** custo × ticks fora do SLO ([captura](p14-pareto.png)). Em `unexpected_peak` a fronteira só tem pontos antecipativos; em `wrong_forecast` só reativos (previsão errada torna a reativa dominante). 56 configurações por cenário. |
| 2:00–2:45 | **Error budget** (comando abaixo): percentil p90 gasta R$ 0,28 a mais que p50 e preserva 4 min de budget (R$ 0,07 por minuto). Alerta rápido de burn rate dispara no p50 (tick 12) e não no p90. |
| 2:45–3:30 | **Governança**: proposta insegura rejeitada (exemplo abaixo), texto da LLM com número inventado cai no fallback, e `POST /manifest-diff` gera o diff HPA/ScaledObject sem aplicar nada. |
| 3:30–4:15 | **Calibração** contra o Kind v1.36.4 ([docs/CALIBRATION.md](CALIBRATION.md)): capacidade medida 294 doc/min contra 300 assumidos, startup 12 s; calibrar **não reduziu** o erro (MAE de backlog 36,5 → 41,3 doc). Resultado negativo mostrado de propósito. |
| 4:15–5:00 | Diagramas e limites: motor único, adaptador sem ferramentas, HPA separado. Fechar em "Próximos passos" do README. |

## Explicação offline

```bash
curl -fsS http://127.0.0.1:8000/explanations -H 'Content-Type: application/json' -d '{"scenario":"predictable_peak","seed":42}' > /tmp/peakguard-explanation.json
python3 -m json.tool /tmp/peakguard-explanation.json
```

## IA real, opcional

Somente com extra `.[llm]`, chave e modelo configurados no ambiente do servidor e `PEAKGUARD_LLM_ENABLED=true`. Essa chamada pode gerar cobrança. Verifique `mode=llm` antes de dizer que houve seleção gerada pelo provedor. `fallback` significa que a integração não forneceu uma seleção aceita. A explicação textual é sempre renderizada pelo servidor a partir de alegações verificadas.

```bash
curl -fsS http://127.0.0.1:8000/explanations -H 'Content-Type: application/json' -d '{"scenario":"predictable_peak","seed":42,"use_llm":true}'
```

A execução P7 não dispõe de provedor configurado e não apresenta uma resposta externa como evidência. O teste abaixo exercita o SDK real com HTTP simulado, explicitamente sem geração externa:

```bash
PYTHONPATH=/tmp/peakguard-test-deps python3 -m pytest tests/test_explanations.py -q -k real_sdk_adapter
```

## Rejeição controlada e reproduzível

A proposta abaixo é injetada pelo demonstrador, não gerada por IA. Ela cita o custo correto, mas escolhe uma política que violou SLO. O mesmo validador é usado com respostas do provedor.

```bash
PYTHONPATH=/tmp/peakguard-test-deps python3 - <<'PY'
import json
from peakguard.scenarios import load_scenario
from peakguard.simulator import Config, compare
from peakguard.explanations import explain
comparison = compare(load_scenario('predictable_peak', 42), Config())
proposal = {'policy': 'reactive', 'claims': [{'id': 'reactive.cost_brl', 'value': comparison['results']['reactive']['summary']['cost_brl']}], 'hypotheses': []}
result = explain(comparison, provider=lambda _: proposal, use_llm=True)
print(json.dumps({'provider': 'injetado; não é LLM externo', 'audit': result['audit'], 'selected': result['proposal']['policy'], 'execution_allowed': result['execution_allowed']}, indent=2))
PY
```

Esperado: rejeição por `slo`, fallback `anticipatory`, `execution_allowed=false`.

## Benchmark

```bash
python3 -m peakguard.benchmarks --output /tmp/peakguard-demo-benchmark
```

Mostrar `comparison.svg`, `comparison.md` e `report.json`.

## Error budget, Pareto e manifesto (v2)

```bash
curl -fsS http://127.0.0.1:8000/error-budget -H 'Content-Type: application/json' -d '{"scenario":"unexpected_peak","seed":42,"risk_appetite":0.9,"slo_target":0.99}'
curl -fsS http://127.0.0.1:8000/pareto -H 'Content-Type: application/json' -d '{"scenario":"unexpected_peak","seed":42}'
curl -fsS http://127.0.0.1:8000/manifest-diff -H 'Content-Type: application/json' -d '{"scenario":"predictable_peak","kind":"hpa","name":"documents","namespace":"demo"}'
PYTHONPATH=. python3 local/p14/results.py   # regenera evidence/p14/results.json (todos os números do roteiro)
```

Os números de p50 × p90 usam chegadas `burst` e `activation_delay_ticks=3`, que a API ainda não expõe; por isso vêm de `evidence/p14/results.json` e do teste `tests/test_p10.py::test_higher_percentile_costs_more_and_burns_less_budget`.

## Perguntas técnicas previsíveis

1. **Por que não usar só o HPA?** O HPA reage à CPU média e leva 20–30 s só para criar pods (`first_scale_after_load_seconds` em `evidence/p13/calibration.json`); a política antecipativa simulada usa o calendário. Mas o simulador não foi implantado no Kubernetes: a comparação indica tendência, não equivalência de algoritmos.
2. **E se a previsão estiver errada?** É um cenário essencial: em `wrong_forecast` a fronteira de Pareto só tem pontos reativos, e o validador determinístico (guarda de SLO, min/max, orçamento) continua cobrindo a proposta. O percentil maior (p90) compra margem pagando mais, como mostra o error budget.
3. **A IA pode alterar o cluster?** Não. A LLM só explica propostas; validação de SLO, custo e permissões é determinística, qualquer número fora das evidências aciona o fallback, e o manifesto é apenas um diff para PR (`applied=false`, `execution_allowed=false`). A chamada real à LLM ainda não foi executada (sem chave; ver [VERIFICATION](VERIFICATION.md)).
