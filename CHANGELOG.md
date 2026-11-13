# Changelog

Entregas por fase. O histórico Git não é reescrito; os commits desta rodada (P8–P14) seguem Conventional Commits. Dados são sintéticos e valores estimados, salvo indicação de métricas observadas no Kind local.

## P20 — Filas por pod (hipótese da calibração)
- `local/p20/perpod.py` reanalisa `evidence/p13/observed.json` sem cluster → `evidence/p20/results.json`. MAE do backlog 41,3 (fila central) → 24,1 doc (uma fila por pod, chegadas iguais); o extremo `sticky` dá 319,7. Motor e benchmarks inalterados; leitura e limites em `docs/CALIBRATION.md`.

## P18 — Chamada real à LLM
- Dashboard: opção "Explicar com LLM" (`use_llm`) e selo da origem da explicação (`llm`/`fallback`/`offline`, com o motivo da rejeição), com teste; capturas `docs/p18-dashboard-llm-*.png` do build de produção com a API real.
- Diagrama de arquitetura refeito com o Archify 3.2.0 (estado P0–P19, evidências do commit `d56b599`); `docs/peakguard-archify.png` atualizado.
- `PEAKGUARD_LLM_BASE_URL` opcional (provedor compatível com a API OpenAI; `json_object` com schema no prompt). `local/p12/llm_sweep.py` e `local/p12/llm_chart.py`; `evidence/p18/` e `docs/p18-llm.svg`. Command A+ em 8 cenários: 6/8 aceitas pelo checker, 2 no fallback; detalhes em `docs/VERIFICATION.md`.

## P17B — Coleta intercalada da antecipativa
- `local/p17/experiment.py collect --order interleaved --output evidence/p17b`, com `loadavg` e `docker stats` por repetição e análise com/sem repetições carregadas. Conclusão da P17 mantida (backlog máx. 185 → 2,8 doc, +37% de réplicas-minuto); tabela em `docs/KUBERNETES.md`.

## P19 — Apresentação v3
- README e `docs/DEMO.md` com os resultados de P15–P17 (cada claim cita o artefato), roteiro "hipótese → medição → nova hipótese" e "Próximos passos" revisados; o resultado negativo da P15 e o limite da P17 (previsão perfeita, uma curva) ficam visíveis. P18 (chamada real à LLM) não foi executada: sem chave.
- Capturas `docs/p7-dashboard.png` e `docs/p7-abstention.png` refeitas do build de produção (`docker compose up --build`); as de `docs/p14-*.png` já eram do visual atual.

## P17 — Antecipativa no Kubernetes
- `manifest_diff(..., schedule_start=...)` e `POST /manifest-diff` com `schedule_start`: ScaledObject com gatilho `cron` do KEDA derivado do calendário previsto e CPU como piso; nada aplicado pela API.
- `local/p17/` (instalação só do KEDA e experimento): HPA reativo × KEDA cron no Kind local, 3 repetições cada. Backlog máximo observado 166 → 3,3 doc com +32% de réplicas-minuto (custo hipotético); detalhes em `docs/KUBERNETES.md`.

## Interface — investigação de capacidade
- Dashboard redesenhado como investigação: cenários viram perguntas, o relatório mostra o comando, um log de eventos derivado das séries (`frontend/lib/investigation.mjs`, com testes), o achado e o veredito do validador.
- Base escura com brilho violeta, gradiente violeta→magenta só em ações e destaques, cores fixas por grandeza (demanda, reativa, antecipativa, risco) e tipografia Ubuntu/Ubuntu Mono.
- Pontos do Pareto e rótulos dos eixos em HTML (o SVG esticado deformava círculos e texto); layout sem rolagem horizontal no celular; foco visível e `prefers-reduced-motion` respeitado.

## P16 — Paridade da API e do dashboard
- API: `arrivals` e `ewma_window` nas requisições com `scenario`/`seed`; `decision_delay_ticks` no `config`. Padrão idêntico às respostas anteriores (`tests/test_p16.py`).
- Dashboard: seletor de chegadas, percentil de risco (`risk_appetite`) e rótulo `synthetic` para chegadas estocásticas.

## P15 — Atraso de decisão do controlador
- `Config.decision_delay_ticks` (padrão 0; só política reativa), separado de `activation_delay_ticks`; benchmarks inalterados.
- `local/p15/recalibrate.py` reanalisa `evidence/p13/observed.json` sem cluster → `evidence/p15/calibration.json`. Atraso extra derivado = 0 ticks; o MAE de backlog não melhora (41,3 doc). Próxima hipótese: filas por pod (`docs/CALIBRATION.md`).

## P14 — Apresentação v2
- README e `docs/DEMO.md` com resultados P9–P13, roteiro de 5 minutos, três perguntas técnicas e "Próximos passos".
- `local/p14/results.py` gera `evidence/p14/results.json` (reproduzível, conferido por `tests/test_p14.py`).
- Capturas reais do dashboard: `docs/p14-fiscal.png` e `docs/p14-pareto.png`; rótulos dos cenários fiscais e eixo zero no gráfico de Pareto.
- Eixos com valores redondos e inteiros (`frontend/lib/axis.mjs`, com testes) e rótulos em HTML, legíveis em qualquer largura; capturas refeitas a partir do build de produção (Docker Compose), com o Pareto no cenário `unexpected_peak` citado no roteiro.

## P13 — Calibração contra o Kind
- Kind recriado em Kubernetes v1.36.4; 3 repetições em `evidence/p13/` (capacidade 294 doc/min por réplica, startup mediano de 12 s).
- `docs/CALIBRATION.md`: os parâmetros calibrados não reduziram o erro do simulador (MAE de backlog 36,5 → 41,3 doc). Script em `local/p13/calibrate.py`, fora do CI.

## P12 — Governança
- Regras do validador em `peakguard/rules.yaml`, validadas na importação (falha rápida); dependência `pyyaml`.
- `POST /manifest-diff`: diff de HPA ou ScaledObject para PR, sem aplicar nada.
- Checker de fidelidade: número fora das evidências ou URL no texto da LLM aciona o fallback determinístico. Chamada real à LLM não executada (sem chave).

## P11 — Pareto e FinOps estendido
- `ewma_window` na política reativa; varredura (56 combinações, máx. 200) com cache e comando `python -m peakguard sweep`; fronteira de Pareto custo × ticks fora do SLO.
- `peakguard/finops.py` (requests, bin-packing, ocioso, spot × on-demand, scale-to-zero; preços hipotéticos), `POST /pareto`, `POST /finops` e gráfico de Pareto no dashboard.

## P10 — Error budget e previsão com incerteza
- SLO com consumo de budget, burn rate multi-janela (1h/5m e 6h/30m), custo por minuto de budget preservado, MAE/MAPE.
- `risk_appetite` (p50/p80/p90) em `simulate`, `compare` e na API; `POST /error-budget`.

## P9 — Cenários fiscais e multi-seed
- Quatro cenários do calendário fiscal, chegadas `poisson`/`burst`, `multiseed` com IC 95% e checagem pela Lei de Little.

## P8 — Reprodutibilidade
- Dockerfiles, `compose.yaml`, prova de clone limpo e Kind fixado em v1.36.

## P0–P7 — Primeira rodada
- Especificação, simulador determinístico, API FastAPI, dashboard Next.js, explicação assistida por IA com validação determinística, benchmarks, demonstração Kubernetes opcional e documentação de apresentação (ver `ROADMAP.md` e `docs/VERIFICATION.md`).
