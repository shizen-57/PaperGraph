"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { compare } from "@/lib/api";
import type { CompareResult, DocumentSummary, Side } from "@/lib/types";

const CHANGE: Record<string, string> = { unchanged: "Unchanged", modified: "Modified", added: "Added", removed: "Removed" };

export default function CompareView({ docs, initialA, initialB }: { docs: DocumentSummary[]; initialA: string; initialB: string }) {
  const [a, setA] = useState(initialA);
  const [b, setB] = useState(initialB);
  const [res, setRes] = useState<CompareResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hideSame, setHideSame] = useState(true);

  useEffect(() => {
    if (!a || !b || a === b) return;
    let live = true;
    setRes(null);
    setError(null);
    compare(a, b).then((r) => live && setRes(r), (e) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => { live = false; };
  }, [a, b]);

  const rows = res?.rows.filter((r) => !hideSame || r.change !== "unchanged") ?? [];
  const pick = (value: string, set: (v: string) => void, label: string) => (
    <label className="pick">
      <span>{label}</span>
      <select value={value} onChange={(e) => set(e.target.value)}>
        {docs.map((d) => <option key={d.id} value={d.id}>{d.folder}/ {d.title}{d.version_label ? ` (${d.version_label})` : ""}</option>)}
      </select>
    </label>
  );

  return (
    <>
      <div className="glass compare-bar">
        {pick(a, setA, "A")}
        <span className="arrow" aria-hidden="true">→</span>
        {pick(b, setB, "B")}
        <label className="hide-same"><input type="checkbox" checked={hideSame} onChange={(e) => setHideSame(e.target.checked)} /> Hide unchanged</label>
      </div>

      {a === b ? <p className="viewer-msg">Pick two different documents.</p>
        : error ? <p className="viewer-msg">{error}</p>
          : !res ? <div className="a thinking" role="status"><span className="sr-only">Comparing documents…</span><i /><i /><i /></div>
            : (
              <>
                <div className="compare-sum">
                  {(["modified", "added", "removed", "unchanged"] as const).map((k) => (
                    <span key={k} className={`chg chg-${k}`}>{res.rows.filter((r) => r.change === k).length} {CHANGE[k].toLowerCase()}</span>
                  ))}
                </div>
                {rows.length === 0 ? <p className="viewer-msg">No differences.</p> : (
                  <div className="glass sect">
                    <table className="tbl diff">
                      <thead><tr><th>Change</th><th>{res.a.title} {res.a.version_label}</th><th>{res.b.title} {res.b.version_label}</th></tr></thead>
                      <tbody>
                        {rows.map((r, i) => (
                          <tr key={i}>
                            <td>
                              <span className={`chg chg-${r.change}`}>{CHANGE[r.change]}</span>
                              {r.summary && <p className="chg-sum">{r.summary}</p>}
                              {r.change === "modified" && !r.summary && <p className="chg-sum muted">No summary (LLM offline)</p>}
                            </td>
                            <td><SideCell s={r.a} /></td>
                            <td><SideCell s={r.b} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
    </>
  );
}

function SideCell({ s }: { s: Side | null }) {
  if (!s) return <span className="muted">—</span>;
  return (
    <div className="side">
      <Link className="side-where" href={`/docs/${encodeURIComponent(s.doc_id)}?el=${s.element_id ?? ""}`}>
        {s.section_path || "(no section)"} · p.{s.page} →
      </Link>
      <p>{s.text.length > 600 ? s.text.slice(0, 600) + "…" : s.text}</p>
      {s.quote && (
        <blockquote className={s.quote_match >= 0.9 ? "" : "bad"} title={s.quote_match >= 0.9 ? "Quote found in this version" : "Quote not found in this version"}>
          {s.quote_match >= 0.9 ? "✓" : "⚠"} “{s.quote}”
        </blockquote>
      )}
    </div>
  );
}
