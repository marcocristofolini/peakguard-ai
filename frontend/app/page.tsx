"use client";
import { useEffect, useState } from "react";
import { recommend } from "../lib/recommendation.mjs";
import { niceTicks } from "../lib/axis.mjs";
import { interpretDecision, type Validation } from "../lib/decision.mjs";

type Tick = {
  time_minutes: number;
  demand_docs_per_minute: number;
  capacity_docs_per_minute: number;
  backlog_docs: number;
  active_replicas: number;
  slo_violated: boolean;
};
type Summary = {
  cost_brl: number;
  cost_brl_per_1000_docs: number | null;
  max_backlog_docs: number;
  slo_violation_minutes: number;
  processed_docs: number;
  demand_docs: number;
};
type Run = { ticks: Tick[]; summary: Summary };
type Comparison = { results: { reactive: Run; anticipatory: Run } };
type ParetoPoint = {
  policy: "reactive" | "anticipatory";
  cost_brl: number;
  slo_violation_ticks: number;
  pareto: boolean;
  target_utilization: number;
};
type Pareto = { points: ParetoPoint[]; combinations: number };
const names: Record<string, string> = {
  stable: "Carga estável",
  predictable_peak: "Pico previsível",
  unexpected_peak: "Pico inesperado",
  wrong_forecast: "Previsão incorreta",
  fiscal_month_close: "Fiscal: fechamento do mês",
  fiscal_das_day20: "Fiscal: DAS dia 20",
  fiscal_ancillary_obligations: "Fiscal: obrigações acessórias",
  fiscal_irpf_april: "Fiscal: IRPF de abril",
};
const money = (x: number | null) =>
  x === null
    ? "—"
    : new Intl.NumberFormat("pt-BR", {
        style: "currency",
        currency: "BRL",
        maximumFractionDigits: 2,
      }).format(x);
const num = (x: number) =>
  new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(x);
const labels: Record<string, string> = {
  reactive: "Reativa",
  anticipatory: "Antecipativa",
  tie: "Empate",
};

// Área útil do gráfico no viewBox 760×190: x 40–740, y 24 (topo) a 164 (zero).
const yPos = (value: number, max: number) => 164 - (value / max) * 140;

// Rótulos em HTML, fora do SVG: o SVG usa preserveAspectRatio="none" para
// esticar, o que distorceria texto; aqui o texto mantém tamanho legível.
function Axes({
  y,
  x,
}: {
  y: { value: number; label: string; max: number }[];
  x: [string, string];
}) {
  return (
    <div className="axes" aria-hidden="true">
      {y.map((t) => (
        <span
          key={t.value}
          className="tick y"
          style={{ top: `${(yPos(t.value, t.max) / 190) * 100}%` }}
        >
          {t.label}
        </span>
      ))}
      <span className="tick x start">{x[0]}</span>
      <span className="tick x end">{x[1]}</span>
    </div>
  );
}

