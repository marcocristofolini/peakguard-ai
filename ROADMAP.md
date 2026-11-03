# PeakGuard AI — roadmap executável

## Objetivo e limites
Criar um demonstrador local de capacidade preditiva e FinOps para serviços de processamento de documentos. Comparar políticas de escalonamento sob cargas idênticas, estimar custo e risco de SLO e permitir explicações assistidas por IA. Nenhum acesso presumido à infraestrutura da Contabilizei; usar dados sintéticos e identificar estimativas.

## Princípios
- O mecanismo de previsão não tem autoridade para alterar infraestrutura; toda proposta passa por políticas determinísticas e aprovação humana.
- Comparações justas: mesma carga, seed, capacidade por réplica, latência, preços e limitações.
- Simulação offline deve funcionar sem LLM, cluster, conta cloud, banco de dados ou credenciais.
- Preferir poucas dependências, funções simples, tipos e testes. Sem orquestração de agentes ou microserviços prematuros.
- Medir resultados antes de afirmar melhorias. Incluir cenários onde antecipar é pior.

## Métricas e unidade
- workload: documentos/minuto; throughput: documentos processados/minuto; backlog: documentos pendentes
- capacidade: documentos/minuto por réplica; capacidade total: réplicas ativas x capacidade unitária
- custos: BRL por réplica-hora; custo total calculado por duração do intervalo; custo por 1.000 documentos
- confiabilidade: atrasos na fila, violações de SLO (por exemplo, tempo máximo em fila) e saturação
- dados: marcar synthetic, predicted, estimated ou observed; identificar fontes e premissas
- simulação discreta: intervalos regulares (ex.: 1 minuto), sem inconsistência dimensional
- previsão antecipativa: horizonte definido; evitar usar dados do futuro de maneira indevida

## P0 — especificação e estrutura
Entrega:
- Estrutura Python enxuta e documentação com contrato da simulação
- Fixtures sintéticas versionadas; explicação de parâmetros e unidades
- Hipóteses, limites e fórmula de custo documentados
Aceite: README reproduz cenário, estrutura organizada, sem dependências supérfluas.
Não implementar API nem UI.

## P1 — simulador determinístico
Entrega:
- Motor com séries de demanda, capacidade, fila, custo e eventos por tick.
- Política reativa simples (escala após limiar de utilização/backlog) e antecipativa com previsões.
- Simular atraso de ativação de réplica e cooldown iguais para políticas quando aplicável.
- Previsões geradas por função simples e explícita; incluir previsão errada e avaliação de erro.
- Regras para min/max réplicas, disponibilidade, custo e restrições de SLO.
- CLI: executar cenário, comparar políticas, exportar JSON.
- Quatro fixtures: baseline estável, pico previsível, pico inesperado e previsão falsa.
- Testes pytest: reprodutibilidade, custo por tempo, backlog, throughput, limites, casos extremos, erro de previsão.
Aceite: mesmo input + mesma seed geram resultado idêntico; contas e unidades corretas; todas as políticas usam mesma carga.
Não usar IA, API, frontend, Kubernetes ou infraestrutura externa.

## P2 — API FastAPI
Entrega:
- Endpoints de listagem de cenários, execução simulada e comparação de políticas.
- Tipos e validações de entrada/saída; limites contra cenários excessivamente grandes.
- Erros claros e documentação da API.
- Testes de endpoint, incluindo entradas inválidas.
Aceite: execução local reproduz resultados do motor; não duplicar lógica no controller.
Não adicionar autenticação complexa, banco de dados ou filas para MVP.

## P3 — dashboard Next.js
Entrega:
- Tela de seleção de cenários e parâmetros essenciais.
- Gráficos de demanda, capacidade, backlog, custo, alertas de SLO e comparação A/B.
- Indicadores sintéticos/estimados visíveis, loading e erro.
- Recomendação determinística visível, com trade-offs e custo.
Aceite: dados reais retornados pela API, captura de tela verdadeira e build reproduzível.
Evitar design system e dependências amplas sem necessidade.

## P4 — explicação assistida por IA
Entrega:
- Adaptador opcional de LLM, não obrigatório para execução local.
- Contexto restrito a resultados de simulação e políticas aprovadas; saída estruturada.
- Sem credenciais no código; exemplos em .env.example.
- Rejeitar qualquer recomendação que descumpra min/max, custo ou SLO.
- Fallback determinístico sem API de IA e trilha de auditoria curta.
- Testes de resposta inválida, ausência do provedor, alucinação e proposta insegura.
Aceite: IA explica, mas nunca autoriza nem aplica alterações de infraestrutura; offline continua funcional.
Não criar frameworks de múltiplos agentes.

## P5 — benchmarks e validação
Entrega:
- Executar políticas nas mesmas fixtures e sementes; relatório machine-readable.
- Medir throughput, backlog, custo por volume, minutos em violação e falhas por cenário.
- Incluir análise de sensibilidade a erro de previsão e custo operacional.
- Mostrar limitações; sem percentual fictício ou seleção oportunista de experimentos.
Aceite: relatório reprodutível por comando único, resultados iguais em seeds fixas.

## P6 — integração opcional Kubernetes
Entrega:
- Cluster local Kind somente se acrescentar demonstração real.
- Workload de fila com métricas exportadas, Prometheus; integrar KEDA/HPA quando aplicável.
- OpenCost opcional, com distinção entre preço estimado e custo real observado.
- Validação de recursos e limpeza do ambiente.
Aceite: manifests e scripts idempotentes, sem serviços cloud pagos, sem efeitos externos.
Não é bloqueador para apresentar MVP.

## P7 — apresentação e documentação
Entrega:
- README objetivo com arquitetura, instruções, testes e screenshots reais.
- Demo de até 5 minutos: pico, comparação, custo, explicação e bloqueio de proposta insegura.
- Trade-offs, limitações, segurança e próximos experimentos.
- Revisão de over-engineering e verificação de segredos.
Aceite: pessoa externa consegue rodar a demo local e reproduzir benchmarks.

## Fases v2 (P8–P14)
P0–P7 estão concluídas. A segunda rodada aprofunda o rigor técnico; a especificação de cada fase está em `docs/prompts/`.

- P8 (concluída) — Reprodutibilidade: Dockerfiles, `compose.yaml`, prova de clone limpo e Kind fixado em v1.36.
- P9 (concluída) — Cenários do calendário fiscal brasileiro (sintéticos), chegadas estocásticas, multi-seed com IC 95% e checagem pela Lei de Little.
- P10 (concluída) — Error budget, burn rate multi-janela, custo por minuto de budget preservado e previsão por percentil com MAE/MAPE.
- P11 (concluída) — Fronteira de Pareto custo × SLO e modelo FinOps estendido (requests, bin-packing, ocioso, spot, scale-to-zero).
- P12 — Governança: validador como policy-as-code, diff de manifesto para PR e checker de fidelidade da explicação da LLM.
- P13 — Calibração do simulador contra medições do Kind local.
- P14 — Apresentação v2 com os novos resultados.

## Contrato de trabalho
Cada execução implementa só uma fase pedida, testa mudanças relacionadas e atualiza docs/STATUS.md (até 20 linhas). Não fazer push nem deploy automaticamente. Não refatorar áreas não relacionadas. Se o simulador mudar, regenerar `benchmarks/results`: o CI (`ci-python`) compara os resultados commitados. Ao encerrar, responder em até oito linhas com entrega, arquivos, comandos de teste e bloqueios.
