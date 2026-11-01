# Continuação Codex — um comando por fase

## Regra em toda sessão
`Use Caveman na comunicação, preservando termos e código. Aplique Superpowers: writing-plans só para a fase ainda não planejada; executing-plans inline; TDD RED→GREEN→REFACTOR; systematic-debugging quando falhar; verification-before-completion antes de afirmar sucesso. Leia AGENTS.md, ROADMAP.md e docs/STATUS.md. Sem subagentes/worktrees por padrão, sem refazer contexto ou avançar fases. Teste, atualize STATUS.md (até 20 linhas) e resuma até 8 linhas. Não faça push.`

### Context7 por fase
O MCP `context7` está disponível. Para código dependente de APIs externas, confirme versão e sintaxe atual antes de implementar: `resolve-library-id` quando o ID for desconhecido; `query-docs` com pergunta específica. Reutilize documentação obtida, não consulte tarefas de lógica interna ou puro Python e não despeje trechos extensos na resposta.

### P2 — API
**Modelo:** `gpt-6.1-terra` | **Reasoning:** `medium`
**Iniciar:** `codex -m gpt-6.1-terra -c model_reasoning_effort=medium`
Confirme o modelo ativo antes de enviar o prompt. O texto não altera o modelo.
Implemente SOMENTE P2. Consulte Context7 para FastAPI/Pydantic quando houver dúvida de API ou versão. Use motor existente para FastAPI; endpoints de cenários, execução e comparação, validações e testes HTTP. Evite duplicar lógica ou adicionar banco.

### P3 — Dashboard
**Modelo:** `gpt-6.1-terra` | **Reasoning:** `medium`
**Iniciar:** `codex -m gpt-6.1-terra -c model_reasoning_effort=medium`
Implemente SOMENTE P3. Consulte Context7 para APIs do Next.js na versão usada. Next.js com gráficos dos resultados da API, indicadores synthetic/estimated, comparação A/B, loading e erro. Rode build e testes pertinentes.

### P4 — IA explicativa
**Modelo:** `gpt-6.1-sol` | **Reasoning:** `high`
**Iniciar:** `codex -m gpt-6.1-sol -c model_reasoning_effort=high`
Implemente SOMENTE P4. Consulte Context7 para sintaxe do SDK de LLM escolhido, se necessário. LLM opcional e read-only; saída estruturada, validação determinística de propostas, fallback offline e testes de respostas inseguras. Sem execução autônoma.

### P5 — Benchmark
**Modelo:** `gpt-6.1-sol` | **Reasoning:** `medium`
**Iniciar:** `codex -m gpt-6.1-sol -c model_reasoning_effort=medium`
Implemente SOMENTE P5. Mesmas cargas e seeds nas duas políticas; meça custo, fila, throughput e SLO. Inclua previsão errada e limitações. Gere relatório reproduzível.

### P6 — Kubernetes opcional
**Modelo:** `gpt-6.1-sol` | **Reasoning:** `high`
**Iniciar:** `codex -m gpt-6.1-sol -c model_reasoning_effort=high`
Implemente SOMENTE P6 se P0–P5 estiverem validados. Consulte Context7 para APIs/configurações de KEDA/OpenCost e componentes Kubernetes utilizados. Kind, workload, métricas Prometheus e KEDA/OpenCost apenas quando agregarem evidência. Sem cloud paga.

### P7 — Apresentação
**Modelo:** `gpt-6.1-sol` | **Reasoning:** `medium`
**Iniciar:** `codex -m gpt-6.1-sol -c model_reasoning_effort=medium`
Para uma correção isolada de texto no README, opcionalmente use `gpt-6-luna` / `low` em outra sessão; preserve a revisão técnica final no Sol.
Implemente SOMENTE P7. README, screenshots reais, roteiro de demo até cinco minutos e auditoria de simplicidade, segurança e reprodutibilidade. Não invente resultados.
