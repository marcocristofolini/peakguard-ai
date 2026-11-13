# P6 — demonstração Kubernetes local

## Reprodução e isolamento

Pré-requisitos: Docker local, kubectl, Kind (`/tmp/kind` ou variável `KIND`), Python 3.12+, bash e rg. Nenhuma instalação global é feita pelos scripts. Ambiente verificado: WSL2, 6 CPUs, 19 GiB RAM (17 GiB disponíveis) e 920 GiB livres. Não execute simultaneamente outras cargas pesadas.

Na raiz:

```bash
bash local/p6/up.sh
python3 local/p6/experiment.py
bash local/p6/down.sh
```

O setup cria somente `peakguard-p6`, com kubeconfig dedicado em `local/p6/.kubeconfig` (ignorado pelo Git). Todas as operações kubectl fixam `kind-peakguard-p6`. O kubeconfig corrente do operador não é utilizado. O container Kind tem limite de 4 CPUs/6 GiB, swap adicional zero. Kind usa container privilegiado para executar o nó Kubernetes; esse privilégio não é concedido ao workload.

A imagem Kind está fixada por digest no script; o digest é o de `kindest/node` **v1.36.4** (release notes do Kind v0.33.0), dentro da matriz testada do KEDA 2.21. A última execução verificada (anterior à fixação) usou Kubernetes v1.37.0 e Kind v0.33.0; o cluster v1.36.4 foi recriado e usado na calibração P13 (`docs/CALIBRATION.md`), sem KEDA/OpenCost. O workload usa Python 3.14 Alpine; Prometheus usa v3.2.1; metrics-server v0.8.0. Não há cloud, LoadBalancer externo ou volume persistente. Downloads de imagens e manifests exigem internet na primeira execução. Os scripts reaplicam os mesmos recursos e reutilizam o cluster existente; não criam clusters adicionais. Após mudar o código da imagem, recrie a demonstração para garantir novos pods e métricas limpas.

O procedimento de limpeza remove somente o cluster de nome fixo, sendo repetível. Imagens Docker permanecem como cache reutilizável. Não remove clusters, imagens ou volumes de outros projetos. O kubeconfig dedicado contém credenciais apenas desse cluster local e nunca deve ser versionado.

## Workload e limites

Cada pod recebe POST `/documents`, enfileira documento sintético e retorna 202; fila cheia retorna 429. Um consumidor gasta aproximadamente 0,1 segundo de CPU por documento. Isso simula trabalho computacional, não OCR ou processamento real de documentos. A fila é volátil e limitada a 1.000 itens por pod; reinícios e reduções de escala podem perder itens. Não há promessa de entrega durável.

A aplicação tem requests de 100m CPU/32 MiB e limits de 500m/128 MiB, usuário não root, filesystem somente leitura, sem capacidades adicionais ou token Kubernetes. O gerador tem limits de 200m/64 MiB e Prometheus de 500m/512 MiB, com armazenamento efêmero de até 512 MiB e retenção de uma hora. Metrics-server tem limite de 500m/256 MiB. O teto do container Kind também limita os componentes do sistema.

A carga nominal é controlada: 20 segundos a 1 documento/s, 90 segundos a 12/s e 20 segundos a 1/s, total de 1.120 tentativas. Os logs registram admissões, rejeições, erros e tempos efetivos em 13 intervalos. Latência do gerador e contenção podem reduzir a taxa efetiva. Não ocultar erros nem equiparar taxa nominal a throughput observado.

## Métricas e autoscaling

HPA `autoscaling/v2`, mínimo 1 e máximo 4, busca CPU média de 70% do request de 100m (70m por pod). Não é 70% do limite de 500m. Metrics-server fornece CPU; Prometheus coleta a aplicação, sem servir como fonte do HPA. A estabilização de redução é de 180 segundos. Readiness e atualização das métricas introduzem atrasos reais.

