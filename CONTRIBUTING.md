# Como contribuir

Obrigado pelo interesse no PeakGuard AI. Este é um demonstrador de Reliability Engineering + FinOps com dados **sintéticos**; contribuições devem preservar essa natureza.

## Antes de começar

- Para bugs ou ideias, abra uma issue usando os modelos disponíveis.
- Mudanças grandes: descreva a proposta numa issue antes de abrir o PR.
- Vulnerabilidades: não abra issue pública; siga a [política de segurança](.github/SECURITY.md).

## Ambiente

Pré-requisitos: Python 3.12+, Node.js 22+ e npm. Não é necessário Docker, cloud nem chave de LLM.

```bash
# Backend
python3 -m pip install --target /tmp/peakguard-test-deps '.[dev]'
PYTHONPATH=/tmp/peakguard-test-deps python3 -m pytest -q

# Frontend
cd frontend
npm ci --ignore-scripts
npm test
npm run build
```

Se alterar o simulador, regenere os benchmarks e inclua o resultado no PR (o CI compara):

```bash
python3 -m peakguard.benchmarks --output benchmarks/results
```

## Regras do projeto

- Todo número exibido indica sua natureza: `synthetic`, `predicted`, `estimated` ou `observed`, com unidade.
- Nenhum dado, credencial ou integração real de terceiros. Segredos nunca entram no repositório; use `.env.example` só com nomes.
- A IA explica recomendações, mas nunca altera a decisão do validador determinístico.
- Comportamento novo ou correção vem com teste (RED → GREEN → REFACTOR).
- Sem dependências novas sem justificativa no PR.

## Pull requests

1. Crie uma branch a partir da `main`.
2. Use commits no formato [Conventional Commits](https://www.conventionalcommits.org/pt-br/) (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
3. Preencha o modelo de PR e garanta que `ci-python` e `ci-frontend` estejam verdes.
4. PRs em rascunho não disparam o CI; marque como pronto quando quiser a validação.

Ao contribuir, você concorda que sua contribuição será licenciada sob a [licença MIT](LICENSE) e segue o [Código de Conduta](CODE_OF_CONDUCT.md).
