// Linhas do "log de investigação": eventos derivados só das séries simuladas
// (nada é inventado). Cada linha tem tempo (min), texto e tom (cor da evidência).
const docs = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });

export function clock(minutes) {
  return `t+${String(Math.floor(minutes)).padStart(2, '0')}min`;
}

export function investigationLog(reactive, anticipatory) {
  const lines = [];
  for (const [label, run, tone] of [
    ['reativa', reactive, 'reactive'],
    ['antecipativa', anticipatory, 'anticipatory'],
  ]) {
    const ticks = run?.ticks ?? [];
    if (!ticks.length) continue;
    const base = ticks[0].active_replicas;
    const up = ticks.find((t) => t.active_replicas > base);
    if (up) lines.push({ time: up.time_minutes, tone, text: `${label} escala para ${up.active_replicas} réplicas` });
    const violation = ticks.find((t) => t.slo_violated);
    if (violation) lines.push({ time: violation.time_minutes, tone: 'risk', text: `${label} viola o SLO de fila` });
    const peak = ticks.reduce((m, t) => (t.backlog_docs > m.backlog_docs ? t : m), ticks[0]);
    if (peak.backlog_docs > 0)
      lines.push({ time: peak.time_minutes, tone, text: `pico de fila da ${label}: ${docs.format(peak.backlog_docs)} doc` });
  }
  return lines.sort((a, b) => a.time - b.time);
}
