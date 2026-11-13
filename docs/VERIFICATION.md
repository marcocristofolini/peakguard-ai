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

## Atualização de dependências e CI (2026-11-03)

Após o merge dos PRs agrupados do Dependabot (FastAPI 0.162.0, Pydantic 2.14.2, Starlette 1.10.0, openai 3.42.0, pytest <10, React 19.3.1, TypeScript 7, @types/node 26):

- Instalação nova: `python3 -m pip install --target ~/.cache/peakguard-test-deps '.[dev,llm]'`. O extra `dev` exigia `httpx2<1`, versão inexistente; corrigido para `httpx2>=2,<3`.
- `python3 -m pytest -q` — **108 aprovados, nenhum pulado**, incluindo o adaptador com o SDK openai 3.42 e transporte simulado.
- `python3 -m peakguard.benchmarks` + `diff -qr benchmarks/results` — sem diferenças.
- Em `frontend/`: `npm ci`, `npm test` (**7 aprovados**), `npm run build` (Next.js 16.4.3 com TypeScript 7) e `npm audit --omit=dev` — **0 vulnerabilidades**.
- GitHub Actions: `ci-python` (agora com o extra `llm`, para testar atualizações do SDK), `ci-frontend`, `codeql` e `dependency-review` verdes na `main` e nos PRs do Dependabot.

## Limites da entrega

Diagramas refletem o código: explicações por API/terminal, dashboard comparativo, demonstração Kind separada e nenhum caminho da IA para infraestrutura. README foi verificado por instalação nova, CLI instalada, testes e execução no navegador; isso não substitui teste por pessoa externa em outro sistema. Custos são estimados, inclusive aqueles calculados sobre réplicas observadas. Evidências P6 são históricas, não métricas de cluster atual.

Sem push, merge, deploy externo ou publicação. Próximos passos: ensaio cronometrado do roteiro e, se desejado, configuração explícita do provedor para a sequência de IA real. Antes de produção: revisão independente, segurança de acesso, calibração e durabilidade de filas.

## P8 — Clone limpo com Docker (2026-11-03)

Ambiente: WSL Ubuntu 24.04 com o `docker` nativo da integração WSL do Docker Desktop 4.97 (engine e cliente 29.9.2, Compose v5.6.1). Comandos reais:

```bash
git clone -q . /tmp/pg-clean         # + overlay dos arquivos P8 ainda não commitados
cd /tmp/pg-clean
export PEAKGUARD_API_TOKEN=$(openssl rand -hex 32)
docker compose -p pgclean up --build -d
docker compose -p pgclean down --rmi local -v
```

Resultado: build ok (imagens `api` 202 MB, `web` 393 MB); `api` ficou `healthy`; sem token `GET :8000/scenarios` → 401, com Bearer → 200; `GET :3000/` → 200; `GET :3000/api/scenarios` → 200 com `["stable","predictable_peak","unexpected_peak","wrong_forecast"]` (web→api por `http://api:8000`). Usuários dos containers: `peakguard` (api) e `node` (web). Limpeza: `down --rmi local -v`.

Observação: numa primeira tentativa o comando `docker` não existia no WSL porque o Docker Desktop ainda não tinha iniciado a integração (o link `/usr/bin/docker` → `/mnt/wsl/docker-desktop/cli-tools/usr/bin/docker` só é criado quando ele sobe). Não é necessário usar `docker.exe` nem `WSLENV`; se `docker` não for encontrado, inicie o Docker Desktop e confirme a integração com a distro em Settings → Resources → WSL integration.

Escolha de segurança: modo `local` só aceita loopback, então o compose usa `PEAKGUARD_AUTH_MODE=token` com token obrigatório pelo ambiente (nunca no Git). Portas publicadas só em 127.0.0.1. Reprova após o commit: `git clone https://github.com/marcocristofolini/peakguard-ai.git` no commit `86322e7`, sem overlay, com o mesmo `docker compose up --build`: `api` healthy, 401 sem token, 200 com Bearer, dashboard e `/api/scenarios` 200; limpeza com `down --rmi local -v`. Kind: digest alterado para v1.36.4; cluster não foi recriado nesta fase.

## P12 — Governança (2026-11-03)

