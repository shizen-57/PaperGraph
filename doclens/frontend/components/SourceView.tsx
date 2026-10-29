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
  if (doc.file_type === "image") return <ImageViewer url={browserUrl(`/files/${doc.id}`)} size={doc.page_sizes[0]} target={target} />;
  return <TextViewer elements={elements} target={target} slides={doc.file_type === "pptx"} />;
}

/** A scanned page or photo with the highlight box drawn over it. Boxes are in the image's own pixels. */
function ImageViewer({ url, size, target }: { url: string; size?: [number, number]; target: Target | null }) {
  const b = target?.bbox;
  const [w, h] = size ?? [1, 1];
  return (
    <div className="pdf-page" style={{ position: "relative", maxWidth: 900 }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={url} alt="Uploaded document" style={{ width: "100%", display: "block" }} />
      {b && size && (
        <div key={target!.seq} className="hl" style={{
          left: `${(b.x0 / w) * 100}%`, top: `${(b.y0 / h) * 100}%`,
          width: `${((b.x1 - b.x0) / w) * 100}%`, height: `${((b.y1 - b.y0) / h) * 100}%`,
        }} />
      )}
    </div>
  );
}

function TextViewer({ elements, target, slides = false }: { elements: Element[]; target: Target | null; slides?: boolean }) {
  const hl = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (target) hl.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [target]);

  return (
    <article className="text-doc">
      {elements.map((e, i) => {
        const on = target?.elementId === e.id;
        const isHeading = !!e.heading?.endsWith(e.text) && e.text.length < 120;
        return (
          <div key={on ? `${e.id}-${target!.seq}` : e.id} ref={on ? hl : undefined} className={`tx${on ? " tx-hl" : ""}`}>
            {e.line != null && <span className="ln" aria-hidden="true">{e.line}</span>}
            {slides && (i === 0 || elements[i - 1].page !== e.page) && <span className="ln" aria-hidden="true">Slide {e.page}</span>}
            {e.table ? <TableView table={e.table} /> : isHeading ? <h3>{e.text}</h3> : <p>{e.text}</p>}
          </div>
        );
      })}
    </article>
  );
}
