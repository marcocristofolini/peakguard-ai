const names = { reactive: "Reativa", anticipatory: "Antecipativa" };

export function interpretDecision(validation) {
  if (!validation || validation.execution_allowed !== false) {
    return {
      status: "unavailable",
      policy: null,
      title: "Validação indisponível",
      reason:
        "A comparação não equivale à aprovação de uma política. Verifique a API de explicações.",
    };
  }

  if (validation.proposal === null) {
    return {
      status: "abstained",
      policy: null,
      title: "Nenhuma política aprovada",
      reason:
        validation.explanation ||
        "As alternativas não atenderam aos limites de segurança.",
    };
  }

  const policy = validation.proposal?.policy;
  if (!Object.hasOwn(names, policy)) {
    return {
      status: "unavailable",
      policy: null,
      title: "Validação indisponível",
      reason: "A API retornou uma seleção desconhecida.",
    };
  }

  return {
    status: "approved",
    policy,
    title: `Política ${names[policy]}`,
    reason:
      validation.explanation ||
      "Alternativa validada pelas regras determinísticas.",
  };
}

// Origem da explicação: a LLM só explica; o checker de fidelidade e o validador decidem.
export function explanationSource(validation) {
  if (!validation) return null;
  if (validation.mode === "llm")
    return { tone: "approved", text: "Explicação da LLM aceita pelo checker de fidelidade." };
  if (validation.mode === "fallback") {
    const reasons = validation.audit?.[0]?.reasons?.join(", ");
    return {
      tone: "abstained",
      text: `LLM rejeitada${reasons ? ` (${reasons})` : ""}; explicação determinística usada.`,
    };
  }
  return { tone: "approved", text: "Explicação determinística (offline), sem LLM." };
}
