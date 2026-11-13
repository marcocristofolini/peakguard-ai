"""Adaptador opcional OpenAI (ou compatível via PEAKGUARD_LLM_BASE_URL): somente saída estruturada, sem ferramentas."""

import json
import os

from .explanations import Proposal

OPENAI_URL = 'https://api.openai.com/v1'


def generate(context: dict, usage: dict | None = None) -> dict:
    """`usage` (opcional) recebe a contagem de tokens da chamada; nunca a chave."""
    if os.environ.get('PEAKGUARD_LLM_ENABLED') != 'true':
        raise RuntimeError('LLM desabilitado')
    key, model = os.environ.get('OPENAI_API_KEY'), os.environ.get('PEAKGUARD_LLM_MODEL')
    if not key or not model:
        raise RuntimeError('Configuração ausente')
    from openai import OpenAI
    base_url = os.environ.get('PEAKGUARD_LLM_BASE_URL', OPENAI_URL)
    system = ('Selecione uma política existente sem violação de SLO e dentro dos limites. '
              'Cite apenas IDs e valores exatos das evidências fornecidas. '
              'O campo rationale, se usado, só pode conter números presentes nas evidências e nenhuma URL. '
              'Dados são sintéticos/estimados; não há observações de produção. '
              'Você não autoriza nem executa ações. Não há ferramentas disponíveis.')
    openai_native = base_url == OPENAI_URL
    if not openai_native:  # shortcut: provedor compatível só com json_object (ex. DeepSeek), schema no prompt; usar json_schema se passar a suportar
        system += ' Responda apenas com JSON válido neste JSON Schema: ' + json.dumps(Proposal.model_json_schema())
    messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': json.dumps(context, allow_nan=False)}]
    with OpenAI(api_key=key, base_url=base_url, timeout=10 if openai_native else 180, max_retries=0) as client:
        if openai_native:
            response = client.chat.completions.parse(model=model, store=False, max_completion_tokens=1000,
                                                     messages=messages, response_format=Proposal)
        else:
            response = client.chat.completions.create(model=model, max_tokens=4000, messages=messages,
                                                      response_format={'type': 'json_object'})
        if usage is not None and response.usage is not None:
            usage.update(prompt_tokens=response.usage.prompt_tokens, completion_tokens=response.usage.completion_tokens)
        message = response.choices[0].message
        parsed = message.parsed if openai_native else Proposal.model_validate_json(message.content or '')
        if parsed is None:
            raise ValueError('Resposta ausente ou recusada')
        return parsed.model_dump()
