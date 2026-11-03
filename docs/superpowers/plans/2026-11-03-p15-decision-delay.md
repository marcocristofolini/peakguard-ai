# P15 — Atraso de decisão do controlador
1. RED: `tests/test_p15.py` — atraso 0 == motor atual (hash de resultado idêntico ao default); atraso maior não reduz `max_backlog_docs` num pico; antecipativa inalterada; validação de `decision_delay_ticks` (inteiro >= 0).
2. GREEN: `Config.decision_delay_ticks` (padrão 0, não negativo, inteiro). Em `simulate`, histórico (demanda suavizada, demanda anterior, backlog) por tick; a política reativa e o `_safe_target` usam o valor de `tick - delay` (antes de `delay` ticks: zeros). Antecipativa usa valores atuais.
3. Rodar `tests/test_benchmarks.py` e `tests/test_p14.py`: benchmarks e `evidence/p14/results.json` não mudam.
4. Recalibração sem cluster: `local/p15/recalibrate.py` lê `evidence/p13/observed.json` e reusa `local/p13/calibrate.py`; atraso extra = max(0, round((mediana(first_scale) − carga baixa inicial − 1 tick embutido) / tick)), regra fixada antes de ver o MAE; sensibilidade 1 e 2 ticks rotulada como não derivada; grava `evidence/p15/calibration.json`.
5. Atualizar `docs/CALIBRATION.md` (nova tabela, resultado honesto, próxima hipótese: filas por pod), ROADMAP (P15 concluída), `docs/STATUS.md`, `CHANGELOG.md`.
6. Suíte completa uma vez no fim; `/cost` não acessível ao agente (registrar como nos outros).
