# Contrato da simulação P0 + P1

Este demonstrador usa cargas sintéticas e um modelo fluido determinístico. Não acessa infraestrutura da Contabilizei nem executa alterações em infraestrutura real. Todas as decisões afetam apenas a simulação em memória.

## Dados e unidades

| Grandeza | Unidade | Classificação |
| --- | --- | --- |
| Demanda | documentos/minuto | `synthetic` |
| Previsão declarada | documentos/minuto | `predicted` |
| Capacidade por réplica e throughput | documentos/minuto | `estimated` |
| Fila e processados no intervalo | documentos | `estimated` |
| Espera e latência aproximada | minutos | `estimated` |
| Preço | BRL/réplica-hora | premissa sintética |
| Custo | BRL | `estimated` |

Não há dados `observed` de infraestrutura externa. O JSON declara essa ausência em `data_labels`. A demanda passada conhecida pelo controlador continua sendo sintética. Decisões reativas usam somente o tick anterior e a fila acumulada.

## Parâmetros

Os nomes abaixo são os campos de `Config`. Na CLI, substitua `_` por `-` e acrescente `--`. Durações e preços aceitam valores decimais; contagens e intervalos em ticks exigem inteiros.

| Parâmetro | Padrão | Significado |
| --- | --- | --- |
| `tick_minutes` | 1 | duração de um intervalo, em minutos |
| `capacity_docs_per_minute_per_replica` | 100 | capacidade unitária |
| `price_brl_per_replica_hour` | 1.2 | preço sintético, inclusive durante ativação |
| `min_replicas`, `max_replicas`, `initial_replicas` | 1, 10, 1 | disponibilidade mínima, teto e estado inicial ativo |
| `activation_delay_ticks` | 2 | ticks até uma adição fornecer capacidade |
| `cooldown_ticks` | 2 | intervalo mínimo entre duas mudanças de tamanho |
| `forecast_horizon_ticks` | 3 | janela de previsão: tick atual e dois seguintes |
| `target_utilization` | 0.8 | utilização desejada, no intervalo (0, 1] |
| `budget_brl` | 10 | teto de custo total da execução |
| `slo_queue_minutes` | 2 | limite de espera em fila; violação quando espera > limite |
| `base_latency_minutes` | 0.1 | parcela fixa adicionada à espera estimada |

Mínimo de uma réplica; máximo e estado inicial devem ser compatíveis. Capacidade, duração, SLO e horizonte devem ser positivos. Preço e orçamento podem ser zero. Entradas não finitas, séries vazias e taxas negativas são recusadas. Combinações que excedem limites numéricos do motor também são recusadas.

## Ordem do tick e fórmulas

1. Ativar as adições cujo prazo chegou. Réplicas iniciais já começam ativas.
2. A política propõe um total de réplicas usando demanda passada, fila e, na política antecipativa, previsão declarada.
3. Aplicar limites de disponibilidade, SLO e orçamento. Aplicar cooldown; aumentos aguardam ativação, reduções são imediatas. Ao reduzir, cancelar primeiro adições pendentes.
4. Inserir a demanda do tick na fila FIFO e consumir até a capacidade disponível. Cobrar as réplicas ativas e pendentes.

Para duração `dt` em minutos, demanda `d` e capacidade unitária `c`:

```text
chegadas_docs = d * dt
capacidade_docs_por_minuto = replicas_ativas * c
processados_docs = min(fila_anterior_docs + chegadas_docs, capacidade_docs_por_minuto * dt)
fila_final_docs = fila_anterior_docs + chegadas_docs - processados_docs
throughput_docs_por_minuto = processados_docs / dt
custo_tick_brl = (replicas_ativas + replicas_pendentes) * preço_brl_por_replica_hora * dt / 60
custo_total_brl = soma(custo_tick_brl)
replica_horas = soma(replicas_ativas + replicas_pendentes) * dt / 60
custo_por_1000_docs = custo_total_brl / documentos_processados * 1000
```

Sem documentos processados, custo por 1.000 é `null`. Saturação ocorre quando a fila disponível alcança ou excede a capacidade do intervalo; utilização é a fração da capacidade consumida. Não há descarte, limite de fila ou drenagem automática depois do último tick. A fila residual permanece no resumo; adições ainda pendentes não processam documentos, mas são cobradas pelo tempo dentro da execução.

