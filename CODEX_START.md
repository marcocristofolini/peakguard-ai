# Codex — iniciar PeakGuard AI (P0 + P1)

**Modelo:** `gpt-6.1-sol` | **Reasoning:** `medium`
**Iniciar no WSL:** `codex -m gpt-6.1-sol -c model_reasoning_effort=medium`
**Importante:** texto do prompt não troca o modelo; selecione antes de executá-lo.

Use as skills `caveman` e Superpowers relevantes (`writing-plans`, `executing-plans`, `test-driven-development`, `verification-before-completion`). Siga `AGENTS.md` e o escopo P0/P1 em `ROADMAP.md`. Leia `docs/STATUS.md`.

Objetivo APENAS nesta execução:
1. Plano incremental curto da fase em `docs/superpowers/plans/`. O roadmap já define produto e arquitetura; não reabra brainstorming sem bloqueio real.
2. Motor Python 3.12+ determinístico: mesma demanda/seed para políticas reativa e antecipativa, filas, throughput, atraso de réplicas, custos por réplica-hora e políticas min/max/SLO.
3. Quatro cenários sintéticos: carga estável, pico previsível, pico inesperado e previsão falsa.
4. CLI para comparar políticas e exportar JSON.
5. Testes com ciclos RED → GREEN → REFACTOR: determinismo, unidades/custo, backlog, throughput, limites e previsão incorreta.

Context7: já disponível via MCP. Em P0/P1, não consulte por padrão; use somente se encontrar dúvida concreta de versão ou API externa. Resolva o ID da biblioteca uma vez e faça consulta específica com `query-docs`, sem copiar documentação extensa.

Use execução INLINE, sem subagentes/worktrees, sem venv ou dependências desnecessárias. Não crie API, UI, LLM, Kubernetes, integrações cloud ou CI. Não avance para P2.

Confirme verificação com comandos e resultados reais. Atualize `docs/STATUS.md` (máximo 20 linhas). Resposta Caveman: `feito | arquivos | testes | bloqueios | próximo`, até 8 linhas. Não faça push.