Na execução original, o HPA nativo demonstrou a reação à carga. Em 2026-11-01, KEDA e OpenCost foram instalados **posteriormente** no mesmo cluster local. O HPA original continua controlando `documents`. KEDA controla uma implantação **separada**, `documents-keda`, por CPU, sem disputar o HPA antigo. OpenCost é um serviço adicional para análise de custos estimados: valores locais não representam faturas cloud.

Prometheus descobre todos os pods da aplicação no namespace e lê `/metrics` a cada 5 segundos. Seu RBAC permite apenas get/list/watch de pods nesse namespace. São exportados contadores de admitidos, processados e rejeitados, tamanho da fila e máximo acumulado de espera em segundos. O máximo é acumulado por processo; não é percentil. Throughput é `sum(rate(documents_processed_total[30s]))`, em documentos/s. Fila não inclui o item em processamento.

Metrics-server usa `--kubelet-insecure-tls` somente neste cluster Kind, por certificados kubelet autoassinados. Essa exceção local não deve ser aplicada a clusters externos. A autenticação do Prometheus na API Kubernetes permanece com CA e token do service account.

Referências usadas: [HPA](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/) e [descoberta de pods Prometheus](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#pod), consultadas via Context7. O manifest oficial metrics-server é fixado na URL de versão em `up.sh`.

## Evidências e comparação

`evidence/p6/observed.json` registra versões, amostras de réplicas, resultados brutos Prometheus, logs de carga e status HPA. Valores capturados são `observed`, a origem da carga é `synthetic`. Tempos e resultados observados não são determinísticos entre execuções. Falhas de Job, ausência de métricas e ausência de crescimento de réplicas fazem o experimento falhar.

`evidence/p6/simulated.json` contém as políticas do motor sobre a mesma curva nominal (13 ticks de 10 segundos), teto de 4 réplicas e capacidade assumida de 300 documentos/minuto/réplica. Essa capacidade equivale idealmente a 5 documentos/s sob limite de 500m e trabalho de 0,1 CPU-s, mas não foi calibrada como capacidade medida. A previsão desta referência conhece a curva nominal. Os tempos de ativação/cooldown do modelo não equivalem às janelas do HPA.

O simulador usa FIFO central e taxas fluidas; Kubernetes usa filas independentes por pod e distribuição por conexão. HPA olha CPU, política reativa simulada olha demanda/fila. A comparação serve para confrontar tendências e atrasos, não afirmar igualdade de algoritmos, desempenho ou SLO. A coleta dura além da carga para observar drenagem; o motor termina ao fim de seu horizonte. Máximo acumulado de espera observado não equivale ao tempo em violação calculado pelo motor.

O custo é `estimated`: integração pelo método de retângulos à esquerda das réplicas prontas amostradas × duração em horas × BRL 1,2/réplica-hora. Não inclui pods pendentes, nó Kind, monitoramento, eletricidade, operador ou preço cloud. É uma projeção sobre réplicas observadas, nunca custo real faturado. Não se alega economia nem confiabilidade produtiva.

## Resultado desta execução

Evidência em `evidence/p6/observed.json`: 1.120 admissões e 1.120 processamentos observados, zero rejeições e zero erros do gerador. Réplicas prontas variaram de 1 a 4. A coleta cobriu aproximadamente 164,67 segundos; máximo de throughput amostrado foi 14,20 documentos/s (janela de 30 s), maior backlog amostrado 175 documentos e maior espera acumulada 35,93 segundos. Ao fim, backlog era zero e Prometheus tinha quatro targets saudáveis.

A integração de réplicas prontas resultou em BRL 0,164768 **estimados**, sob tarifa arbitrária de BRL 1,2/réplica-hora. Na referência simulada de 130 segundos, o reativo teve backlog máximo de 210 documentos e custo estimado BRL 0,133333; o antecipativo teve backlog zero e BRL 0,123333. Ambos processaram os 1.120 documentos simulados, com zero minutos em violação do SLO de fila de dois minutos. Os horizontes de custo e mecanismos são distintos; não subtrair esses valores como ganho real.

Os quatro pods observados contrastam com o pré-escalonamento idealizado, mas esta execução não testa uma política antecipativa real no Kubernetes. Autoscaling observado valida funcionamento do HPA, não equivalência ao controlador simulado. Erros, indisponibilidade de métricas e ausência de escala não são tratados como sucesso. O setup foi reaplicado com sucesso no mesmo cluster; a limpeza foi exercitada após preservar os resultados.

## KEDA e OpenCost instalados após o ensaio original (2026-11-01)

Instalação comprovada no cluster Kind `peakguard-p6`:
- KEDA Helm chart `2.21.0`, operador, metrics API server e admission webhook em `keda` (pods Ready).
- `ScaledObject/documents-keda` com trigger CPU 70%, limites 1–3, estado Ready/Active, HPA `keda-hpa-documents-keda`. A implantação `documents-keda` é isolada da implantação `documents` do ensaio original.
- OpenCost Helm chart `2.5.33`, aplicação `1.121.3` no namespace `opencost`, pod 2/2 Ready; Prometheus `peakguard-p6/prometheus:9090`. O Prometheus desta demo não inclui, necessariamente, todas as métricas de kube-state-metrics utilizadas por relatórios completos do OpenCost. Custo nominal é estimado.
- `local/p6/up.sh` fixa Kubernetes **v1.36.4**, dentro da matriz declarada do KEDA 2.21 (1.34–1.36). A execução anterior em v1.37.0 ficou fora dessa matriz; a verificação em v1.36.4 está pendente (cluster não foi recriado na P8).

Instalação/reinstalação reprodutível (Docker/Kind, Helm 3 e internet):

```bash
bash local/p6/up.sh
bash local/p6/install-keda-opencost.sh
export KUBECONFIG="$PWD/local/p6/.kubeconfig"
kubectl -n keda get pods
kubectl -n peakguard-p6 get scaledobject documents-keda
kubectl -n peakguard-p6 get hpa
kubectl -n opencost get pods
```

Visualize o OpenCost localmente (em terminal separado):

```bash
kubectl -n opencost port-forward svc/opencost 19090:9090
# UI: http://127.0.0.1:19090
```

O OpenCost não equivale a uma fatura de cloud: Kind não tem preços faturados. O ScaledObject KEDA é uma demonstração separada; não prova que o sistema antecipativo simulado controla o cluster. Encerre port-forward com Ctrl+C. Para remover **todo o cluster dedicado**, use `bash local/p6/down.sh` quando terminar os testes.

## P17 — Antecipativa no Kubernetes (2026-11-03)

Natureza: **observed local cluster** (Kind `peakguard-p6`, Kubernetes v1.36.4, WSL2, 4 CPUs/6 GiB) × **simulation** (`estimated`). Carga `synthetic` (Job P6, 1.120 tentativas). Custo **hipotético** (BRL 1,2/réplica-hora × minutos de pods prontos). Nada roda no CI.

Reprodução (ação explícita no cluster de demonstração; o script aplica e remove HPA/ScaledObject):

```bash
bash local/p6/up.sh
bash local/p17/install-keda.sh          # só KEDA 2.21; sem OpenCost e sem documents-keda
python3 local/p17/experiment.py collect --repetitions 3   # evidence/p17/observed.json
python3 local/p17/experiment.py analyze                   # evidence/p17/results.json
bash local/p6/down.sh
```

**Estratégias no mesmo Deployment `documents`, nunca ao mesmo tempo.** Antes de cada repetição o script remove os controladores, drena e volta a 1 pod. Reativa: HPA original (CPU 70%). Antecipativa: o HPA é apagado e se aplica um `ScaledObject` gerado por `manifest_diff(..., schedule_start=...)`, o mesmo gerador de `POST /manifest-diff` (que só gera texto). O manifesto tem CPU 70% como piso reativo e um gatilho `cron` com `desiredReplicas: 4`. A janela vem do calendário declarado (curva nominal: pico nos ticks 2–10 de 10 s), antecipada em `forecast_horizon_ticks` (30 s) e arredondada para o minuto (resolução do cron). Antes de cada repetição o script confere que existe um único controlador; ao final remove o ScaledObject e restaura o HPA. Config do motor: P13 (294 doc/min, ativação 1 tick), alvo 70%, máximo 4 réplicas.

O validador determinístico propôs `reactive` para essa curva (mais barato, sem violar o SLO simulado). O cron deriva do calendário, não da política proposta; a antecipativa foi medida como alternativa, não como recomendação.

| Média de 3 repetições | Reativa (HPA) observada | Reativa simulada | Antecipativa (KEDA cron + CPU) observada | Antecipativa simulada |
| --- | --- | --- | --- | --- |
| Backlog máximo (documentos) | 166 (171; 145; 182) | 142 | 3,3 (3; 5; 2) | 0 |
| 1ª escala em relação ao início da carga (s) | +30,7 | +30 | −32,7 (−26; −36; −36) | 0 |
| Réplicas-minuto (janela de ~215 s, 60 s antes da carga até a drenagem) | 9,14 | 7,67 | 12,08 | 9,33 |
| Custo hipotético (BRL) | 0,183 | 0,153 | 0,242 | 0,187 |

Leitura:
- No cluster, a pré-escala reduziu o backlog máximo de 166 para ~3 documentos, com ~32% mais réplicas-minuto (12,08 × 9,14). Isso é uma troca de custo por fila, medida em 3 repetições num único nó com uma curva de carga, e não economia nem ganho de confiabilidade em produção.
- Divergências: (1) o cron escala ~33 s antes da carga, contra 0 s no motor. O minuto arredondado para baixo e o polling do KEDA antecipam mais que o horizonte de 30 s. (2) O fim da janela é arredondado para cima, e o HPA do KEDA usa estabilização de redução padrão (300 s). As réplicas ficam além da necessidade; o motor cancela a escala logo após o pico, daí +2,7 réplicas-minuto observadas. (3) A reativa observada tem backlog maior (166 × 142) e mais réplicas-minuto (9,14 × 7,67), porque o HPA decide por CPU média e o motor por demanda, e a fila é por pod. (4) O backlog observado da antecipativa não é zero, pela fila por pod e pela distribuição por conexão.
- Limites: o calendário conhece exatamente a curva (previsão perfeita); o cenário de previsão errada não foi testado no cluster. 3 repetições, um nó, uma carga.

### Ambiente de medição e ressalvas (P17)

O Kind roda no WSL2 da mesma máquina que o Docker Desktop, o Windows e as demais ferramentas de desenvolvimento. CPU, memória e disco são compartilhados, e qualquer carga externa entra na medição. Os números absolutos descrevem esta máquina e não se transferem para um cluster com nós dedicados. O que esta coleta sustenta é a comparação relativa entre estratégias.

**Interferência identificada.** Builds `docker compose` de outra tarefa rodaram durante parte da coleta, entre 12:05 e 12:17 (horário de Brasília, 03/11). Cruzando os horários de `observed.json` com os artefatos dessas builds:

| Repetição | Janela | Sobreposição |
| --- | --- | --- |
| Reativa 0 | 12:12:55–12:16:01 | Build às ~12:13:00–12:14:05, na subida e no pico da carga, e outra às ~12:15:45, na drenagem |
| Reativa 1 | 12:16:35–12:19:41 | Só os ~15 s iniciais, durante o reset, antes da carga |
| Reativa 2 | 12:20:15–12:23:21 | Nenhuma |
| Antecipativas 0–2 | 12:33:43–12:48:15 | Nenhuma |

Impacto estimado: a repetição mais afetada (reativa 0: 171 doc, 1ª escala em 33 s) não ficou pior que a limpa (reativa 2: 182 doc, 29 s). O atraso de 3–4 s na 1ª escala está dentro da variação entre repetições (backlog reativo de 145 a 182 doc). Sem a reativa 0, a média da reativa vai de 166 para ~164 doc. Como a interferência só atingiu a reativa, ela não favoreceu a antecipativa, e a diferença principal (~166 × ~3 doc) é muito maior que o ruído.

**Limite de método mais relevante.** As estratégias rodaram em blocos: as 3 reativas e, ~10 min depois, as 3 antecipativas. Mudanças de carga da máquina entre os blocos se confundem com o efeito da estratégia, e só a interferência acima pôde ser identificada, porque tinha horário conhecido. A coleta não registrou a carga do host. A refação intercalada, com 5 repetições e registro de carga, está especificada em `docs/prompts/P17B.md`.

Evidências: `evidence/p17/observed.json` (séries Prometheus `query_range`, logs do Job, horários de criação dos pods, manifesto aplicado por repetição) e `evidence/p17/results.json`. A 1ª tentativa da antecipativa abortou: o pré-requisito "1 réplica antes da carga", herdado da P13, é incompatível com a pré-escala. O script passou a dispensá-lo só nessa estratégia, e as 3 repetições reativas já coletadas foram mantidas. Cluster apagado ao final (`No kind clusters found`).

### Coleta intercalada (P17B)

Refação da P17 com 5 repetições por estratégia, alternando reativa e antecipativa (R, A, R, A…), mesmo cluster Kind v1.36.4 + KEDA 2.21, mesmo gerador de manifesto. Registra `loadavg` do WSL antes e depois de cada carga e `docker stats` do nó do Kind no pico (amostras pontuais). Repetições com `loadavg` de 1 min antes da carga acima de 2,0 são marcadas. Evidências: `evidence/p17b/observed.json` e `results.json` (a P17 em `evidence/p17/` não foi alterada). Métricas observadas no Kind local; carga sintética; custo hipotético.

| Métrica (média; mín–máx) | P17 reativa (3, em bloco) | P17B reativa (5) | P17 antecipativa (3, em bloco) | P17B antecipativa (5) |
| --- | --- | --- | --- | --- |
| Backlog máximo (doc) | 166 | 185,4 (143–267) | 3,3 | 2,8 (1–5) |
| 1ª escala vs. início da carga (s) | +30,7 | +49,2 (+39 a +63) | −32,7 | −44,4 (−51 a −37) |
| Réplicas-minuto | 9,14 | 10,07 (8,5–10,9) | 12,08 | 13,77 (13,2–14,4) |

Sem as repetições marcadas (reativa 0, `loadavg` 2,66; antecipativa 3, `loadavg` 3,14): reativa 188,3 doc, 51,8 s e 10,46 réplicas-minuto; antecipativa 2,75 doc, −42,8 s e 13,6 réplicas-minuto. Os demais `loadavg` de 1 min antes da carga ficaram entre 0,76 e 1,77. No pico, o nó do Kind usou 244–268% de CPU na reativa e 166–200% na antecipativa, com ~1 GiB de memória.

**A conclusão não mudou.** A antecipativa continua eliminando o backlog (≈185 → ≈3 doc, mais de 60× menor nos dois conjuntos de dados) ao custo de mais réplicas-minuto (+37% contra +32% na P17). Os intervalos não se sobrepõem: o pior caso da antecipativa (5 doc) é muito menor que o melhor da reativa (143 doc). Excluir as repetições carregadas muda as médias em menos de 4%. O que mudou foi o tamanho absoluto: a reativa ficou pior (166 → 185 doc; 1ª escala de +30,7 → +49,2 s), ainda dentro da faixa da P17B (143–267 doc); os valores absolutos descrevem esta máquina, não um cluster dedicado. Limites herdados: calendário declarado igual à carga (previsão perfeita) e uma única curva.
