# PeakGuard AI — regras permanentes para Codex

## Objetivo
Implementar o roadmap incrementalmente, priorizando um demonstrador local, determinístico, barato e testável. Consulte `ROADMAP.md` para escopo e critérios de aceite. Nunca presuma acesso à infraestrutura real de terceiros.

## Escopo e simplicidade
- Execute apenas a fase explicitamente solicitada; não antecipe fases.
- Prefira solução simples em Python 3.12+ / FastAPI e Next.js / TypeScript.
- Sem venv, GitHub Actions, cloud paga, bancos/filas/frameworks novos sem necessidade comprovada.
- Não adicione abstrações, serviços, factories, plugins ou camadas especulativas.
- Reutilize código existente; inspecione somente arquivos pertinentes. Não leia todo o repositório sem motivo.

## Evidências e segurança
- Identifique dados `synthetic`, `estimated`, `observed` e custos com unidade.
- O LLM apenas explica recomendações aprovadas por lógica determinística. Não executa ações.
- Segredos fora do repositório; `.env.example` sem valores reais.
- Falhas na IA não podem impedir simulação offline.
- Não afirmar economia ou confiabilidade real sem medição verificável.

## Validação
- Escreva testes focados no comportamento alterado; rode testes/lint/build pertinentes.
- Registre comandos exatos e falhas, não invente verificações.
- Não faça push, merge, publicação ou deploy sem pedido explícito.

## Economia de tokens
- Respostas finais curtas: `feito; arquivos; testes; bloqueios; próximo passo`.
- Não recopie grandes arquivos, logs ou documentos; cite caminhos e resuma diffs.
- Evite narrar comandos triviais e revisar documentação não relacionada.
- Atualize `docs/STATUS.md` (máximo 20 linhas): fase, entregas, comandos, bloqueios e próximo passo. Use-o como handoff entre sessões.
