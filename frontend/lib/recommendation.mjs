export function recommend(reactive, anticipatory) {
  const a = reactive.summary, b = anticipatory.summary;
  if (a.slo_violation_minutes !== b.slo_violation_minutes) return { policy: a.slo_violation_minutes < b.slo_violation_minutes ? 'reactive' : 'anticipatory', reason: 'Menos minutos com violação de SLO; o custo pode ser maior.' };
  if (a.cost_brl !== b.cost_brl) return { policy: a.cost_brl < b.cost_brl ? 'reactive' : 'anticipatory', reason: 'Mesmo tempo em violação de SLO e menor custo estimado; confira o backlog da alternativa.' };
  return { policy: 'tie', reason: 'Mesmo tempo em violação de SLO e mesmo custo estimado; confira o backlog de cada política.' };
}
