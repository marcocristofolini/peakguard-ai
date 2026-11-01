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

A imagem Kind está fixada por digest no script; a execução verificada usou Kubernetes v1.37.0 e Kind v0.33.0. O workload usa Python 3.14 Alpine; Prometheus usa v3.2.1; metrics-server v0.8.0. Não há cloud, LoadBalancer externo ou volume persistente. Downloads de imagens e manifests exigem internet na primeira execução. Os scripts reaplicam os mesmos recursos e reutilizam o cluster existente; não criam clusters adicionais. Após mudar o código da imagem, recrie a demonstração para garantir novos pods e métricas limpas.

O procedimento de limpeza remove somente o cluster de nome fixo, sendo repetível. Imagens Docker permanecem como cache reutilizável. Não remove clusters, imagens ou volumes de outros projetos. O kubeconfig dedicado contém credenciais apenas desse cluster local e nunca deve ser versionado.

## Workload e limites

Cada pod recebe POST `/documents`, enfileira documento sintético e retorna 202; fila cheia retorna 429. Um consumidor gasta aproximadamente 0,1 segundo de CPU por documento. Isso simula trabalho computacional, não OCR ou processamento real de documentos. A fila é volátil e limitada a 1.000 itens por pod; reinícios e reduções de escala podem perder itens. Não há promessa de entrega durável.

A aplicação tem requests de 100m CPU/32 MiB e limits de 500m/128 MiB, usuário não root, filesystem somente leitura, sem capacidades adicionais ou token Kubernetes. O gerador tem limits de 200m/64 MiB e Prometheus de 500m/512 MiB, com armazenamento efêmero de até 512 MiB e retenção de uma hora. Metrics-server tem limite de 500m/256 MiB. O teto do container Kind também limita os componentes do sistema.

A carga nominal é controlada: 20 segundos a 1 documento/s, 90 segundos a 12/s e 20 segundos a 1/s, total de 1.120 tentativas. Os logs registram admissões, rejeições, erros e tempos efetivos em 13 intervalos. Latência do gerador e contenção podem reduzir a taxa efetiva. Não ocultar erros nem equiparar taxa nominal a throughput observado.

## Métricas e autoscaling

HPA `autoscaling/v2`, mínimo 1 e máximo 4, busca CPU média de 70% do request de 100m (70m por pod). Não é 70% do limite de 500m. Metrics-server fornece CPU; Prometheus coleta a aplicação, sem servir como fonte do HPA. A estabilização de redução é de 180 segundos. Readiness e atualização das métricas introduzem atrasos reais.

Escolha HPA: demonstra reação à carga com recursos Kubernetes nativos. KEDA exigiria instalação de operador e outra integração de métricas, sem necessidade para este ensaio. OpenCost não foi instalado: Kind não possui preço real atribuível ao pod; uma tarifa sintética explícita evita apresentar custo inventado como observado.

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
