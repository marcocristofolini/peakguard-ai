# Prompt inicial para Codex (PeakGuard AI)

Implemente o projeto conforme ROADMAP.md e AGENTS.md.

Nesta execução, faça SOMENTE P0 + P1:
- Estrutura mínima em Python 3.12+ e simulador determinístico de demanda/capacidade.
- Compare política reativa vs antecipativa com a mesma carga e seed.
- Validador determinístico (min/max réplicas, restrições de SLO, custo) e custo por réplica-hora.
- Quatro cenários sintéticos incluindo pico, previsão incorreta, carga estável e saturação.
- CLI que exporte JSON e testes pytest para determinismo, fila, throughput, custo e limites.

Não implemente API, UI, LLM, Kubernetes, integração cloud nem CI nesta execução.
Sem venv, cloud paga ou over-engineering. Leia só arquivos pertinentes.
Rode testes e registre o resultado em docs/STATUS.md (<=20 linhas).
Resposta final: entrega, arquivos, testes, bloqueios, próximo passo (máximo 8 linhas).
Não avance para P2.
