"use client";

import Link from "next/link";
import { useState } from "react";
import { VerifyBadge } from "./AnswerView";
import FieldsPanel from "./FieldsPanel";
import SourceView from "./SourceView";
import { Composer, Conversation, useAsk } from "./useAsk";
import type { BBox, Citation, Claim, DocumentDetail, Extraction, Target } from "@/lib/types";

const TYPE_LABEL: Record<string, string> = {
  contribution: "Contribution", limitation: "Limitation", method: "Method", dataset: "Dataset", result: "Result", future_work: "Future work",
};
const REL_LABEL: Record<string, [string, string]> = { // [as source, as target]
  supersedes: ["supersedes", "superseded by"], cites: ["cites", "cited by"],
  same_topic: ["same topic as", "same topic as"], feedback_on: ["feedback on", "has feedback in"],
};

type Tab = "fields" | "claims" | "ask" | "relations";
const TABS: Tab[] = ["fields", "claims", "ask", "relations"];

export default function DocView({ doc, titles, extraction, initialElement, initialQuestion }: {
  doc: DocumentDetail; titles: Record<string, string>; extraction: Extraction | null; initialElement?: string; initialQuestion?: string;
}) {
  const start = doc.elements.find((e) => e.id === initialElement);
  const [tab, setTab] = useState<Tab>(initialQuestion ? "ask" : extraction || doc.claim_list.length === 0 ? "fields" : "claims");
  const [target, setTarget] = useState<Target | null>(start ? { page: start.page, bbox: start.bbox, elementId: start.id, seq: 1 } : null);
  const show = (page: number, bbox: BBox | null, elementId: string | null) =>
    setTarget((t) => ({ page, bbox, elementId, seq: (t?.seq ?? 0) + 1 }));
  const { turns, busy, submit } = useAsk({ doc_ids: [doc.id] }, initialQuestion);

  return (
    <>
      <header className="glass doc-head">
        <Link href="/docs" className="back">← Documents</Link>
        <h1>{doc.title}</h1>
        <div className="right">
          <span className="badge">{doc.folder}/</span>
          {doc.version_label && <span className="badge">{doc.version_label}</span>}
          {doc.year && <span className="badge">{doc.year}</span>}
          <span className="badge">{doc.lang === "ja" ? "日本語" : doc.lang === "bn" ? "বাংলা" : "English"}</span>
          {(doc.file_type === "pdf" || doc.file_type === "pptx") && <span className="badge">{doc.pages} {doc.file_type === "pptx" ? "slides" : "pages"}</span>}
        </div>
      </header>

      <div className="doc-layout">
        <section className="glass source-pane" aria-label="Source">
          <div className="pane-head"><h2>Source document</h2><span>{doc.file_type.toUpperCase()}{doc.file_type === "pdf" ? ` · ${doc.pages} pages` : doc.file_type === "pptx" ? ` · ${doc.pages} slides` : doc.file_type === "image" ? "" : " · Original text"}</span></div>
          <div className="viewer"><SourceView doc={doc} elements={doc.elements} target={target} /></div>
        </section>

        <section className="glass panel">
          <div className="tabs" role="tablist" aria-label="Document inspector">
            {TABS.map((t) => (
              <button key={t} id={`doc-tab-${t}`} className="tab" role="tab" aria-controls={`doc-panel-${t}`}
                aria-selected={tab === t} tabIndex={tab === t ? 0 : -1} onClick={() => setTab(t)}
                onKeyDown={(e) => {
                  if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(e.key)) return;
                  e.preventDefault();
                  const next = e.key === "Home" ? TABS[0] : e.key === "End" ? TABS[TABS.length - 1]
                    : TABS[(TABS.indexOf(t) + (e.key === "ArrowRight" ? 1 : 2)) % TABS.length];
                  setTab(next);
                  document.getElementById(`doc-tab-${next}`)?.focus();
                }}>
                {t === "fields" ? `Fields${extraction ? ` · ${extraction.fields.filter((f) => f.status !== "missing").length}` : ""}` : t === "claims" ? `Claims · ${doc.claims}` : t === "ask" ? "Ask" : `Relations · ${doc.relations}`}
              </button>
            ))}
          </div>

          <div className="panel-body" role="tabpanel" id="doc-panel-fields" aria-labelledby="doc-tab-fields" hidden={tab !== "fields"}>
            <FieldsPanel doc={doc} initial={extraction} target={target} onShow={show} />
          </div>

          <div className="panel-body" role="tabpanel" id="doc-panel-claims" aria-labelledby="doc-tab-claims" hidden={tab !== "claims"}>
            <ClaimsPanel claims={doc.claim_list} target={target} onShow={(c) => c.page && show(c.page, c.bbox, c.element_id)}
              eligible={doc.folder === "papers" || doc.folder === "drafts"} />
          </div>

          {/* stays mounted so the chat survives tab switches */}
          <div role="tabpanel" id="doc-panel-ask" aria-labelledby="doc-tab-ask" hidden={tab !== "ask"} style={{ display: tab === "ask" ? "contents" : undefined }}>
            <div className="panel-body">
              <Conversation turns={turns} busy={busy} active={null}
                onCite={(c: Citation) => show(c.page, c.bbox, c.element_id)}
                empty={<><b>Ask this document</b>Answers come only from this document and cite their page.</>} />
            </div>
            <Composer onAsk={submit} busy={busy} placeholder="Ask about this document…"
              examples={["What is the main contribution?", "What limitations are stated?"]} />
          </div>

          <div className="panel-body" role="tabpanel" id="doc-panel-relations" aria-labelledby="doc-tab-relations" hidden={tab !== "relations"}>
            {doc.relation_list.length === 0 ? <p className="empty-chat">No relations found for this document.</p> : (
              <ul className="rels">
                {doc.relation_list.map((r) => {
                  const out = r.source_id === doc.id;
                  const other = out ? r.target_id : r.source_id;
                  return (
                    <li key={r.id} className="rel">
                      <span className={`edge-tag e-${r.type}`}>{REL_LABEL[r.type][out ? 0 : 1]}</span>
                      <Link href={`/docs/${encodeURIComponent(other)}`}>{titles[other] ?? other}</Link>
                      <p>{r.evidence}</p>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </section>
      </div>
    </>
  );
}

function ClaimsPanel({ claims, target, onShow, eligible }: {
  claims: Claim[]; target: Target | null; onShow: (c: Claim) => void; eligible: boolean;
}) {
  if (claims.length === 0) {
    return <p className="empty-chat">{eligible ? "No claims extracted yet: the claims stage needs an LLM (LLM_MODEL)." : "Claims are extracted for papers and drafts only."}</p>;
  }
  return (
    <div>
      {claims.map((c) => (
        <button key={c.id} className="field" disabled={!c.page} aria-pressed={!!c.element_id && target?.elementId === c.element_id}
          onClick={() => onShow(c)} title={c.page ? "Show in the source" : "Quote not found in the document"}>
          <span className="row">
            <span className="name">{TYPE_LABEL[c.claim_type]}</span>
            <VerifyBadge v={c.verification} match={c.quote_match} />
            {c.page && <span className="page">p.{c.page}</span>}
          </span>
          <span className="value">{c.claim}</span>
          <span className="quote">“{c.quote}”</span>
        </button>
      ))}
    </div>
  );
}
