# PeakGuard AI — contrato Codex

## Escopo
- `ROADMAP.md` é especificação aprovada; implemente SOMENTE fase pedida.
- Dados e requisitos são sintéticos; nunca alegue acesso à infraestrutura da Contabilizei.
- Python 3.12+, FastAPI e Next.js apenas nas fases previstas; MVP começa offline.
- Sem venv, GitHub Actions, cloud paga, frameworks de agentes, abstrações especulativas ou dependências sem motivo.

## Caveman: economize tokens na conversa
- A skill `caveman` já está disponível no Codex. Use respostas objetivas em português.
- Responda primeiro com resultado. Omita elogios, introduções, recaps e narração de comandos triviais.
- Preserve integralmente caminhos, código, comandos, números, erros, negações e condições.
- NÃO aplique estilo telegráfico a código, testes, comentários, README, docs, logs, mensagens de commit ou textos exibidos ao usuário da aplicação.
- Resumo final: `feito | arquivos | testes | bloqueios | próximo`, no máximo 8 linhas.

## Superpowers: engenharia disciplinada, sem cerimônia extra
- Skills disponíveis no Codex em `~/.agents/skills/superpowers/`. Invoque as relevantes; não finja que foram executadas.
- `using-superpowers`: verifique habilidades aplicáveis antes da tarefa.
- `writing-plans`: para nova fase, faça UM plano curto apenas para a fase, com caminhos, passos testáveis e comandos. Guarde em `docs/superpowers/plans/`. Não replaneje todo o roadmap.
- O design já está definido no ROADMAP. Não reinicie brainstorming nem peça confirmação, salvo se houver decisão realmente bloqueante.
- `executing-plans`: execute o plano na MESMA sessão, sem agentes adicionais por padrão. Evite worktrees e revisores paralelos na fase inicial.
- `test-driven-development`: para comportamento novo ou correção, siga RED → GREEN → REFACTOR. Prove que o teste falhou pelo motivo esperado antes do código.
- `systematic-debugging`: ao falhar, investigue causa com evidências; não aplique remendos às cegas.
- `verification-before-completion`: rode verificações pertinentes e leia saída antes de declarar sucesso ou commitar.
- Faça revisão de requisitos e diff ao finalizar a fase. Use revisão externa somente se justificada por risco ou solicitação.

## Context7: documentação atual sem desperdício de tokens
- MCP `context7` já está registrado no Codex. Use-o quando uma tarefa depender da sintaxe atual, versão, configuração ou comportamento de biblioteca/API/SDK/CLI externa.
- Fluxo: `resolve-library-id` (com nome e objetivo específico) se o ID ainda não for conhecido; depois `query-docs` com o ID correto e UMA dúvida técnica delimitada. Respeite versões fixadas pelo projeto.
- Consulte antes de escrever código dependente dessa API e use somente trechos relevantes. Reutilize o que já foi consultado na sessão; evite repetir buscas.
- Não consulte Context7 para algoritmos próprios, simulador determinístico, Python padrão, revisão de código, refatoração ou debugging de lógica interna.
- Prioridade futura: FastAPI/Pydantic (P2), Next.js (P3), SDK de LLM (P4), KEDA/OpenCost e integração Kubernetes (P6). P0/P1 dispensam consultas, salvo dúvida concreta sobre API externa.
- Se Context7 estiver indisponível, não invente APIs. Consulte documentação oficial por outro meio quando necessário e registre limitação.
- Economize contexto: no máximo uma resolução de biblioteca por ID desconhecido e uma consulta focada por dúvida; apenas consultas adicionais se a evidência inicial for insuficiente. Não copie documentação extensa para o chat nem para `STATUS.md`.
- Não inclua tokens de autenticação, chaves MCP ou conteúdo privado nos prompts, código ou commits.

## Modelos por fase (escolha antes de iniciar o Codex)
- A instrução escrita no prompt NÃO altera o modelo ativo. Inicie nova sessão com `codex -m <slug> -c model_reasoning_effort=<level>` ou use `/model` antes de executar a fase. Confira disponibilidade no seletor.
- P0+P1: `gpt-6.1-sol` / `medium` (simulador e decisões iniciais).
- P2: `gpt-6.1-terra` / `medium` (implementação de API).
- P3: `gpt-6.1-terra` / `medium` (frontend e integração).
- P4: `gpt-6.1-sol` / `high` (limites de agentes e segurança).
- P5: `gpt-6.1-sol` / `medium` (benchmarks verificáveis).
- P6: `gpt-6.1-sol` / `high` (integração Kubernetes e troubleshooting).
- P7: `gpt-6.1-sol` / `medium` (auditoria final e apresentação).
- Ajustes isolados de texto/documentação, fora da implementação principal: `gpt-6-luna` / `low`, em sessão separada se compensar.
- Se um modelo não estiver disponível, use `gpt-6.1-sol` / `medium`. Não faça upgrade automático para `high` nem mude de modelo no meio da fase sem necessidade demonstrada.
- Evite sessões paralelas, raciocínio `max`/`ultra` e múltiplas consultas Context7 sem necessidade. O objetivo é reduzir consumo sem comprometer validação.

## Segurança, precisão e simulação
- Distinga `synthetic`, `predicted`, `estimated` e `observed`; informe unidades.
- IA apenas explica propostas; validação de SLO, custos e permissões é determinística. Sem execução automática.
- Sem segredos no repositório; `.env.example` com nomes, nunca valores reais.
- Não afirme economia real ou melhoria de confiabilidade sem benchmark reproduzível.
- Trate o caso de previsão errada como cenário essencial. Modo offline deve funcionar sem LLM.

## Operação e handoff
- Leia `AGENTS.md`, fase pedida do `ROADMAP.md` e `docs/STATUS.md`; abra mais arquivos somente conforme a tarefa.
- Faça um passo testável por vez. Rode teste relevante primeiro, suíte maior ao concluir fase.
- Não publique, faça push, merge ou deploy sem pedido explícito.
- Atualize `docs/STATUS.md` em até 20 linhas com fase, resultados, testes e próximo passo.
- Nunca despeje arquivos completos ou logs enormes no chat. Use diff resumido e erro decisivo.
