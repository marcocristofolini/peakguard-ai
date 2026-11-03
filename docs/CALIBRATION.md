# Calibração do simulador contra o Kind local (P13)

Natureza dos dados: **observed local cluster** (Kind `peakguard-p6`, Kubernetes v1.36.4, WSL2, container limitado a 4 CPUs/6 GiB) × **simulation** (`estimated`). Carga `synthetic` (Job P6: 20 s a 1 doc/s, 90 s a 12 doc/s, 20 s a 1 doc/s; 1.120 tentativas). Custo do Kind: sempre hipotético; não medido aqui. Nada desta fase roda no CI.

Coleta concluída em 2026-11-03 às 13:55 UTC, `python3 local/p13/calibrate.py collect --repetitions 3`; análise `... analyze`. Evidências: `evidence/p13/observed.json` (séries brutas Prometheus via `query_range`, logs da carga, startup dos pods) e `evidence/p13/calibration.json`. No cluster só foi criado o Job de carga; o resto foi leitura.

## Medições (3 repetições)

| Medida | Valor | Método |
| --- | --- | --- |
| service_rate por réplica | mediana 4,9 doc/s (5,0; 4,9; 4,9) = 294 doc/min | mediana de `rate(documents_processed_total[15s])` por pod com fila > 0 (24–29 amostras saturadas por repetição) |
| startup do pod | mediana 12 s (mín. 3, máx. 13; 9 pods) | `creationTimestamp` → condição `Ready` |
| 1ª escala após aplicar o Job | 32,8 s; 21,1 s; 28,4 s | criação do primeiro pod novo; inclui os 20 s iniciais de carga baixa |
| admissões / rejeições+erros | 1.120 / 0 em cada repetição | logs do Job |
| réplicas | 1 → 4 (máximo do HPA) em todas | 3 pods novos por repetição |

O valor antigo (300 doc/min/réplica) vinha de 0,1 CPU-s por documento sob limite de 500m; a medição confirma ~2% abaixo.

## Simulação antes × depois sobre o mesmo trace observado

Motor: política `reactive`, tick de 10 s, `max_replicas=4`, chegadas = admissões observadas por intervalo de 10 s, ticks de demanda zero até o fim da drenagem observada (~155–159 s). Antigo: 300 doc/min, `activation_delay_ticks=2`. Calibrado: 294 doc/min, `activation_delay_ticks=1` (startup 12 s arredondado). Erro = MAE por bin de 10 s, média das 3 repetições. Atraso = estimativa por Lei de Little (backlog ÷ throughput), em ambos os lados.

| Métrica (MAE) | Antigo | Calibrado | Rep. 0 (ant./cal.) | Rep. 1 | Rep. 2 |
| --- | --- | --- | --- | --- | --- |
| Backlog (documentos) | 36,5 | 41,3 | 48,0 / 54,7 | 28,3 / 26,5 | 33,2 / 42,8 |
| Throughput (doc/s) | 3,37 | 3,63 | 3,87 / 4,19 | 3,23 / 3,20 | 3,01 / 3,50 |
| Atraso estimado (s) | 6,87 | 6,97 | 8,40 / 8,90 | 5,87 / 4,50 | 6,33 / 7,52 |

## Leitura

- A calibração de capacidade e startup **não reduziu** o erro: piorou na média (backlog +13%) e melhorou só na repetição 1. A diferença entre parâmetros é menor que a variação entre repetições; não há ganho demonstrado.
- A capacidade antiga já estava correta. O erro dominante é estrutural: o HPA decide por CPU média com métricas de 15 s e leva ~20–30 s até criar pods, enquanto a política reativa simulada reage à demanda no tick seguinte. Reduzir a ativação para 1 tick deixa o modelo ainda mais rápido que o cluster. O atraso de 2 ticks antigo acaba compensando, por acaso, parte da latência de decisão do HPA.
- Próximo passo sugerido (não executado): modelar o atraso de decisão do controlador (medido em `first_scale_after_load_seconds`) separado do startup, e filas por pod.
- Limites: 3 repetições, um único nó, uma curva de carga; o simulador usa FIFO central e taxas fluidas, o cluster tem filas por pod. Não alegar precisão do simulador nem economia real.

Cluster apagado ao final com `bash local/p6/down.sh` (`No kind clusters found`).
