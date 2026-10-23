"use client";

import Link from "next/link";
import { useState } from "react";
import { VerifyBadge } from "./AnswerView";
import DocTree from "./DocTree";
import SourceView from "./SourceView";
import { Composer, Conversation, useAsk } from "./useAsk";
import { getDocument } from "@/lib/api";
import type { Citation, DocumentDetail, DocumentSummary, Target } from "@/lib/types";
import styles from "./AskWorkspace.module.css";

export const EXAMPLES = [
  "What are the key findings?",
  "How do the approaches compare?",
  "What changed between versions?",
];

type Evidence = { c: Citation; doc: DocumentDetail | null; target: Target; error?: string };

export default function AskWorkspace({ docs, initialQuestion, initialFolder }: {
  docs: DocumentSummary[]; initialQuestion?: string; initialFolder?: string;
}) {
  const [selected, setSelected] = useState(() => new Set(docs.filter((d) => d.folder === initialFolder).map((d) => d.id)));
  const { turns, busy, submit } = useAsk(selected.size ? { doc_ids: [...selected] } : {}, docs.length ? initialQuestion : undefined);
  const [ev, setEv] = useState<Evidence | null>(null);

  async function show(c: Citation) {
    const target = { page: c.page, bbox: c.bbox, elementId: c.element_id, seq: (ev?.target.seq ?? 0) + 1 };
    if (ev?.doc?.id === c.document_id) return setEv({ ...ev, c, target });
    setEv({ c, doc: null, target });
    try {
      const doc = await getDocument(c.document_id);
      setEv((cur) => (cur?.c === c ? { ...cur, doc } : cur));
    } catch (e) {
      setEv((cur) => (cur?.c === c ? { ...cur, error: e instanceof Error ? e.message : String(e) } : cur));
    }
  }

  return (
    <div className={`ws ${styles.workspace}`}>
      <aside className="ws-tree" aria-label="Sources to search">
        <div className="pane-head"><h2>Sources</h2><span className={styles.count}>{docs.length}</span></div>
        {docs.length ? <DocTree docs={docs} selected={selected} onChange={setSelected} /> : (
          <div className={styles.sourcesEmpty}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8M8 17h5" /></svg>
            <h3>Your sources live here</h3>
            <p>Add documents to your space to start asking questions.</p>
            <Link href="/space">Add documents <span aria-hidden="true">→</span></Link>
          </div>
        )}
      </aside>

      <section className="panel ws-main" aria-label="Conversation">
        <div className="pane-head"><h2>Conversation</h2><span>{selected.size ? `${selected.size} selected` : "All sources"}</span></div>
        <div className="panel-body">
          <Conversation turns={turns} busy={busy} onCite={show} active={ev?.c.chunk_id}
            empty={<><b>Ask your documents</b><p>Explore ideas, compare findings, and find answers grounded in your sources.</p><span className={styles.trustNote}>Page references. Exact quotes. Checked sources.</span></>} />
        </div>
        <Composer onAsk={submit} busy={busy} disabled={!docs.length} examples={docs.length ? EXAMPLES.slice(0, 2) : []}
          placeholder={docs.length ? "Ask a question about your documents…" : "Add documents to start asking questions"} />
      </section>

      <section className="ws-evidence" aria-label="Evidence">
        <div className="pane-head"><h2>Evidence</h2><span>Source preview</span></div>
        {!ev ? (
          <div className="evidence-empty"><svg viewBox="0 0 32 32" aria-hidden="true"><rect x="7" y="4" width="18" height="24" rx="3" /><path d="M12 11h8M12 16h8M12 21h4" /></svg><h3>Follow the evidence</h3><p>Open a citation in any answer to see the exact quote and its source.</p></div>
        ) : (
          <>
            <div className="ev-card">
              <div className="ev-title">
                <span className="cite" aria-hidden="true">{ev.c.n}</span>
                <b>{ev.c.document_title}</b>
                <span className="badge">p.{ev.c.page}</span>
                <VerifyBadge v={ev.c.verification} match={ev.c.quote_match} />
              </div>
              {ev.c.quote && <blockquote>“{ev.c.quote}”</blockquote>}
              <Link className="ev-open" href={`/docs/${encodeURIComponent(ev.c.document_id)}?el=${ev.c.element_id ?? ""}`}>
                Open in document →
              </Link>
            </div>
            <div className="ev-source">
              {ev.error ? <p className="viewer-msg">{ev.error}</p>
                : ev.doc ? <SourceView doc={ev.doc} elements={ev.doc.elements} target={ev.target} />
                  : <p className="viewer-msg">Opening…</p>}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
