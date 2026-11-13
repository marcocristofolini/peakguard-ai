"use client";
import { useEffect, useState } from "react";
import { recommend } from "../lib/recommendation.mjs";
import { niceTicks } from "../lib/axis.mjs";
import { explanationSource, interpretDecision, type Validation } from "../lib/decision.mjs";
import { investigationLog, clock } from "../lib/investigation.mjs";

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
type Tone = "demand" | "reactive" | "anticipatory" | "risk";

// Cores de evidência: cada grandeza tem sempre a mesma cor na página.
const C = {
  demand: "#F5B851",
  reactive: "#5B8CFF",
  anticipatory: "#2DD4A7",
  risk: "#FF5C7A",
};

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
// Cada cenário vira a pergunta que a investigação responde.
const questions: Record<string, [string, string]> = {
  stable: ["Carga estável", ": vale manter réplicas extras?"],
  predictable_peak: ["Pico previsível", ": antecipar compensa o custo?"],
  unexpected_peak: ["Pico inesperado", ": quem segura a fila?"],
  wrong_forecast: ["Previsão incorreta", ": quanto custa antecipar à toa?"],
  fiscal_month_close: ["Fechamento do mês", ": a fila aguenta o volume?"],
  fiscal_das_day20: ["DAS dia 20", ": antecipar evita violar o SLO?"],
  fiscal_ancillary_obligations: ["Obrigações acessórias", ": qual política sai mais barata?"],
  fiscal_irpf_april: ["IRPF de abril", ": o pico cabe no orçamento?"],
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
// A API devolve ids de política em inglês dentro do texto; a tela fala português.
const ptPolicies = (text: string) =>
  text.replace(/\banticipatory\b/g, "antecipativa").replace(/\breactive\b/g, "reativa");
const verdicts: Record<string, string> = {
  approved: "Aprovada pelo validador",
  abstained: "Validador se absteve",
  unavailable: "Validação indisponível",
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

function Evidence({
  tone,
  title,
  unit,
  children,
  id,
}: {
  tone: Tone;
  title: string;
  unit: string;
  children: React.ReactNode;
  id?: string;
}) {
  return (
    <figure className={`evidence ${tone}`} id={id}>
      <figcaption>
        <span className="etitle">
          <i aria-hidden="true" />
          {title}
        </span>
        <span className="unit">{unit}</span>
      </figcaption>
      {children}
    </figure>
  );
}

function Legend({ items }: { items: { name: string; color: string }[] }) {
  return (
    <div className="legend">
      {items.map((s) => (
        <span key={s.name}>
          <i style={{ background: s.color }} />
          {s.name}
        </span>
      ))}
    </div>
  );
}

function Chart({
  title,
  unit,
  tone,
  series,
  lastTime,
}: {
  title: string;
  unit: string;
  tone: Tone;
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
    <Evidence tone={tone} title={title} unit={unit}>
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
              className="grid"
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {series.map((s) => (
            <polyline
              key={s.name}
              fill="none"
              stroke={s.color}
              strokeWidth="2.25"
              strokeLinejoin="round"
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
      <Legend items={series} />
    </Evidence>
  );
}

function ParetoChart({ data }: { data: Pareto }) {
  const xs = data.points.map((p) => p.cost_brl),
    minX = Math.min(...xs),
    spanX = Math.max(Math.max(...xs) - minX, 1e-9),
    yTicks = niceTicks(Math.max(...data.points.map((p) => p.slo_violation_ticks), 0)),
    maxY = yTicks.at(-1) ?? 1;
  return (
    <Evidence
      tone="risk"
      title={`Fronteira de Pareto em ${data.combinations} configurações`}
      unit="custo estimado × ticks fora do SLO, menor é melhor"
    >
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
              className="grid"
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </svg>
        {/* Pontos em HTML: no SVG esticado um círculo vira elipse. */}
        <div className="dots">
          {data.points.map((p, i) => (
            <span
              key={i}
              className={`dot ${p.pareto ? "front" : ""}`}
              style={{
                left: `${((40 + ((p.cost_brl - minX) / spanX) * 700) / 760) * 100}%`,
                top: `${(yPos(p.slo_violation_ticks, maxY) / 190) * 100}%`,
                color: C[p.policy],
              }}
              title={`${labels[p.policy]}, utilização ${p.target_utilization}, ${money(p.cost_brl)}, ${p.slo_violation_ticks} ticks fora do SLO${p.pareto ? ", na fronteira" : ""}`}
            />
          ))}
        </div>
        <Axes
          y={yTicks.map((t) => ({ value: t, label: num(t), max: maxY }))}
          x={[money(minX), money(minX + spanX)]}
        />
      </div>
      <div className="legend">
        <span>
          <i style={{ background: C.reactive }} />
          Reativa
        </span>
        <span>
          <i style={{ background: C.anticipatory }} />
          Antecipativa
        </span>
        <span className="hint">Ponto cheio: na fronteira. Vazado: dominado.</span>
      </div>
    </Evidence>
  );
}

function Mark() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id="pgmark" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#6D3BF5" />
          <stop offset="1" stopColor="#E04BC8" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="url(#pgmark)" />
      <path
        d="M6 22 L12 15 L16 18 L23 9 L26 12"
        fill="none"
        stroke="#fff"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M6 25.5 H26" stroke="#fff" strokeOpacity=".45" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export default function Home() {
  const [scenarios, setScenarios] = useState<string[]>([]),
    [scenario, setScenario] = useState("predictable_peak"),
    [seed, setSeed] = useState(42),
    [budget, setBudget] = useState(10),
    [maxReplicas, setMaxReplicas] = useState(10),
    [slo, setSlo] = useState(2),
    [arrivals, setArrivals] = useState("deterministic"),
    [risk, setRisk] = useState(""),
    [useLlm, setUseLlm] = useState(false),
    [result, setResult] = useState<Comparison | null>(null),
    [ran, setRan] = useState<{ scenario: string; seed: number; arrivals: string } | null>(null),
    [validation, setValidation] = useState<Validation | null>(null),
    [pareto, setPareto] = useState<Pareto | null>(null),
    [loading, setLoading] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    fetch("/api/scenarios")
      .then(async (r) => {
        if (!r.ok)
          throw new Error(
            "Não foi possível carregar os cenários. Verifique se a API está rodando.",
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
        arrivals,
        ...(risk !== "" ? { risk_appetite: Number(risk) } : {}),
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
      setRan({ scenario, seed, arrivals });
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
          body: useLlm ? JSON.stringify({ ...JSON.parse(payload), use_llm: true }) : payload,
        });
        if (v.ok) setValidation(await v.json());
      } catch {
        setValidation(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "A simulação falhou. Tente de novo.");
    } finally {
      setLoading(false);
    }
  }
  const a = result?.results.reactive,
    b = result?.results.anticipatory,
    ranking = a && b ? recommend(a, b) : null,
    rec = a && b ? interpretDecision(validation) : null,
    source = explanationSource(validation),
    log = a && b ? investigationLog(a, b) : [],
    lastTime = a?.ticks.at(-1)?.time_minutes ?? 0;
  return (
    <div className="app">
      <header className="nav">
        <a className="brand" href="#investigar">
          <Mark />
          <span>
            peakguard<b>.ai</b>
          </span>
        </a>
        <nav aria-label="Seções">
          <a href="#investigar">Investigar</a>
          <a href="#evidencias">Evidências</a>
          <a href="#comparacao">Comparação</a>
        </nav>
        <span className="env">
          <i aria-hidden="true" /> Ambiente local, dados sintéticos
        </span>
      </header>

      <section className="hero">
        <h1>Investigue a capacidade antes do pico</h1>
        <p>
          A mesma carga sintética roda nas políticas reativa e antecipativa. O
          validador decide qual é segura; nenhuma infraestrutura é alterada.
        </p>
      </section>

      <section className="case" id="investigar">
        <form className="ask" onSubmit={execute}>
          <h2>Qual cenário investigar?</h2>
          <div className="questions" role="radiogroup" aria-label="Cenário">
            {scenarios.length === 0 && !error && (
              <p className="muted">Carregando cenários…</p>
            )}
            {scenarios.map((s) => {
              const [topic, rest] = questions[s] ?? [names[s] ?? s, ""];
              return (
                <label key={s} className={`q ${s === scenario ? "on" : ""}`}>
                  <input
                    type="radio"
                    name="scenario"
                    value={s}
                    checked={s === scenario}
                    onChange={() => setScenario(s)}
                  />
                  <span>
                    <b>{topic}</b>
                    {rest}
                  </span>
                  {s.startsWith("fiscal_") && <em>fiscal</em>}
                </label>
              );
            })}
          </div>
          <details className="params">
            <summary>
              Parâmetros <span>seed {seed}, até {maxReplicas} réplicas, {money(budget)}, SLO de {num(slo)} min</span>
            </summary>
            <div className="fields">
              <label>
                Seed
                <input type="number" step="1" value={seed} onChange={(e) => setSeed(Number(e.target.value))} required />
              </label>
              <label>
                Máximo de réplicas
                <input type="number" min="1" max="1000" step="1" value={maxReplicas} onChange={(e) => setMaxReplicas(Number(e.target.value))} required />
              </label>
              <label>
                Orçamento (BRL)
                <input type="number" min="0" step="0.01" value={budget} onChange={(e) => setBudget(Number(e.target.value))} required />
              </label>
              <label>
                SLO de fila (min)
                <input type="number" min="0.1" step="0.1" value={slo} onChange={(e) => setSlo(Number(e.target.value))} required />
              </label>
              <label>
                Chegadas
                <select value={arrivals} onChange={(e) => setArrivals(e.target.value)}>
                  <option value="deterministic">Determinísticas</option>
                  <option value="poisson">Poisson</option>
                  <option value="burst">Rajadas</option>
                </select>
              </label>
              <label className="check">
                <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} />
                Explicar com LLM (opcional; o validador decide)
              </label>
              <label>
                Percentil de risco (opcional)
                <input type="number" min="0.01" max="0.99" step="0.01" placeholder="ex.: 0,9" value={risk} onChange={(e) => setRisk(e.target.value)} />
              </label>
            </div>
            {arrivals !== "deterministic" && (
              <p className="muted">
                Chegadas {arrivals === "burst" ? "em rajadas" : "Poisson"} sorteadas pela seed: synthetic e reproduzíveis.
              </p>
            )}
          </details>
          <button className="run" disabled={loading || !scenarios.length}>
            {loading ? "Investigando…" : "Investigar cenário"}
          </button>
        </form>

        <article className="report" aria-live="polite">
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          {loading && (
            <div className="empty" role="status">
              <div className="spinner" />
              Rodando as duas políticas sobre a mesma carga…
            </div>
          )}
          {!result && !loading && !error && (
            <div className="empty">
              <strong>Nenhuma investigação aberta</strong>
              <p>Escolha uma pergunta à esquerda e clique em Investigar cenário.</p>
            </div>
          )}
          {a && b && rec && ran && (
            <>
              <div className="chips">
                <span className="chip scenario">{names[ran.scenario] ?? ran.scenario}</span>
                <span className="chip">synthetic</span>
                <span className="chip">custo estimated</span>
                {ran.arrivals !== "deterministic" && <span className="chip">chegadas {ran.arrivals}</span>}
              </div>
              <pre className="terminal" key={`${ran.scenario}-${ran.seed}-${ran.arrivals}`}>
                <span className="cmd">
                  <span className="prompt">$</span> peakguard compare {ran.scenario} --seed {ran.seed}
                  {ran.arrivals !== "deterministic" ? ` --arrivals ${ran.arrivals}` : ""}
                </span>
                {log.length === 0 && <span className="line">nenhuma violação de SLO nem fila acumulada</span>}
                {log.map((l, i) => (
                  <span key={i} className={`line ${l.tone}`} style={{ animationDelay: `${120 + i * 90}ms` }}>
                    <time>{clock(l.time)}</time>
                    {l.text}
                  </span>
                ))}
              </pre>
              <p className="finding">
                <span className="arrow" aria-hidden="true">→</span>
                <span>
                  <strong>{rec.title}.</strong> {ptPolicies(rec.reason)}
                </span>
              </p>
              <p className="verdict">
                <span className={`vtag ${rec.status}`}>{verdicts[rec.status] ?? rec.status}</span>
                <span>
                  Ranking por SLO e custo:{" "}
                  {ranking?.policy === "tie" ? "empate" : (labels[ranking?.policy || ""] || "indisponível").toLowerCase()}.
                  O ranking não substitui o validador, e nada é executado automaticamente.
                </span>
              </p>
              {source && (
                <p className="verdict">
                  <span className={`vtag ${source.tone}`}>{validation?.mode}</span>
                  <span>{source.text}</span>
                </p>
              )}
              <dl className="facts">
                <div>
                  <dt>Demanda total</dt>
                  <dd>{num(a.summary.demand_docs)} <small>doc</small></dd>
                </div>
                <div>
                  <dt>Maior fila</dt>
                  <dd>{num(Math.max(a.summary.max_backlog_docs, b.summary.max_backlog_docs))} <small>doc</small></dd>
                </div>
                <div>
                  <dt>Menor custo</dt>
                  <dd>{money(Math.min(a.summary.cost_brl, b.summary.cost_brl))}</dd>
                </div>
                <div>
                  <dt>Menor violação de SLO</dt>
                  <dd>{num(Math.min(a.summary.slo_violation_minutes, b.summary.slo_violation_minutes))} <small>min</small></dd>
                </div>
              </dl>
            </>
          )}
        </article>
      </section>

      {a && b && (
        <section className="board" id="evidencias">
          <h2>Evidências</h2>
          <Chart
            tone="demand"
            title="Demanda e capacidade"
            unit="documentos por minuto"
            lastTime={lastTime}
            series={[
              { name: "Demanda sintética", color: C.demand, values: a.ticks.map((t) => t.demand_docs_per_minute) },
              { name: "Capacidade reativa", color: C.reactive, values: a.ticks.map((t) => t.capacity_docs_per_minute) },
              { name: "Capacidade antecipativa", color: C.anticipatory, values: b.ticks.map((t) => t.capacity_docs_per_minute) },
            ]}
          />
          <div className="pair">
            <Chart
              tone="reactive"
              title="Réplicas ativas"
              unit="réplicas"
              lastTime={lastTime}
              series={[
                { name: "Reativa", color: C.reactive, values: a.ticks.map((t) => t.active_replicas) },
                { name: "Antecipativa", color: C.anticipatory, values: b.ticks.map((t) => t.active_replicas) },
              ]}
            />
            <Chart
              tone="risk"
              title="Fila"
              unit="documentos"
              lastTime={lastTime}
              series={[
                { name: "Reativa", color: C.reactive, values: a.ticks.map((t) => t.backlog_docs) },
                { name: "Antecipativa", color: C.anticipatory, values: b.ticks.map((t) => t.backlog_docs) },
              ]}
            />
          </div>
          {pareto && <ParetoChart data={pareto} />}
          <Evidence tone="anticipatory" title="Políticas lado a lado" unit="valores estimated" id="comparacao">
            <div className="tablewrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Política</th>
                    <th scope="col">Custo total</th>
                    <th scope="col">Custo por 1.000 doc</th>
                    <th scope="col">Maior fila</th>
                    <th scope="col">Violação de SLO</th>
                    <th scope="col">Processados</th>
                  </tr>
                </thead>
                <tbody>
                  {(
                    [
                      ["Reativa", a, C.reactive],
                      ["Antecipativa", b, C.anticipatory],
                    ] as [string, Run, string][]
                  ).map(([name, r, color]) => (
                    <tr key={name}>
                      <th scope="row">
                        <i style={{ background: color }} />
                        {name}
                      </th>
                      <td>{money(r.summary.cost_brl)}</td>
                      <td>{money(r.summary.cost_brl_per_1000_docs)}</td>
                      <td>{num(r.summary.max_backlog_docs)} doc</td>
                      <td>{num(r.summary.slo_violation_minutes)} min</td>
                      <td>{num(r.summary.processed_docs)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="footnote">
              SLO é o tempo máximo em fila. Os resultados dependem das premissas
              do simulador e não são medições de produção.
            </p>
          </Evidence>
        </section>
      )}

      <footer className="foot">
        PeakGuard AI. Simulação offline com dados sintéticos e custos estimados.
      </footer>
    </div>
  );
}