function Chart({
  title,
  unit,
  series,
  lastTime,
}: {
  title: string;
  unit: string;
  lastTime: number;
  series: { name: string; color: string; values: number[] }[];
}) {
  const length = Math.max(...series.map((s) => s.values.length), 1),
    ticks = niceTicks(Math.max(...series.flatMap((s) => s.values), 0)),
    max = ticks.at(-1) ?? 1;
  const points = (v: number[]) =>
    v
      .map(
        (y, i) =>
          `${40 + (i * 700) / Math.max(length - 1, 1)},${yPos(y, max)}`,
      )
      .join(" ");
  return (
    <section className="panel chart">
      <div className="panelhead">
        <div>
          <span className="eyebrow">SÉRIE TEMPORAL</span>
          <h3>{title}</h3>
        </div>
        <span className="unit">{unit}</span>
      </div>
      <div className="plot">
        <svg
          viewBox="0 0 760 190"
          role="img"
          aria-label={`${title}, ${unit}`}
          preserveAspectRatio="none"
        >
          {ticks.map((t) => (
            <line
              key={t}
              x1="40"
              x2="740"
              y1={yPos(t, max)}
              y2={yPos(t, max)}
              stroke="#263645"
              strokeDasharray="3 5"
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {series.map((s) => (
            <polyline
              key={s.name}
              fill="none"
              stroke={s.color}
              strokeWidth="2.5"
              vectorEffect="non-scaling-stroke"
              points={points(s.values)}
            />
          ))}
        </svg>
        <Axes
          y={ticks.map((t) => ({ value: t, label: num(t), max }))}
          x={["0 min", `${num(lastTime)} min`]}
        />
      </div>
      <div className="legend">
        {series.map((s) => (
          <span key={s.name}>
            <i style={{ background: s.color }} />
            {s.name}
          </span>
        ))}
      </div>
    </section>
  );
}
function ParetoChart({ data }: { data: Pareto }) {
  const xs = data.points.map((p) => p.cost_brl),
    minX = Math.min(...xs),
    spanX = Math.max(Math.max(...xs) - minX, 1e-9),
    yTicks = niceTicks(Math.max(...data.points.map((p) => p.slo_violation_ticks), 0)),
    maxY = yTicks.at(-1) ?? 1,
    color = { reactive: "#6e92ff", anticipatory: "#45d8b4" };
  return (
    <section className="panel chart">
      <div className="panelhead">
        <div>
          <span className="eyebrow">FRONTEIRA DE PARETO · {data.combinations} CONFIGURAÇÕES</span>
          <h3>Custo × passos fora do SLO</h3>
        </div>
        <span className="unit">BRL estimado · ticks (menor é melhor)</span>
      </div>
      <div className="plot">
        <svg
          viewBox="0 0 760 190"
          role="img"
          aria-label="Dispersão de custo estimado por passos fora do SLO; pontos cheios formam a fronteira de Pareto"
          preserveAspectRatio="none"
        >
          {yTicks.map((t) => (
            <line
              key={t}
              x1="40"
              x2="740"
              y1={yPos(t, maxY)}
              y2={yPos(t, maxY)}
              stroke="#263645"
              strokeDasharray="3 5"
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {data.points.map((p, i) => (
            <circle
              key={i}
              cx={40 + ((p.cost_brl - minX) / spanX) * 700}
              cy={yPos(p.slo_violation_ticks, maxY)}
              r={p.pareto ? 5 : 3.5}
              fill={p.pareto ? color[p.policy] : "none"}
              stroke={color[p.policy]}
              strokeWidth="1.5"
              opacity={p.pareto ? 1 : 0.6}
            >
              <title>{`${labels[p.policy]} · utilização ${p.target_utilization} · ${money(p.cost_brl)} · ${p.slo_violation_ticks} ticks fora do SLO${p.pareto ? " · fronteira" : ""}`}</title>
            </circle>
          ))}
        </svg>
        <Axes
          y={yTicks.map((t) => ({ value: t, label: num(t), max: maxY }))}
          x={[money(minX), money(minX + spanX)]}
        />
      </div>
      <div className="legend">
        <span>
          <i style={{ background: color.reactive }} />
          Reativa
        </span>
        <span>
          <i style={{ background: color.anticipatory }} />
          Antecipativa
        </span>
        <span>Ponto cheio = fronteira; vazado = dominado</span>
      </div>
    </section>
  );
}

export default function Home() {
  const [scenarios, setScenarios] = useState<string[]>([]),
    [scenario, setScenario] = useState("predictable_peak"),
    [seed, setSeed] = useState(42),
    [budget, setBudget] = useState(10),
    [maxReplicas, setMaxReplicas] = useState(10),
    [slo, setSlo] = useState(2),
    [result, setResult] = useState<Comparison | null>(null),
    [validation, setValidation] = useState<Validation | null>(null),
    [pareto, setPareto] = useState<Pareto | null>(null),
    [loading, setLoading] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    fetch("/api/scenarios")
      .then(async (r) => {
        if (!r.ok)
          throw new Error(
            "Não foi possível carregar os cenários. Verifique a API.",
          );
        return r.json();
      })
      .then(setScenarios)
      .catch((e) => setError(e.message));
  }, []);
  async function execute(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    setValidation(null);
    setPareto(null);
    try {
      const payload = JSON.stringify({
        scenario,
        seed,
        config: {
          budget_brl: budget,
          max_replicas: maxReplicas,
          slo_queue_minutes: slo,
        },
      });
      const r = await fetch("/api/comparisons", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
      });
      const data = await r.json();
      if (!r.ok)
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Parâmetros inválidos. Revise os valores informados.",
        );
      setResult(data);
      fetch("/api/pareto", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
      })
        .then((p) => (p.ok ? p.json() : null))
        .then(setPareto)
        .catch(() => setPareto(null));
      try {
        const v = await fetch("/api/explanations", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: payload,
        });
        if (v.ok) setValidation(await v.json());
      } catch {
        setValidation(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao executar simulação.");
    } finally {
      setLoading(false);
    }
  }
  const a = result?.results.reactive,
    b = result?.results.anticipatory,
    ranking = a && b ? recommend(a, b) : null,
    rec = a && b ? interpretDecision(validation) : null;
  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <div className="logo">✳</div>
          <div>
            <strong>
              peakguard<span>.ai</span>
            </strong>
            <small>CAPACITY INTELLIGENCE</small>
          </div>
        </div>
        <div className="navtitle">WORKSPACE</div>
        <div className="navactive">
          <span>◫</span> Visão geral <b>01</b>
        </div>
        <div className="sidebottom">
          <div className="status">
            <i /> AMBIENTE LOCAL
          </div>
          <p>
            Simulações offline
            <br />
            Dados sintéticos
          </p>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div>
            <span className="crumb">
              WORKSPACE <b>/</b> CAPACITY PLANNING
            </span>
          </div>
          <div className="topright">
            <span className="dot" /> SISTEMA LOCAL{" "}
            <span className="avatar">PG</span>
          </div>
        </header>
        <div className="content">
          <div className="heading">
            <div>
              <div className="kicker">
                <span /> SIMULATION WORKSPACE
              </div>
              <h1>
                Inteligência de capacidade<span>.</span>
              </h1>
              <p>
                Antecipe riscos de demanda e compare decisões de escalonamento.
              </p>
            </div>
            <div className="tag">
              ◈ &nbsp; DADOS SINTÉTICOS <span> / </span> CUSTOS ESTIMADOS
            </div>
          </div>
          <div className="workspace">
            <section className="panel controls">
              <div className="panelhead">
                <div>
                  <span className="eyebrow">CONFIGURAÇÃO</span>
                  <h2>Nova simulação</h2>
                </div>
                <span className="step">01</span>
              </div>
              <p className="muted">
                Defina o cenário e os limites da comparação.
              </p>
              <form onSubmit={execute}>
                <label>
                  Cenário
                  <select
                    value={scenario}
                    onChange={(e) => setScenario(e.target.value)}
                    disabled={!scenarios.length}
                  >
                    {scenarios.length === 0 ? (
                      <option>Carregando cenários...</option>
                    ) : (
                      scenarios.map((s) => (
                        <option key={s} value={s}>
                          {names[s] || s}
                        </option>
                      ))
                    )}
                  </select>
                </label>
                <div className="fieldrow">
                  <label>
                    Seed
                    <input
                      type="number"
                      step="1"
                      value={seed}
                      onChange={(e) => setSeed(Number(e.target.value))}
                      required
                    />
                  </label>
                  <label>
                    Máx. réplicas
                    <input
                      type="number"
                      min="1"
                      max="1000"
                      step="1"
                      value={maxReplicas}
                      onChange={(e) => setMaxReplicas(Number(e.target.value))}
                      required
                    />
                  </label>
                </div>
                <div className="fieldrow">
                  <label>
                    Orçamento <small>BRL</small>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={budget}
                      onChange={(e) => setBudget(Number(e.target.value))}
                      required
                    />
                  </label>
                  <label>
                    SLO fila <small>min</small>
                    <input
                      type="number"
                      min="0.1"
                      step="0.1"
                      value={slo}
                      onChange={(e) => setSlo(Number(e.target.value))}
                      required
                    />
                  </label>
                </div>
                <button disabled={loading || !scenarios.length}>
                  {loading ? "Simulando..." : "Executar comparação"}{" "}
                  <span>↗</span>
                </button>
              </form>
              <div className="controlnote">
                <span>ⓘ</span> As duas políticas usam a mesma carga e seed.
                Nenhuma infraestrutura é alterada.
              </div>
            </section>
            <div className="maincol">
              <div className="sectiontitle">
                <div>
                  <span className="eyebrow">ANÁLISE DE CENÁRIO</span>
                  <h2>Visão de risco</h2>
                </div>
                <span className="badge">
                  {result ? "SIMULAÇÃO CONCLUÍDA" : "AGUARDANDO EXECUÇÃO"}
                </span>
              </div>
              {error && (
                <div className="error" role="alert">
                  {error}
                </div>
              )}
              {loading && (
                <div className="empty" role="status">
                  <div className="spinner" />
                  Executando comparação...
                </div>
              )}
              {!result && !loading && !error && (
                <div className="empty">
                  <div className="emptyicon">⌁</div>
                  <strong>Pronto para simular</strong>
                  <p>
                    Selecione um cenário e execute a comparação para visualizar
                    os resultados.
                  </p>
                </div>
              )}
              {a && b && rec && (
                <>
                  <div className="metrics">
                    <div className="metric">
                      <span>DEMANDA TOTAL</span>
                      <strong>{num(a.summary.demand_docs)}</strong>
                      <small>documentos sintéticos</small>
                    </div>
                    <div className="metric">
                      <span>MAIOR BACKLOG</span>
                      <strong>
                        {num(
                          Math.max(
                            a.summary.max_backlog_docs,
                            b.summary.max_backlog_docs,
                          ),
                        )}
                      </strong>
                      <small>documentos em fila</small>
                    </div>
                    <div className="metric">
                      <span>MENOR CUSTO</span>
                      <strong>
                        {money(
                          Math.min(a.summary.cost_brl, b.summary.cost_brl),
                        )}
                      </strong>
                      <small>estimativa da execução</small>
                    </div>
                    <div className="metric">
                      <span>VIOLAÇÃO DE SLO</span>
                      <strong>
                        {num(
                          Math.min(
                            a.summary.slo_violation_minutes,
                            b.summary.slo_violation_minutes,
                          ),
                        )}
                        <em> min</em>
                      </strong>
                      <small>melhor resultado</small>
                    </div>
                  </div>
                  <div
                    className={`recommend ${rec.status === "approved" ? "" : "recommend-warning"}`}
                  >
                    <div className="recicon">✳</div>
                    <div>
                      <div className="eyebrow">
                        VALIDAÇÃO DE SEGURANÇA ·{" "}
                        {rec.status === "approved"
                          ? "APROVADA"
                          : rec.status === "abstained"
                            ? "ABSTENÇÃO"
                            : "INCOMPLETA"}
                      </div>
                      <h3>{rec.title}</h3>
                      <p>{rec.reason}</p>
                      <p className="footnote">
                        Ranking por SLO/custo:{" "}
                        {ranking?.policy === "tie"
                          ? "empate"
                          : labels[ranking?.policy || ""] || "indisponível"}
                        . Ranking não substitui validação por políticas.
                      </p>
                    </div>
                    <span className="recchip">SEM EXECUÇÃO AUTOMÁTICA</span>
                  </div>
                  <Chart
                    lastTime={a.ticks.at(-1)?.time_minutes ?? 0}
                    title="Demanda e capacidade"
                    unit="documentos / minuto"
                    series={[
                      {
                        name: "Demanda sintética",
                        color: "#f4c66a",
                        values: a.ticks.map((t) => t.demand_docs_per_minute),
                      },
                      {
                        name: "Capacidade reativa",
                        color: "#6e92ff",
                        values: a.ticks.map((t) => t.capacity_docs_per_minute),
                      },
                      {
                        name: "Capacidade antecipativa",
                        color: "#45d8b4",
                        values: b.ticks.map((t) => t.capacity_docs_per_minute),
                      },
                    ]}
                  />
                  <div className="chartgrid">
                    <Chart
                      lastTime={a.ticks.at(-1)?.time_minutes ?? 0}
                      title="Réplicas ativas"
                      unit="réplicas"
                      series={[
                        {
                          name: "Reativa",
                          color: "#6e92ff",
                          values: a.ticks.map((t) => t.active_replicas),
                        },
                        {
                          name: "Antecipativa",
                          color: "#45d8b4",
                          values: b.ticks.map((t) => t.active_replicas),
                        },
                      ]}
                    />
                    <Chart
                      lastTime={a.ticks.at(-1)?.time_minutes ?? 0}
                      title="Backlog"
                      unit="documentos"
                      series={[
                        {
                          name: "Reativa",
                          color: "#6e92ff",
                          values: a.ticks.map((t) => t.backlog_docs),
                        },
                        {
                          name: "Antecipativa",
                          color: "#45d8b4",
                          values: b.ticks.map((t) => t.backlog_docs),
                        },
                      ]}
                    />
                  </div>
                  {pareto && <ParetoChart data={pareto} />}
                  <section className="panel tablepanel">
                    <div className="panelhead">
                      <div>
                        <span className="eyebrow">ANÁLISE COMPARATIVA</span>
                        <h3>Políticas lado a lado</h3>
                      </div>
                      <span className="unit">VALORES ESTIMADOS</span>
                    </div>
                    <div className="tablewrap">
                      <table>
                        <thead>
                          <tr>
                            <th>POLÍTICA</th>
                            <th>CUSTO TOTAL</th>
                            <th>CUSTO / 1.000 DOC.</th>
                            <th>BACKLOG MÁX.</th>
                            <th>VIOLAÇÃO SLO</th>
                            <th>PROCESSADOS</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(
                            [
                              ["Reativa", a],
                              ["Antecipativa", b],
                            ] as [string, Run][]
                          ).map(([name, r]) => (
                            <tr key={name}>
                              <td>
                                <i
                                  className={
                                    name === "Reativa" ? "blue" : "green"
                                  }
                                />
                                {name}
                              </td>
                              <td>{money(r.summary.cost_brl)}</td>
                              <td>{money(r.summary.cost_brl_per_1000_docs)}</td>
                              <td>{num(r.summary.max_backlog_docs)}</td>
                              <td>
                                {num(r.summary.slo_violation_minutes)} min
                              </td>
                              <td>{num(r.summary.processed_docs)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p className="footnote">
                      SLO: tempo máximo em fila. Resultados dependem das
                      premissas do simulador; não são medições de produção.
                    </p>
                  </section>
                </>
              )}
            </div>
          </div>
          <footer>
            PEAKGUARD AI <span> / </span> CAPACITY PLANNING <span>·</span>{" "}
            SIMULAÇÃO OFFLINE
          </footer>
        </div>
      </main>
    </div>
  );
}