- Regras do validador em `peakguard/rules.yaml` (réplicas min/max, teto de orçamento, SLO tolerado, evidência mínima), validadas na importação; arquivo inválido ou ausente falha com `ValueError`. PyYAML adicionado ao `pyproject.toml` (o projeto não tinha parser YAML; necessário para regras e manifestos).
- `POST /manifest-diff` gera HPA `autoscaling/v2` ou ScaledObject KEDA e diff unificado só a partir de proposta aprovada pelo validador. Nada é aplicado; teste bloqueia `kubernetes`, `subprocess` e `socket`.
- Fidelidade: número no `rationale` da LLM que não exista nas evidências enviadas (ou URL) rejeita a resposta e aciona o fallback determinístico. Fixtures de prompt injection em `tests/fixtures/prompt_injection.json`. Todos os testes usam mock.
- **Chamada real à LLM: NÃO executada (bloqueio).** Não há `.env` no repositório nem `OPENAI_API_KEY`/`PEAKGUARD_LLM_MODEL` no ambiente da sessão; o valor da chave nunca foi lido ou impresso. Tokens, latência e custo continuam sem medição. Para executar uma vez: `set -a; . ./.env; set +a; python3 local/p12/real_llm_call.py` (imprime modelo, modo, tokens e latência, nunca a chave) e registrar aqui; custo = tokens × tabela de preços vigente do modelo, a informar pelo operador.

## Chamada real à LLM (P18) — 2026-11-13

Cenário `predictable_peak`, seed 42, `local/p12/real_llm_call.py`. Provedor compatível com a API OpenAI (`PEAKGUARD_LLM_BASE_URL=https://net.beaverai.org/v1`, agregador comunitário), modelo `Cgg507/devstral-small-2507`. Adaptador em modo `json_object` com o schema no prompt (esse provedor não foi testado com `json_schema`).

| Item | Valor |
| --- | --- |
| Tokens de entrada / saída | 5.339 / 169 (observed, relatados pelo provedor) |
| Latência | 20,83 s (observed) |
| Resultado | `mode=fallback`, `audit.status=rejected`, motivo `unsupported_evidence` |
| Custo | não estimado: o provedor não publica tabela de preços |

O que isso mostra: a LLM respondeu JSON válido no schema, mas o checker de fidelidade rejeitou o conteúdo (evidência citada que não existe no contexto enviado) e o fallback determinístico assumiu, com `execution_allowed=false`. O guard funcionou; a qualidade do modelo para esta tarefa fica abaixo do necessário nesta amostra única. Não se generaliza: uma chamada, um modelo, um cenário. O texto bruto da resposta não foi guardado.

Histórico da fase (o que aconteceu antes desse resultado):
- DeepSeek (`deepseek-flash`): a chave autenticou, mas a geração retornou HTTP 402 Insufficient Balance (conta sem saldo), sem tokens cobrados.
- Provedor atual, 1ª tentativa: timeout em 91 s (limite de 90 s do adaptador); nada recebido. O limite subiu para 180 s e houve uma única nova tentativa (transitório), que gerou a linha acima.
- Uma chamada extra de diagnóstico, só para ler o 402 da DeepSeek. Chaves passadas por variável de ambiente; nunca gravadas.

### P18 — varredura com Command A+ (2026-11-13)

`local/p12/llm_sweep.py`: uma chamada por cenário (os 8 de `ALL_SCENARIOS`, seed 42, `Config()` padrão), modelo `cohere/command-a-plus` via gateway compatível (`https://api.xkiro.com/v1`, plano gratuito: preço listado US$ 0/1M tokens, estimado pela listagem do provedor). Dados em `evidence/p18/cohere_command-a-plus.json` (proposta devolvida, auditoria, tokens, latência por cenário; sem a chave).

| Resultado | Cenários |
| --- | --- |
| Aceita pelo checker (`mode=llm`) | `stable`, `predictable_peak`, `fiscal_month_close`, `fiscal_das_day20`, `fiscal_ancillary_obligations`, `fiscal_irpf_april` (6/8) |
| Rejeitada → fallback | `unexpected_peak` (`slo`: escolheu `anticipatory`, que viola o SLO nesse cenário); `wrong_forecast` (`unsupported_evidence`: escolheu `reactive` com valores que não batem com as evidências) |

Totais observados: 33.840 tokens de entrada e 8.582 de saída em 8 chamadas; latência média 7,9 s (máx. 11,6 s). Nenhuma falha de API. As duas rejeições são o validador determinístico e o checker de fidelidade fazendo o trabalho: o fallback assumiu com `execution_allowed=false`. Limites: um modelo, uma execução por cenário, sem repetição por seed (o contexto é determinístico), sem avaliar a qualidade do texto aceito. As tentativas anteriores com outros modelos (Haiku 5.5 e demais "premium": 403, plano sem saldo) estão no registro acima.

