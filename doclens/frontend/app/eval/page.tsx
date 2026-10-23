import Notice from "@/components/Notice";
import { ApiError, getEval, getEvalRuns } from "@/lib/api";
import type { EvalRun } from "@/lib/types";

// Shows only what the eval scripts wrote: results/eval.json (python -m backend.eval) and eval/results/*.json
// (python eval/run_eval.py). Nothing here is typed in by hand.
const pct = (x: number | null | undefined) => (x == null ? "—" : `${(x * 100).toFixed(1)}%`);
const num = (x: number | null | undefined, digits = 2) => (x == null ? "—" : x.toFixed(digits));
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

function RunsTable({ runs }: { runs: EvalRun[] }) {
  return (
    <div className="glass sect">
      <h3>Parser and extractor runs</h3>
      <div className="table-scroll">
        <table className="tbl">
          <thead>
            <tr>
              <th>Run</th><th>Parser</th><th>Extractor</th><th>F1 clean</th><th>F1 scanned</th><th>Verified</th>
              <th title="Of the wrong values, the share the evidence check flagged">Wrong values caught</th>
              <th>Table TEDS</th><th>Pages/s</th><th>Peak VRAM</th><th>$/1k pages</th>
            </tr>
          </thead>
          <tbody>
            {runs.map(({ name, config: c, summary: s }) => {
              const all = s.all ?? {};
              return (
                <tr key={name}>
                  <td title={`${c.date ?? ""} · ${c.hardware?.gpu ?? c.hardware?.cpu ?? ""}`}>{name}</td>
                  <td>{c.parser}{c.parser_version ? ` ${String(c.parser_version).split(",")[0]}` : ""}</td>
                  <td>{c.extractor === "llm" ? c.llm ?? "LLM" : "rules"}</td>
                  <td>{num(s.clean?.field_f1)}</td>
                  <td>{num(s.scanned?.field_f1)}</td>
                  <td>{pct(all.evidence?.verified_rate)}</td>
                  <td>{pct(all.evidence?.hallucination_catch_rate)}</td>
                  <td>{num(all.teds)}</td>
                  <td>{num(all.parse?.pages_per_sec, 2)}</td>
                  <td>{all.peak_vram_mb != null ? `${all.peak_vram_mb} MB` : "—"}</td>
                  <td>{all.cost_per_1k_pages_parse_usd != null ? `$${all.cost_per_1k_pages_parse_usd}` : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="sub" style={{ marginTop: 10 }}>
        “—” means not measured on that run (for example, no GPU). Hover a run name for its date and hardware.
      </p>
    </div>
  );
}

function QaStats({ ev }: { ev: Record<string, any> }) {
  const grades: Record<string, number> = ev.answers?.grades ?? {};
  const graded = Object.values(grades).reduce((s, n) => s + n, 0);
  const speed: Record<string, { seconds: number; pages: number | null; sec_per_page: number | null }> = ev.speed ?? {};
  return (
    <>
      <div className="section-head">
        <h1>Question answering</h1>
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

export default async function EvalPage() {
  const [qa, runs] = await Promise.allSettled([getEval(), getEvalRuns()]);
  const offline = [qa, runs].find((r) => r.status === "rejected" && !(r.reason instanceof ApiError && r.reason.status === 404));
  if (offline && offline.status === "rejected") {
    return (
      <>
        <div className="page-head"><h1>Evaluation</h1></div>
        <Notice title="Backend offline" icon="⚠">{offline.reason instanceof Error ? offline.reason.message : String(offline.reason)}</Notice>
      </>
    );
  }
  const runList = runs.status === "fulfilled" ? runs.value : [];
  const qaStats = qa.status === "fulfilled" ? qa.value : null;

  if (!qaStats && runList.length === 0) {
    return (
      <>
        <div className="page-head"><h1>Evaluation</h1><p>Review parsers, extraction, retrieval and answer quality across your documents.</p></div>
        <section className="glass eval-empty">
          <span className="badge">Awaiting results</span><h2>No evaluation yet</h2>
          <p>Your measured results will appear here once an evaluation is complete.</p>
          <details className="eval-setup"><summary>How to generate results</summary><ol>
            <li>Parser and extractor runs: <code>python eval/run_eval.py --parser pdfium --extractor rules --out eval/results/pdfium-rules.json</code></li>
            <li>Question answering: add questions to <code>labels/qa.jsonl</code>, run <code>python -m backend.eval answers</code>, grade <code>labels/answer_grades.csv</code>, then run <code>python -m backend.eval</code>.</li>
          </ol></details>
        </section>
      </>
    );
  }

  return (
    <>
      {runList.length > 0 && (
        <>
          <div className="section-head">
            <h1>Evaluation</h1>
            <span>from eval/results/*.json · synthetic Japanese invoices, clean and scanned</span>
          </div>
          <RunsTable runs={runList} />
        </>
      )}
      {qaStats && <QaStats ev={qaStats} />}
    </>
  );
}
