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

## P15 — Atraso de decisão separado do startup

Sem cluster: `python3 local/p15/recalibrate.py` relê `evidence/p13/observed.json` e grava `evidence/p15/calibration.json` (mesmos dados `observed`, simulação `estimated`). O `Config` ganhou `decision_delay_ticks` (padrão 0): a política reativa decide com demanda e backlog de `decision_delay_ticks` ticks antes; a antecipativa não muda; benchmarks e `evidence/p14/results.json` idênticos.

**Derivação (regra fixada antes de ver o MAE).** `first_scale_after_load_seconds` (32,8; 21,1; 28,4 s) inclui os 20 s iniciais de carga baixa. Descontados: 12,8; 1,1; 8,4 s entre o degrau de carga e a criação do 1º pod (mediana 8,4 s). A reativa simulada já tem 1 tick (10 s) embutido, por usar a demanda do tick anterior. Atraso extra = `max(0, round((8,4 − 10)/10))` = **0 ticks**. A hipótese da P13 (HPA leva ~20–30 s para decidir) vinha de ler esse valor sem descontar a carga baixa; os dados não a sustentam.

| MAE médio (3 rep.) | Antigo | P13 | P13 + atraso derivado (0) | Sensib. 1 tick* | Sensib. 2 ticks* |
| --- | --- | --- | --- | --- | --- |
| Backlog (documentos) | 36,5 | 41,3 | 41,3 | 36,4 | 44,8 |
| Throughput (doc/s) | 3,37 | 3,63 | 3,63 | 3,38 | 3,33 |
| Atraso estimado (s) | 6,87 | 6,97 | 6,97 | 7,02 | 9,55 |

\* Não derivados dos dados; só delimitam o efeito. Não escolhidos pelo erro.

Leitura: o atraso derivado é 0, então a configuração P13 não muda e o MAE segue 41,3 (sem melhora). Atraso de 1 tick aproxima o backlog do valor antigo (36,4 vs 36,5), mas piora o atraso estimado, e 2 ticks piora backlog e atraso; com 3 repetições e diferenças menores que a variação entre repetições, isso não demonstra ganho e não foi adotado (sem ajuste até o número melhorar). Próxima hipótese: filas por pod (o cluster balanceia por pod; o motor usa FIFO central e taxa fluida), a testar numa fase própria.

## Filas por pod (P20, 2026-11-13)

Hipótese deixada pela P15: o erro restante vem do FIFO central do motor, contra uma fila por pod no cluster. Teste sem cluster, com `local/p20/perpod.py` sobre `evidence/p13/observed.json` (3 repetições): o mesmo calendário de réplicas do motor (reativa, 294 doc/min, ativação de 1 tick) alimenta três modelos de fila. `even`: chegadas divididas igualmente entre os pods ativos, pods novos com fila vazia. `sticky`: chegadas só nos pods originais (limite superior de pods novos ociosos). Resultado em `evidence/p20/results.json` (backlog observado × estimado, MAE em doc):

| Repetição | Fila central (motor) | Por pod, `even` | Por pod, `sticky` |
| --- | --- | --- | --- |
| 0 | 54,7 | 32,8 | 309,9 |
| 1 | 26,5 | 21,6 | 331,9 |
| 2 | 42,8 | 18,0 | 317,2 |
| Média | 41,3 | 24,1 | 319,7 |

Leitura: dividir a carga entre filas por pod reduz o MAE médio de 41,3 para 24,1 doc (−42%, nas 3 repetições); o extremo `sticky` é bem pior. No pico observado, 93–97% do backlog ficou no pod mais carregado e só 2 pods tinham fila, então o cluster fica entre os dois modelos: pods novos recebem parte da carga, não a divisão igual. A hipótese se sustenta em parte, mas a melhora não prova o mecanismo (pode vir do timing das ativações). Limites: 3 repetições, uma curva de carga, nenhum parâmetro novo ajustado pelo erro. O motor e `benchmarks/results` não foram alterados: adotar filas por pod no motor mudaria os benchmarks e é decisão separada.

