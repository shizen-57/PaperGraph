"use client";

import TableView from "./TableView";
import { browserUrl } from "@/lib/api";
import type { Answer, Citation, ConfidenceLabel } from "@/lib/types";

const TONE: Record<ConfidenceLabel, string> = { High: "ok", Medium: "warn", Low: "low", Unverified: "bad", Insufficient: "" };

export function ConfidenceBadge({ label, score }: { label: ConfidenceLabel; score?: number }) {
  return (
    <span className={`badge ${TONE[label]}`} title="Combines retrieval score, quote match, citation validity, numbers and coverage">
      {label === "Insufficient" ? "Insufficient evidence" : `${label} confidence`}
      {score != null && label !== "Insufficient" && ` · ${Math.round(score * 100)}`}
    </span>
  );
}

export function VerifyBadge({ v, match }: { v: "verified" | "unverified"; match: number }) {
  return v === "verified"
    ? <span className="badge ok">✓ quote {match === 1 ? "found" : `${Math.round(match * 100)}% match`}</span>
    : <span className="badge bad" title="The quote the model gave is not in this source">⚠ quote not found{match > 0 ? ` (${Math.round(match * 100)}%)` : ""}</span>;
}

type Props = { a: Answer; onCite: (c: Citation) => void; active?: string | null };

export default function AnswerView({ a, onCite, active }: Props) {
  const byN = new Map(a.citations.map((c) => [c.n, c]));
  return (
    <div className="a">
      <div className="a-head">
        <ConfidenceBadge label={a.confidence_label} score={a.confidence} />
        {a.approximate && <span className="badge warn">≈ read from a chart</span>}
        {a.unverified_numbers.length > 0 && (
          <span className="badge warn">⚠ {a.unverified_numbers.length} number{a.unverified_numbers.length > 1 ? "s" : ""} not in the cited sources</span>
        )}
        <span className="latency">{(a.latency_ms / 1000).toFixed(1)} s</span>
      </div>
      <p>
        {a.answer.split(/(\[\d+\])/).map((part, i) => {
          const c = byN.get(Number(part.match(/^\[(\d+)\]$/)?.[1]));
          return c ? (
            <button key={i} className={`cite${c.verification === "unverified" ? " cite-bad" : ""}`} onClick={() => onCite(c)}
              aria-label={`Source ${c.n}: ${c.document_title}, page ${c.page}`}>{c.n}</button>
          ) : (
            <NumberFlags key={i} text={part} numbers={a.unverified_numbers} />
          );
        })}
      </p>
      {a.relationship_path.length > 0 && (
        <div className="path"><span>Followed</span>{a.relationship_path.map((p) => <code key={p}>{p}</code>)}</div>
      )}
      {a.citations.length > 0 && (
        <div className="sources">
          {a.citations.map((c) => (
            <button key={c.n} className={`source${active === c.chunk_id ? " on" : ""}`} onClick={() => onCite(c)}>
              <span className="head">
                <span className="cite" aria-hidden="true">{c.n}</span>
                <b>{c.document_title}</b> · p.{c.page}
                <VerifyBadge v={c.verification} match={c.quote_match} />
              </span>
              {c.quote && <span className="snippet">“{c.quote}”</span>}
              {c.crop_url && <img src={browserUrl(c.crop_url)} alt={`${c.type} on page ${c.page}`} loading="lazy" />}
              {c.table && <TableView table={c.table} />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Wrap numbers the backend couldn't find in the sources. It strips commas, so match "1,500" against "1500". */
function NumberFlags({ text, numbers }: { text: string; numbers: string[] }) {
  if (numbers.length === 0) return <>{text}</>;
  const pattern = numbers.map((n) => n.split("").map((ch) => ch.replace(/[.]/, "\\.")).join(",?")).join("|");
  const re = new RegExp(`(?<![\\d.,])(${pattern})(?![\\d])`, "g");
  const out: React.ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(re)) {
    out.push(text.slice(last, m.index));
    out.push(<span key={m.index} className="num-warn" title="Not found in the cited sources">{m[0]}</span>);
    last = m.index! + m[0].length;
  }
  out.push(text.slice(last));
  return <>{out}</>;
}
