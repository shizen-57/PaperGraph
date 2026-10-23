"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef } from "react";
import TableView from "./TableView";
import { browserUrl } from "@/lib/api";
import type { Document, Element, Target } from "@/lib/types";

// pdf.js needs the browser
const PdfViewer = dynamic(() => import("./PdfViewer"), {
  ssr: false,
  loading: () => <p className="viewer-msg">Loading viewer…</p>,
});

/** A document's source: the PDF with a highlight box, or md/txt paragraphs with the cited one highlighted. */
export default function SourceView({ doc, elements, target }: { doc: Document; elements: Element[]; target: Target | null }) {
  if (doc.file_type === "pdf") return <PdfViewer url={browserUrl(`/files/${doc.id}`)} pageSizes={doc.page_sizes} target={target} />;
  return <TextViewer elements={elements} target={target} />;
}

function TextViewer({ elements, target }: { elements: Element[]; target: Target | null }) {
  const hl = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (target) hl.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [target]);

  return (
    <article className="text-doc">
      {elements.map((e) => {
        const on = target?.elementId === e.id;
        const isHeading = !!e.heading?.endsWith(e.text) && e.text.length < 120;
        return (
          <div key={on ? `${e.id}-${target!.seq}` : e.id} ref={on ? hl : undefined} className={`tx${on ? " tx-hl" : ""}`}>
            {e.line != null && <span className="ln" aria-hidden="true">{e.line}</span>}
            {e.table ? <TableView table={e.table} /> : isHeading ? <h3>{e.text}</h3> : <p>{e.text}</p>}
          </div>
        );
      })}
    </article>
  );
}
