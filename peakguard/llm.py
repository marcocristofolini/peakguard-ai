"""Adaptador opcional OpenAI: somente saída estruturada, sem ferramentas."""

import json
import os

from .explanations import Proposal


def generate(context: dict, usage: dict | None = None) -> dict:
    """`usage` (opcional) recebe a contagem de tokens da chamada; nunca a chave."""
    if os.environ.get('PEAKGUARD_LLM_ENABLED') != 'true':
        raise RuntimeError('LLM desabilitado')
    key, model = os.environ.get('OPENAI_API_KEY'), os.environ.get('PEAKGUARD_LLM_MODEL')
    if not key or not model:
        raise RuntimeError('Configuração ausente')
    from openai import OpenAI
    with OpenAI(api_key=key, base_url='https://api.openai.com/v1', timeout=10, max_retries=0) as client:
        response = client.chat.completions.parse(
            model=model, store=False, max_completion_tokens=1000,
            messages=[{'role': 'system', 'content':
                'Selecione uma política existente sem violação de SLO e dentro dos limites. '
                'Cite apenas IDs e valores exatos das evidências fornecidas. '
                'O campo rationale, se usado, só pode conter números presentes nas evidências e nenhuma URL. '
                'Dados são sintéticos/estimados; não há observações de produção. '
                'Você não autoriza nem executa ações. Não há ferramentas disponíveis.'},
                {'role': 'user', 'content': json.dumps(context, allow_nan=False)}],
            response_format=Proposal,
        )
        if usage is not None and response.usage is not None:
            usage.update(prompt_tokens=response.usage.prompt_tokens, completion_tokens=response.usage.completion_tokens)
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ValueError('Resposta ausente ou recusada')
        return parsed.model_dump()
