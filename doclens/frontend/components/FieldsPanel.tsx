"use client";

import { useMemo, useState } from "react";
import { ApiError, extractDocument } from "@/lib/api";
import type { BBox, DocType, DocumentDetail, ExtractedField, Extraction, Target } from "@/lib/types";

const TYPES: { id: DocType; label: string }[] = [
  { id: "invoice", label: "Invoice" }, { id: "spec_sheet", label: "Spec sheet" }, { id: "financial_report", label: "Financial report" },
];
const LABEL: Record<string, string> = {
  invoice_number: "Invoice number", issue_date: "Issue date", due_date: "Due date", issuer: "Issuer", recipient: "Recipient",
  subtotal: "Subtotal", tax: "Tax", total: "Total", product_name: "Product", model_number: "Model number",
  manufacturer: "Manufacturer", rated_voltage: "Rated voltage", rated_current: "Rated current", power: "Power", weight: "Weight",
  dimensions: "Dimensions", operating_temperature: "Operating temperature", company_name: "Company", fiscal_period_end: "Period end",
  unit: "Unit", revenue: "Revenue", operating_income: "Operating income", ordinary_income: "Ordinary income",
  net_income: "Net income", total_assets: "Total assets",
};
const CELL: Record<string, string> = { name: "Item", quantity: "Qty", unit_price: "Unit price", amount: "Amount", tax_rate: "Tax rate" };

// The yen sign is only right for Japanese documents; English and Bangla amounts show the number, and "as printed" carries the currency.
const show = (f: ExtractedField, lang: string) => {
  if (f.value == null) return f.raw ?? "—";
  if (f.kind === "amount" && typeof f.value === "number") return `${lang === "ja" ? "¥" : ""}${f.value.toLocaleString("en-US")}`;
  if (f.kind === "percent" && typeof f.value === "number") return `${Math.round(f.value * 1000) / 10}%`;
  return String(f.value);
};

function Status({ f }: { f: ExtractedField }) {
  if (f.status === "missing") return <span className="badge" title="The document doesn't state this">not in document</span>;
  if (f.status === "verified") return <span className="badge ok" title="The quote is in the document and contains the value">✓ verified</span>;
  const why = f.quote_match < 0.9 ? "the quote is not in the document" : !f.value_in_quote ? "the value is not in its quote or source" : "the value could not be read";
  return <span className="badge bad" title={why}>⚠ unverified · {why}</span>;
}

export default function FieldsPanel({ doc, initial, target, onShow }: {
  doc: DocumentDetail; initial: Extraction | null; target: Target | null;
  onShow: (page: number, bbox: BBox | null, elementId: string | null) => void;
}) {
  const [ex, setEx] = useState<Extraction | null>(initial);
  const [type, setType] = useState<DocType>(initial?.doc_type ?? "invoice");
  const [extractor, setExtractor] = useState<"llm" | "rules">("llm");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setEx(await extractDocument(doc.id, type, extractor));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Extraction failed.");
    } finally {
      setBusy(false);
    }
  };

  const { header, rows } = useMemo(() => {
    const header: ExtractedField[] = [];
    const rows = new Map<number, ExtractedField[]>();
    for (const f of ex?.fields ?? []) {
      const m = f.name.match(/^line_items\[(\d+)\]\./);
      if (m) rows.set(Number(m[1]), [...(rows.get(Number(m[1])) ?? []), f]);
      else header.push(f);
    }
    return { header, rows: [...rows.entries()].sort((a, b) => a[0] - b[0]) };
  }, [ex]);

  const failed = ex?.checks.filter((c) => c.status === "fail") ?? [];
  const flagged = new Set(failed.flatMap((c) => c.fields));
  const counts = { verified: 0, unverified: 0, missing: 0 };
  ex?.fields.forEach((f) => counts[f.status]++);

  return (
    <div>
      <div className="extract-bar">
        <select value={type} onChange={(e) => setType(e.target.value as DocType)} aria-label="Document type">
          {TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
        </select>
        <select value={extractor} onChange={(e) => setExtractor(e.target.value as "llm" | "rules")} aria-label="Extractor">
          <option value="llm">LLM</option>
          <option value="rules">Rules (no LLM, invoices only)</option>
        </select>
        <button className="btn" onClick={run} disabled={busy}>{busy ? "Extracting…" : ex ? "Run again" : "Extract fields"}</button>
      </div>
      {error && <p className="empty-chat" role="alert">⚠ {error}</p>}
      {!ex && !error && <p className="empty-chat">Pick a document type and extract: every value comes with the quote and page it was read from.</p>}

      {ex && (
        <>
          <div className="extract-summary">
            <span className="badge ok">✓ {counts.verified} verified</span>
            {counts.unverified > 0 && <span className="badge bad">⚠ {counts.unverified} unverified</span>}
            {counts.missing > 0 && <span className="badge">{counts.missing} not in document</span>}
            <span className="latency">{ex.model || "—"} · {ex.seconds.toFixed(1)} s</span>
          </div>

          {failed.length > 0 && (
            <ul className="checks" aria-label="Consistency warnings">
              {failed.map((c) => <li key={c.name}><span className="badge warn">⚠ {c.name.replace(/_/g, " ")}</span> {c.message}</li>)}
            </ul>
          )}
          {ex.checks.length > 0 && failed.length === 0 && ex.checks.some((c) => c.status === "pass") && (
            <p className="checks-ok"><span className="badge ok">✓ arithmetic checks passed</span></p>
          )}

          {header.map((f) => <FieldCard key={f.name} f={f} lang={doc.lang} label={LABEL[f.name] ?? f.name} target={target} onShow={onShow} warn={flagged.has(f.name)} />)}

          {rows.length > 0 && <h3 className="subhead">Line items · {rows.length}</h3>}
          {rows.map(([i, cells]) => (
            <RowCard key={i} n={i + 1} cells={cells} lang={doc.lang} target={target} onShow={onShow} flagged={flagged} />
          ))}
        </>
      )}
    </div>
  );
}

