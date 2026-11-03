# Política de segurança

## Versões suportadas

Apenas a branch `main` recebe correções de segurança.

## Como relatar uma vulnerabilidade

**Não abra issue pública.** Use o relato privado do GitHub:
[Security → Report a vulnerability](https://github.com/marcocristofolini/peakguard-ai/security/advisories/new).

Inclua, se possível: componente afetado (API, dashboard, simulador, scripts de `local/p6`), passos para reproduzir, impacto esperado e versão/commit.

Você recebe confirmação de recebimento em até 7 dias. Correções confirmadas são publicadas como security advisory, com crédito a quem relatou, se desejar.

## Escopo

Este é um projeto de demonstração com dados sintéticos, sem implantação pública oficial. Os limites de segurança da aplicação (autenticação da API, dashboard sem login, requisitos para expor publicamente) estão em [docs/SECURITY.md](../docs/SECURITY.md).
