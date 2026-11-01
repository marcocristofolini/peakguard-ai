# Acesso à API e limites de publicação

A API foi concebida para execução local. Sua autenticação tem dois modos:
- `PEAKGUARD_AUTH_MODE=local` (padrão): aceita clientes com IP loopback. Um endereço remoto recebe HTTP 403. Não confie nesse modo atrás de um proxy público na mesma máquina, pois a conexão pode parecer loopback.
- `PEAKGUARD_AUTH_MODE=token`: exige `Authorization: Bearer <segredo>` em **todas** as rotas, incluindo `/docs` e `/openapi.json`. Token ausente/incorreto recebe 401; variável ausente ou menor que 32 caracteres, 503 (fail closed). Comparação usa `hmac.compare_digest`.

## Exemplo do servidor em modo token

Gere o segredo em sua máquina. Não comite nem cole em logs, URLs ou no frontend.

```bash
export PEAKGUARD_AUTH_MODE=token
export PEAKGUARD_API_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
PYTHONPATH=/tmp/peakguard-p7-clean python3 -m uvicorn peakguard.api:app --host 127.0.0.1 --port 8000
```

Em outro terminal com **acesso ao mesmo segredo**, consulte:

```bash
curl -H "Authorization: Bearer $PEAKGUARD_API_TOKEN" http://127.0.0.1:8000/scenarios
```

Para uma implantação externa, use **TLS terminado em um proxy confiável**, mantenha o FastAPI inacessível diretamente e configure controle de taxa, logs sem credenciais, rotação de tokens, alertas e autenticação dos usuários. O projeto não entrega um serviço multiusuário pronto para produção.

## Dashboard Next.js

O proxy Next pode enviar `PEAKGUARD_BACKEND_TOKEN` ao FastAPI sem colocar a credencial no JavaScript do navegador. **Isso não autentica quem acessa o dashboard**: os endpoints Next continuam públicos para qualquer pessoa que alcance o servidor Next. Portanto, mantenha o dashboard em localhost ou proteja o site inteiro com autenticação no proxy/IdP antes de qualquer exposição pública. Não encaminhe o cabeçalho Authorization recebido do navegador: o proxy usa apenas o segredo de ambiente do servidor.

## Verificações

```bash
PYTHONPATH=/tmp/peakguard-p7-clean python3 -m pytest tests/test_auth.py -q
```

Casos: modo local, credencial ausente/inválida, autenticação válida, configuração fraca/ausente e modo desconhecido. Os testes funcionais não substituem testes de intrusão, análise de vulnerabilidades, TLS e revisão externa.
