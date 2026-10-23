"use client";

import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import type { Target } from "@/lib/types";

// Worker and cMaps are copied into /public by scripts/copy-pdfjs.mjs on npm install.
pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
const OPTIONS = { cMapUrl: "/cmaps/", cMapPacked: true }; // without cMaps, Japanese text renders blank
const MAX_PAGES = 40; // ponytail: renders every page up to this cap; virtualise for long documents

type Props = { url: string; pageSizes: [number, number][]; target: Target | null };

export default function PdfViewer({ url, pageSizes, target }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const hl = useRef<HTMLDivElement>(null);
  const pages = useRef<(HTMLDivElement | null)[]>([]);
  const [width, setWidth] = useState(640);
  const [numPages, setNumPages] = useState(0);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.min(Math.floor(entry.contentRect.width), 900)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!target || !numPages) return;
    // a highlight box if we have one, otherwise just the page
    (hl.current ?? pages.current[target.page - 1])?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [target, numPages]);

  return (
    <div ref={box}>
      <Document
        file={url}
        options={OPTIONS}
        onLoadSuccess={({ numPages }) => setNumPages(numPages)}
        loading={<p className="viewer-msg">Opening PDF…</p>}
        error={<p className="viewer-msg">Couldn&apos;t load the PDF. Is the file still in the space folder?</p>}
      >
        <div className="viewer-pages">
          {Array.from({ length: Math.min(numPages, MAX_PAGES) }, (_, i) => {
            const n = i + 1;
            const scale = width / (pageSizes[i]?.[0] ?? 595); // backend boxes are in PDF points
            const b = target?.page === n ? target.bbox : null;
            return (
              <div key={n} ref={(el) => { pages.current[i] = el; }} className="pdf-page" style={{ width }}>
                <Page pageNumber={n} width={width} renderTextLayer={false} renderAnnotationLayer={false} />
                {b && (
                  <div
                    key={target!.seq}
                    ref={hl}
                    className="hl"
                    style={{
                      left: b.x0 * scale - 4,
                      top: b.y0 * scale - 4,
                      width: (b.x1 - b.x0) * scale + 8,
                      height: (b.y1 - b.y0) * scale + 8,
                    }}
                  />
                )}
                <span className="label">{n} / {numPages}</span>
              </div>
            );
          })}
        </div>
      </Document>
    </div>
  );
}
