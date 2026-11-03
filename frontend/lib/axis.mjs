// Rótulos de eixo "redondos" para grandezas contáveis (réplicas, documentos, ticks).
// Passo = menor valor em {1, 2, 2,5, 5, 10} × 10^k que gere até ~4 intervalos,
// descartando passos fracionários; o topo do eixo é o primeiro múltiplo >= máximo.
const STEPS = [1, 2, 2.5, 5, 10];

export function niceTicks(max, intervals = 4) {
  if (!Number.isFinite(max) || max <= 0) return [0, 1];
  const raw = max / intervals;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = Math.max(
    1,
    STEPS.map((s) => s * magnitude).find((s) => s >= raw && Number.isInteger(s)) ?? 10 * magnitude,
  );
  const top = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = 0; v <= top; v += step) ticks.push(v);
  return ticks;
}
