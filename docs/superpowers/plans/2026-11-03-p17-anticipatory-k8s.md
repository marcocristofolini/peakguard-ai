# P17 — Antecipativa no Kubernetes (Kind local)
1. RED/GREEN: `manifest_diff(..., schedule_start=<datetime UTC>)` acrescenta ao ScaledObject gatilhos `cron` do KEDA derivados do calendário previsto da proposta antecipativa (janela = ticks em que a previsão exige > min réplicas; início antecipado em `forecast_horizon_ticks`, arredondado para o minuto; `desiredReplicas` = réplicas previstas, limitado ao máximo). CPU continua como piso reativo. API: `schedule_start` opcional em `POST /manifest-diff`; nada aplicado.
2. Exige proposta antecipativa aprovada para gerar cron; HPA ignora `schedule_start` (422).
3. `local/p17/experiment.py`: reusa `local/p13/calibrate.py` (kube, prom, repetition). 3 rep. HPA reativo (`documents`), depois troca: apaga HPA → aplica ScaledObject gerado (novo horário por repetição) → 3 rep.; ao final apaga o ScaledObject e restaura o HPA. Nunca os dois ao mesmo tempo (checado antes de cada repetição).
4. Métricas: backlog máximo, 1ª escala relativa ao início da carga, réplicas-minuto (pods prontos, `count(up)`); custo hipotético. Simulação reativa × antecipativa no mesmo trace (Config P13, alvo 70%).
5. Cluster: `up.sh`, KEDA 2.21 só (sem OpenCost, sem `documents-keda`); `down.sh` ao final.
6. Docs: `docs/KUBERNETES.md`, `evidence/p17/`, ROADMAP, STATUS, CHANGELOG. Suíte completa uma vez no fim.