## Espera e SLO

A fila guarda lotes de documentos com o instante de chegada. Todos os documentos de um intervalo chegam no seu início; quantidades fracionárias representam fluido, sem arredondamento a documentos inteiros. A espera de um lote atendido é sua idade no início do tick. Para lotes restantes, mede-se a idade ao fim do tick. `queue_wait_minutes` registra o maior desses valores no intervalo. A latência aproximada soma essa espera a `base_latency_minutes`; um intervalo ocioso tem latência zero.

Esta discretização não modela o tempo de atendimento dentro de cada tick. A resolução da espera é de um tick; não é um percentil de latência nem uma previsão de produção. A idade FIFO permite detectar SLO violado mesmo se a capacidade não consegue escoar a fila. Minutos em violação são o número de ticks violados multiplicado por `dt`, não uma contagem de documentos violados.

O guard de SLO exige pelo menos `ceil((demanda_anterior + backlog / slo_queue_minutes) / c)` réplicas como alvo. Ele bloqueia reduções incompatíveis com a carga já conhecida. Teto e orçamento prevalecem sobre esse alvo: `slo_unachievable` registra o conflito. Ativação, cooldown, picos inesperados e fila já atrasada podem causar violações, registradas como `slo_violation`. O guard não garante SLO sob sobrecarga.

## Políticas e segurança

Reativa: aumenta quando a utilização baseada na demanda anterior excede o alvo ou quando existe backlog. O alvo é `ceil((demanda_anterior + backlog / dt) / (c * target_utilization))`. Reduz abaixo de metade da utilização alvo; entre os limiares, mantém o tamanho.

Antecipativa: usa o maior valor da previsão na janela configurada e propõe `ceil(previsão_maxima / (c * target_utilization))`. A mesma validação determinística de SLO protege contra subprevisões. Ela não lê a realização futura da carga.

Min/max são limites rígidos para o total provisionado; o mínimo também vale para réplicas ativas. Cada proposta reserva o custo de manter o tamanho proposto até o fim: `tamanho * preço * ticks_restantes * dt / 60 <= orçamento_restante`. Essa reserva é conservadora e pode bloquear um pico temporário que caberia em um plano de reduções futuras. Cooldown mantém um tamanho cuja reserva anterior já cobria a execução. Se o orçamento não sustenta as réplicas iniciais por toda a duração, a execução é rejeitada antes de começar. Preço zero dispensa reserva financeira.

Eventos por tick registram escala, ativação, cooldown e restrições. `proposed_replicas` e `safe_target_replicas` permitem auditar a validação. O alvo pode diferir do provisionado por cooldown; o provisionado pode diferir do ativo por ativação.

## Fixtures e previsão

`peakguard/fixtures/*.json` define 24 ticks, baseline de 40 documentos/minuto e ruído inteiro uniforme entre -3 e +3, gerado por `random.Random(seed)`. O pico ocupa os ticks 8 a 14, inclusive. Os tempos reais dependem de `tick_minutes`; o calendário das fixtures usa índices de ticks.

| Fixture | Demanda nominal no pico | Previsão no pico |
| --- | --- | --- |
| `stable` | 40 | 40 |
| `predictable_peak` | 320 | 320 |
| `unexpected_peak` | 320 | 40 |
| `wrong_forecast` | 40 | 320 |

A previsão é uma função explícita do calendário declarado e não contém o ruído realizado. Assume-se que o calendário inteiro esteja disponível desde o início; ele é uma premissa sintética, não um modelo treinado. A janela determina quais previsões a política pode usar. A comparação materializa a carga uma vez e usa as mesmas séries, configuração e seed nas duas políticas. Não altera o gerador aleatório global.

O resumo informa erro absoluto médio: `MAE = média(abs(demanda_realizada - previsão))`, em documentos/minuto. A previsão falsa expõe desperdício potencial; a inesperada expõe ausência de antecipação. Resultados são estimativas do modelo, sem alegação de economia real ou confiabilidade observada. Benchmarks e sensibilidade sistemática ficam para P5.
