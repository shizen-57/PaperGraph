import Notice from "@/components/Notice";
import { ApiError, getEval } from "@/lib/api";

// Shows only what `python -m backend.eval` wrote to results/eval.json. Nothing here is typed in by hand.
const pct = (x: number | null | undefined) => (x == null ? "—" : `${(x * 100).toFixed(1)}%`);
const ms = (x: number | null | undefined) => (x == null ? "—" : `${(x / 1000).toFixed(1)} s`);

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="glass stat">
      <div className="big">{value}</div>
      <div className="label">{label}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

export default async function EvalPage() {
  let ev: Record<string, any>;
  try {
    ev = await getEval();
  } catch (e) {
    const missing = e instanceof ApiError && e.status === 404;
    return (
      <>
        <div className="page-head"><h1>Evaluation</h1><p>Review retrieval, citation quality and answer accuracy across your documents.</p></div>
        {missing ? <section className="glass eval-empty">
          <span className="badge">Awaiting results</span><h2>No evaluation yet</h2>
          <p>Your measured results will appear here once an evaluation is complete.</p>
          <details className="eval-setup"><summary>How to generate results</summary><ol>
            <li>Add questions to <code>labels/qa.jsonl</code>.</li>
            <li>Run <code>python -m backend.eval answers</code> and grade the answers in <code>labels/answer_grades.csv</code>.</li>
            <li>Run <code>python -m backend.eval</code> to calculate the metrics.</li>
          </ol></details>
        </section> : <Notice title="Backend offline" icon="⚠">{e instanceof Error ? e.message : String(e)}</Notice>}
      </>
    );
  }

  const grades: Record<string, number> = ev.answers?.grades ?? {};
  const graded = Object.values(grades).reduce((s, n) => s + n, 0);
  const speed: Record<string, { seconds: number; pages: number | null; sec_per_page: number | null }> = ev.speed ?? {};

  return (
    <>
      <div className="section-head">
        <h1>Evaluation</h1>
        <span>from results/eval.json · {ev.corpus?.documents ?? 0} documents, {ev.corpus?.chunks ?? 0} chunks</span>
      </div>
      <div className="stats">
        <Stat label="Search recall@5" value={pct(ev.search?.recall_at_5)} sub={`gold page in top 5 · ${ev.search?.n ?? 0} questions`} />
        <Stat label="Citation validity" value={pct(ev.citations?.validity)} sub={`cites a gold document/page · ${ev.citations?.n ?? 0} citations`} />
        <Stat label="Quote support" value={pct(ev.citations?.quote_support)} sub="cited quote found in its source" />
        <Stat label="Numeric consistency" value={pct(ev.answers?.numeric_consistency)} sub="answers with every number in a cited source" />
        <Stat label="Required quote retrieved" value={pct(ev.answers?.required_quote)} sub="the gold quote was in the cited passages" />
        <Stat label="Claim quotes verified" value={pct(ev.claims?.quote_verified)} sub={`${ev.claims?.n ?? 0} extracted claims`} />
        <Stat
          label="Answers correct (hand-graded)"
          value={graded ? pct((grades.correct ?? 0) / graded) : "—"}
          sub={graded ? `${grades.correct ?? 0} correct · ${grades.partly ?? 0} partly · ${grades.wrong ?? 0} wrong` : "not graded yet"}
        />
        <Stat label="Answer latency" value={ms(ev.answers?.latency_ms?.mean)} sub={`mean · p95 ${ms(ev.answers?.latency_ms?.p95)}`} />
      </div>

      {Object.keys(speed).length > 0 && (
        <div className="glass sect">
          <h3>Ingestion speed</h3>
          <table className="tbl">
            <thead><tr><th>Stage</th><th>Seconds</th><th>Pages</th><th>s / page</th></tr></thead>
            <tbody>
              {Object.entries(speed).map(([k, s]) => (
                <tr key={k}><td>{k}</td><td>{s.seconds}</td><td>{s.pages ?? "—"}</td><td>{s.sec_per_page ?? "—"}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
