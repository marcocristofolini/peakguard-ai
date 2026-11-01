# Roteiro de demonstração — até cinco minutos

Antes da entrevista: seguir README, manter API e dashboard ativos, preparar `/docs`, `docs/ARCHITECTURE.md` e arquivos de benchmark. Não criar Kind nem instalar dependências durante os cinco minutos. A evidência P6 é histórica e identificada como tal.

| Tempo | Ação e argumento técnico |
| --- | --- |
| 0:00–0:35 | Abrir dashboard. Explicar que demanda é sintética, custos estimados e nenhuma alteração de infraestrutura é executada. Mostrar seleção e seed 42. |
| 0:35–1:25 | Executar pico previsível. Comparar demanda/capacidade, fila e réplicas. Mostrar o ranking SLO/custo e a seleção aprovada pelo backend como decisões distintas. Atraso de ativação explica o backlog reativo. |
| 1:25–1:55 | Executar previsão incorreta e pico inesperado. Antecipar pode custar mais sem melhorar SLO; em cenários sem alternativa segura, destacar a abstenção do validador. |
| 1:55–2:40 | Abrir `/explanations` pelo terminal. Explicar saída estruturada, citações verificadas e auditoria. Se provedor configurado, usar comando ao vivo abaixo; caso contrário, anunciar explicitamente modo offline e teste de SDK com transporte simulado, sem atribuí-los a geração real. |
| 2:40–3:20 | Executar exemplo de rejeição abaixo: proposta reativa tem SLO violado, guard rejeita e fallback escolhe alternativa segura. Ressaltar aprovação humana para qualquer ação futura. |
| 3:20–4:00 | Rodar benchmark; mostrar 108 pares e previsão falsa desfavorável. Abrir gráfico e matriz completa para mostrar que nenhum cenário foi omitido. |
| 4:00–5:00 | Mostrar diagramas: um motor compartilhado, adaptador sem ferramentas, HPA separado. Citar evidência P6 de 1→4 pods e limites da comparação; encerrar com limites de produção e próximos experimentos. |

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

Mostrar `comparison.svg`, `comparison.md` e `report.json`. Perguntas esperadas: por que não usar apenas HPA, efeito de erro de previsão, origem do preço, diferença entre ranking e aprovação, risco de fila volátil e como validar em produção. Responder com [premissas](SIMULATION.md), [benchmark](BENCHMARKS.md) e [observação local](KUBERNETES.md), sem prometer ganhos externos.
