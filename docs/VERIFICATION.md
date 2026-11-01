# Verificação final P7

Execução local de 2026-11-01. Revisão pelo implementador, sem auditor independente. Os resultados abaixo vieram de comandos executados; P6 não foi reexecutada durante P7.

## Instalação e testes

- Instalação nova: `python3 -m pip install --target /tmp/peakguard-p7-clean '.[dev,llm]' --no-cache-dir` — pacote construído e instalado com extras. A partir de `/tmp`, `PYTHONPATH=/tmp/peakguard-p7-clean python3 -m peakguard list` carregou as fixtures instaladas.
- `PYTHONPATH=/tmp/peakguard-p7-clean python3 -m pytest -q` — **103 aprovados**, um aviso prévio de depreciação Starlette/TestClient com HTTPX. SDK testado com transporte HTTP simulado, sem cobrança.
- Em `frontend/`: `npm ci --ignore-scripts --no-audit --no-fund`, `npm test`, `npm run build` — instalação limpa, **3 testes aprovados**, TypeScript e build Next.js 16.4.3 aprovados.
- `python3 -m peakguard.benchmarks --output /tmp/peakguard-p7-benchmark` e `diff -qr benchmarks/results /tmp/peakguard-p7-benchmark` — nenhuma diferença em JSON, Markdown ou SVG.
- `python3 -m compileall -q peakguard local/p6`, `bash -n local/p6/up.sh local/p6/down.sh`, `git diff --check` — sem erros.

## Segurança e dependências

Auditoria npm inicial indicou Next.js crítico e PostCSS/sharp altos. Atualização explícita para Next.js 16.4.3 e respectivo lockfile corrigiu os três pacotes reportados: npm informou **0 vulnerabilidades** após a instalação. A atualização foi seguida de instalação limpa, testes, build e ensaio no navegador. O resultado se limita aos avisos disponíveis no registro naquele momento.

Busca direcionada em 69 arquivos versionáveis encontrou zero correspondências para chaves privadas PEM/OpenSSH e prefixos de chaves OpenAI/AWS. `.env` e kubeconfig local são ignorados pelo Git; `.env.example` tem somente nomes. Busca por padrões não prova ausência de todos os segredos. Dependências Python foram instaladas e testadas, mas não foi executado scanner de avisos de vulnerabilidade Python nem scanner de imagens de contêiner.

Revisão de código: contexto LLM restrito a evidências selecionadas, ausência de ferramentas de escrita, saída estruturada validada, erros brutos do provedor ocultos, mesmos guards no fallback e abstenção sem política segura. API e proxies são locais; não se alega segurança de produção. Importação sem uso nos testes de benchmark foi removida; metadados de packaging e caches TypeScript passaram a ser ignorados. Nenhum framework ou serviço foi removido por especulação.

## Ensaio real da aplicação

API em `127.0.0.1:18080`, dashboard de produção em `127.0.0.1:13000`, backend definido por `PEAKGUARD_API_URL`. Chromium local executou o pico previsível, verificou três gráficos e uma tabela e depois viewport 390 × 844 sem overflow horizontal. Captura de página inteira: `docs/p7-dashboard.png`, inspecionada visualmente. Ela mostra resultados sintéticos realmente retornados pela API.

Exemplo de rejeição do roteiro executado: proposta injetada `reactive`, rejeição `slo`, fallback `anticipatory`, `execution_allowed=false`. Não foi uma resposta de LLM externo. Não havia provedor real configurado nem houve chamada paga; análise externa permanece etapa opcional a executar com configuração do operador antes de apresentá-la como tal.

## Revisão complementar — integração da aprovação

- Corrigida a apresentação do dashboard: ranking por SLO/custo separado da decisão de segurança retornada por `POST /explanations`.
- Adicionado proxy Next.js `POST /api/explanations`, consumo da decisão do backend e estados explícitos de aprovação, abstenção e indisponibilidade.
- Novos testes de frontend cobrem aprovação, ausência de política segura, erro de validação e rejeição de permissão de execução inesperada.
- Fluxo ponta a ponta verificado com API local e frontend: `predictable_peak` produziu `mode=offline`, política `anticipatory` e `execution_allowed=false`; `unexpected_peak` retornou `proposal=null`, motivo `no_safe_policy` e `execution_allowed=false`.
- Chromium headless acionou a interface nos dois cenários, capturou `docs/p7-dashboard.png` e `docs/p7-abstention.png` e não encontrou overflow horizontal a 390 px.
- Auditoria focal: recomendações não autorizam ações, custos permanecem estimados, configurações de produção (autenticação, limites de requisições e segredos) ainda precisam de projeto próprio. Sem alegação de auditoria independente de segurança.

## Atualização de autenticação, dependências e cluster (2026-11-01)

- API: middleware em `local` restringe IP loopback; em `token`, exige Bearer em todas as rotas. Testes incluem credenciais inválidas, ausentes, válidas e falha fechada de configuração. Modo token não substitui TLS, rate limiting ou autenticação do dashboard público.
- A dependência de testes `httpx2` foi adicionada conforme orientação do Starlette. Com `PYTHONPATH=/tmp/peakguard-p7-clean python3 -m pytest -q` e `httpx2` instalado, **108 testes aprovados, sem o aviso anterior de depreciação**.
- Frontend: proxy Next envia token de serviço apenas se configurado em `PEAKGUARD_BACKEND_TOKEN`; 7 testes e build Next.js foram verificados após a mudança.
- Kubernetes: novo cluster Kind foi criado; KEDA 2.21.0 e OpenCost chart 2.5.33 foram instalados com Helm e ficaram Ready. `ScaledObject/documents-keda` Ready/Active com HPA separado; OpenCost pod 2/2 Ready. O uso de Kubernetes 1.37 ultrapassa a matriz testada declarada do KEDA 2.21 (1.34–1.36).
- Nenhuma fatura ou economia cloud foi medida; relatórios OpenCost dependem das métricas disponíveis no Prometheus local.

## Archify e verificações finais da atualização

- Arquitetura em `.archify/architecture-peakguard-ai-20261101-112333/peakguard-architecture.html` gerada de evidências do commit `e8f76f6`. Gates Archify: `validate`, `deliver`, `check` e `browser-check` aprovados com Chromium local. Foi registrada recomendação de revisão perceptual de uma rota com quatro curvas; a topologia não foi alterada.
- Prévia real capturada em `docs/peakguard-archify.png` pelo Chromium. Os componentes do cluster de demonstração são distintos do motor/LLM.
- KEDA e OpenCost são instalações locais do cluster `peakguard-p6`; Helm marcou ambos os releases como `deployed` e os pods como `Running/Ready`. ScaledObject `documents-keda` com status Ready e HPA dedicado. Sem aferição real de gasto cloud.

## Limites da entrega

Diagramas refletem o código: explicações por API/terminal, dashboard comparativo, demonstração Kind separada e nenhum caminho da IA para infraestrutura. README foi verificado por instalação nova, CLI instalada, testes e execução no navegador; isso não substitui teste por pessoa externa em outro sistema. Custos são estimados, inclusive aqueles calculados sobre réplicas observadas. Evidências P6 são históricas, não métricas de cluster atual.

Sem push, merge, deploy externo ou publicação. Próximos passos: ensaio cronometrado do roteiro e, se desejado, configuração explícita do provedor para a sequência de IA real. Antes de produção: revisão independente, segurança de acesso, calibração e durabilidade de filas.
