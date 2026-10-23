import Link from "next/link";
import { Bricolage_Grotesque } from "next/font/google";
import { ConfidenceBadge } from "@/components/AnswerView";
import IngestPanel from "@/components/IngestPanel";
import Notice from "@/components/Notice";
import { getEval, getSpace } from "@/lib/api";
import styles from "./SpacePanels.module.css";

const pct = (x: number | null | undefined) => (x == null ? "—" : `${(x * 100).toFixed(1)}%`);
const display = Bricolage_Grotesque({ subsets: ["latin"], weight: ["600", "700"], variable: "--font-space-display", display: "swap" });

export default async function SpacePage() {
  let space;
  try {
    space = await getSpace();
  } catch {
    return <Notice title="Your workspace is temporarily unavailable" icon="⚠">Please refresh the page in a moment to reconnect to your documents.</Notice>;
  }
  const ev = await getEval().catch(() => null); // no eval yet is normal
  const c = space.counts;

  return (
    <div className={`space-dashboard ${display.variable} ${styles.dashboard}`}>
      <div className="page-head">
        <span className="space-eyebrow">Your workspace</span>
        <h1>Your research, connected.</h1>
        <p>Explore your documents, find connections, and turn questions into answers.</p>
      </div>

      <div className="space-grid">
        <div className="stats space-metrics">
        {([["documents", "/docs"], ["chunks", null], ["claims", "/docs"], ["relations", "/graph"]] as const).map(([k, href]) => {
          const labels = { documents: "Documents", chunks: "Searchable passages", claims: "Key insights", relations: "Connections" };
          const body = <><span className="metric-symbol" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d={k === "documents" ? "M7 3h7l4 4v14H6V3h1m7 0v5h4M9 12h6m-6 4h6" : k === "chunks" ? "M5 6h14M5 12h10M5 18h14" : k === "claims" ? "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z" : "M8 8l8 8M8 16l8-8"} />{k === "relations" && <><circle cx="6" cy="6" r="3" /><circle cx="18" cy="6" r="3" /><circle cx="6" cy="18" r="3" /><circle cx="18" cy="18" r="3" /></>}</svg></span><div className="big">{c[k]}</div><div className="label">{labels[k]}</div></>;
          const className = `glass stat stat-${k}`;
          return href ? <Link key={k} href={href} className={className}>{body}</Link> : <div key={k} className={className}>{body}</div>;
        })}
      </div>

        <div className="space-ingest"><IngestPanel initial={space.last_job} /></div>

        <section className={`${styles.panel} space-folders`} aria-labelledby="collections-title">
          <header className={styles.header}><h2 id="collections-title"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" /></svg>Collections</h2><Link href="/docs">Browse documents</Link></header>
          {Object.keys(space.folders).length === 0 ? <div className={styles.empty}>
            <strong>No collections yet</strong><p>Sync your folder to bring documents into your library, grouped by collection.</p>
            <a className={styles.textAction} href="#library-sync">Go to folder sync <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h12m-5-5 5 5-5 5" /></svg></a>
          </div> : (
            <ul className={styles.collections}>
              {Object.entries(space.folders).map(([f, n]) => (
                <li key={f}><Link href={`/ask?folder=${encodeURIComponent(f)}`}><span className={styles.collectionName}>{f.replace(/[_-]/g, " ")}</span><span className={styles.count}>{n} {n === 1 ? "document" : "documents"}</span><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m8 5 5 5-5 5" /></svg></Link></li>
              ))}
            </ul>
          )}
        </section>

        <section className={`${styles.panel} space-recent`} aria-labelledby="questions-title">
          <header className={styles.header}><h2 id="questions-title"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h13a2 2 0 0 1 2 2v10ZM7 8h9M7 12h6" /></svg>Recent questions</h2></header>
          {space.recent.length === 0 ? <div className={styles.questionEmpty}>
            <h3>Start a conversation.</h3><p>Explore a topic, compare ideas, or find a detail across your documents.</p>
            <Link href="/ask" className={styles.primaryAction}>Ask a question <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h12m-5-5 5 5-5 5" /></svg></Link>
          </div> : (
            <ul className={styles.questions}>
              {space.recent.map((r) => (
                <li key={r.id}><Link href={`/ask?q=${encodeURIComponent(r.question)}`}>{r.question}</Link><ConfidenceBadge label={r.confidence_label} /></li>
              ))}
            </ul>
          )}
          <footer className={styles.footer}>{space.recent.length === 0 ? "Your recent questions will appear here." : <Link className={styles.textAction} href="/ask">Ask another question <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h12m-5-5 5 5-5 5" /></svg></Link>}</footer>
        </section>

        <section className={`${styles.panel} space-eval`} aria-labelledby="quality-title">
          <header className={styles.header}><h2 id="quality-title"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Zm-4 9 3 3 5-6" /></svg>Answer quality</h2></header>
          {!ev ? <div className={styles.empty}><strong>No assessment yet</strong><p>Review how well answers retrieve sources and support their citations once evaluation results are available.</p></div> : (
            <dl className={styles.quality}>
              <div><dt>Relevant sources found</dt><dd>{pct(ev.search?.recall_at_5)}</dd></div>
              <div><dt>Quote support</dt><dd>{pct(ev.citations?.quote_support)}</dd></div>
              <div><dt>Citation validity</dt><dd>{pct(ev.citations?.validity)}</dd></div>
            </dl>
          )}
          <footer className={styles.footer}><Link className={styles.textAction} href="/eval">{ev ? "View quality report" : "Explore evaluation"}<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h12m-5-5 5 5-5 5" /></svg></Link></footer>
        </section>
      </div>
    </div>
  );
}