function FieldCard({ f, lang, label, target, onShow, warn }: {
  f: ExtractedField; lang: string; label: string; target: Target | null; warn: boolean;
  onShow: (page: number, bbox: BBox | null, elementId: string | null) => void;
}) {
  const clickable = f.page != null;
  return (
    <button className={`field status-${f.status}`} disabled={!clickable} aria-pressed={!!f.element_id && target?.elementId === f.element_id}
      onClick={() => f.page != null && onShow(f.page, f.bbox, f.element_id)} title={clickable ? "Show in the source" : undefined}>
      <span className="row">
        <span className="name">{label}</span>
        <Status f={f} />
        {warn && <span className="badge warn" title="A consistency check involving this value failed">⚠ check failed</span>}
        {f.page != null && <span className="page">p.{f.page}</span>}
      </span>
      <span className="value">{show(f, lang)}{f.tax && <small> ({f.tax === "included" ? "tax incl." : "tax excl."})</small>}</span>
      {f.raw && f.raw !== show(f, lang) && <span className="raw">as printed: {f.raw}</span>}
      {f.quote && <span className="quote">“{f.quote}”</span>}
    </button>
  );
}

function RowCard({ n, cells, lang, target, onShow, flagged }: {
  n: number; cells: ExtractedField[]; lang: string; target: Target | null; flagged: Set<string>;
  onShow: (page: number, bbox: BBox | null, elementId: string | null) => void;
}) {
  const first = cells.find((c) => c.page != null);
  const bad = cells.some((c) => c.status === "unverified");
  return (
    <button className={`field row-card ${bad ? "status-unverified" : ""}`} disabled={!first}
      aria-pressed={!!first?.element_id && target?.elementId === first.element_id}
      onClick={() => first && onShow(first.page!, first.bbox, first.element_id)} title="Show this row in the source">
      <span className="row"><span className="name">Row {n}</span>{first?.page != null && <span className="page">p.{first.page}</span>}</span>
      <span className="cells">
        {cells.filter((c) => c.status !== "missing").map((c) => {
          const col = c.name.split(".")[1];
          return (
            <span key={c.name} className={`cell ${c.status} ${flagged.has(c.name) ? "flag" : ""}`}
              title={c.status === "unverified" ? "not verified against the document" : flagged.has(c.name) ? "an arithmetic check failed" : undefined}>
              <small>{CELL[col] ?? col}</small>{show(c, lang)}
            </span>
          );
        })}
      </span>
      {first?.quote && <span className="quote">“{first.quote}”</span>}
    </button>
  );
}
