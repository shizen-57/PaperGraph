"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type { DocumentSummary, Graph, Relation, RelationType } from "@/lib/types";

const W = 900, H = 560;
const FOLDER_COLOR: Record<string, string> = { papers: "#3987e5", drafts: "#d95926", supervisor: "#199e70" };
const OTHER = "#8b8c8e";
// Edge type is carried by dash pattern + legend, not colour
const DASH: Record<RelationType, string> = { supersedes: "", cites: "7 5", same_topic: "2 5", feedback_on: "10 4 2 4" };
const EDGE_LABEL: Record<RelationType, string> = { supersedes: "supersedes", cites: "cites", same_topic: "same topic", feedback_on: "feedback on" };

type P = { x: number; y: number };

/** Small force layout: repulsion between all nodes, springs on edges, pull to the centre. Deterministic. */
function layout(nodes: DocumentSummary[], edges: Relation[]): Record<string, P> {
  // ponytail: O(n²) per step, fine for the 10–50 documents of one space; d3-force beyond that
  const pos: Record<string, P> = {};
  nodes.forEach((n, i) => {
    const a = (2 * Math.PI * i) / nodes.length;
    pos[n.id] = { x: W / 2 + 220 * Math.cos(a), y: H / 2 + 180 * Math.sin(a) };
  });
  const k = Math.sqrt((W * H) / Math.max(nodes.length, 1)) * 0.55;
  for (let step = 0, t = 40; step < 300; step++, t *= 0.985) {
    const d: Record<string, P> = Object.fromEntries(nodes.map((n) => [n.id, { x: 0, y: 0 }]));
    for (const a of nodes) for (const b of nodes) {
      if (a === b) continue;
      const dx = pos[a.id].x - pos[b.id].x, dy = pos[a.id].y - pos[b.id].y;
      const dist = Math.max(Math.hypot(dx, dy), 1);
      d[a.id].x += (dx / dist) * (k * k) / dist;
      d[a.id].y += (dy / dist) * (k * k) / dist;
    }
    for (const e of edges) {
      const a = pos[e.source_id], b = pos[e.target_id];
      if (!a || !b) continue;
      const dx = a.x - b.x, dy = a.y - b.y, dist = Math.max(Math.hypot(dx, dy), 1), f = (dist * dist) / k;
      d[e.source_id].x -= (dx / dist) * f; d[e.source_id].y -= (dy / dist) * f;
      d[e.target_id].x += (dx / dist) * f; d[e.target_id].y += (dy / dist) * f;
    }
    for (const n of nodes) {
      const p = pos[n.id], v = d[n.id];
      v.x += (W / 2 - p.x) * 0.4; v.y += (H / 2 - p.y) * 0.4; // two lone nodes settle ~k/0.9 apart
      const len = Math.max(Math.hypot(v.x, v.y), 1);
      p.x = Math.min(W - 90, Math.max(90, p.x + (v.x / len) * Math.min(len, t)));
      p.y = Math.min(H - 40, Math.max(40, p.y + (v.y / len) * Math.min(len, t)));
    }
  }
  return pos;
}

const short = (s: string, n = 34) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

export default function GraphView({ graph }: { graph: Graph }) {
  const router = useRouter();
  const pos = useMemo(() => layout(graph.nodes, graph.edges), [graph]);
  const [hover, setHover] = useState<string | null>(null);
  const [edge, setEdge] = useState<Relation | null>(null);
  const title = Object.fromEntries(graph.nodes.map((n) => [n.id, n.title]));
  const folders = [...new Set(graph.nodes.map((n) => n.folder))];
  const near = (id: string) => !hover || id === hover || graph.edges.some((e) =>
    (e.source_id === hover && e.target_id === id) || (e.target_id === hover && e.source_id === id));

  return (
    <div className="graph-wrap">
      <div className="glass graph">
        <div className="pane-head graph-heading"><h2>Document map</h2><span>{graph.nodes.length} documents · {graph.edges.length} relations</span></div>
        <div className="legend" aria-label="Legend">
          {folders.map((f) => <span key={f}><i style={{ background: FOLDER_COLOR[f] ?? OTHER }} />{f}/</span>)}
          {(Object.keys(DASH) as RelationType[]).map((t) => (
            <span key={t}><svg width="28" height="8" aria-hidden="true"><line x1="0" y1="4" x2="28" y2="4" strokeDasharray={DASH[t]} /></svg>{EDGE_LABEL[t]}</span>
          ))}
        </div>
        <div className="graph-canvas" tabIndex={0} aria-label="Scrollable document map"><svg viewBox={`0 0 ${W} ${H}`} role="group" aria-label="Document relations graph">
          <defs>
            <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0 8 4 0 8z" fill="currentColor" />
            </marker>
          </defs>
          {graph.edges.map((e) => {
            const a = pos[e.source_id], b = pos[e.target_id];
            if (!a || !b) return null;
            const dx = b.x - a.x, dy = b.y - a.y, len = Math.max(Math.hypot(dx, dy), 1);
            // Trim each end to the rectangular document tile, keeping arrowheads visible.
            const trim = Math.min(Math.min(88 / (Math.abs(dx) / len || 1e-6), 30 / (Math.abs(dy) / len || 1e-6)) + 5, Math.max(0, len / 2 - 2));
            const x1 = a.x + (dx / len) * trim, y1 = a.y + (dy / len) * trim;
            const x2 = b.x - (dx / len) * trim, y2 = b.y - (dy / len) * trim;
            const on = edge?.id === e.id;
            const dim = hover && e.source_id !== hover && e.target_id !== hover;
            return (
              <g key={e.id} className={`g-edge${on ? " on" : ""}${dim ? " dim" : ""}`} onClick={() => setEdge(e)}
                role="button" tabIndex={0} aria-label={`${EDGE_LABEL[e.type]}: ${title[e.source_id]} to ${title[e.target_id]}`} aria-pressed={on}
                onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); setEdge(e); } }}>
                <line x1={x1} y1={y1} x2={x2} y2={y2} className="hit" />
                <line x1={x1} y1={y1} x2={x2} y2={y2} strokeDasharray={DASH[e.type]}
                  markerEnd={e.type === "same_topic" ? undefined : "url(#arrow)"} />
              </g>
            );
          })}
          {graph.nodes.map((n) => {
            const p = pos[n.id];
            return (
              <g key={n.id} className={`g-node${near(n.id) ? "" : " dim"}`} transform={`translate(${p.x},${p.y})`}
                onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}
                onClick={() => router.push(`/docs/${encodeURIComponent(n.id)}`)}
                role="link" tabIndex={0} aria-label={`${n.title} (${n.folder})`}
                onKeyDown={(ev) => ev.key === "Enter" && router.push(`/docs/${encodeURIComponent(n.id)}`)}>
                <rect className="node-tile" x="-88" y="-30" width="176" height="60" rx="12" />
                <circle cx="-72" cy="-10" r="4" fill={FOLDER_COLOR[n.folder] ?? OTHER} />
                <text className="node-title" x="-61" y="-6">{short(n.title, 23)}</text>
                <text className="node-meta" x="-72" y="15">{n.folder}/ {n.version_label || n.year || ""}</text>
                <title>{`${n.title}\n${n.folder}/ · ${n.claims} claims · ${n.relations} relations`}</title>
              </g>
            );
          })}
        </svg></div>
        <p className="graph-help"><span className="graph-pan-hint">Swipe to explore. </span>Select a document to open it. Select a connection to inspect its evidence.</p>
      </div>

      <aside className="glass sect edge-panel">
        <h2 className="inspector-title">Relation details</h2>
        {!edge ? <p className="ingest-help">Click an edge to see why it exists. Click a document to open it.</p> : (
          <>
            <span className="edge-tag">{EDGE_LABEL[edge.type]}</span>
            <h3>{title[edge.source_id]} → {title[edge.target_id]}</h3>
            <p>{edge.evidence}</p>
            <p className="ingest-help">Confidence {Math.round(edge.confidence * 100)}%</p>
          </>
        )}
      </aside>

      <details className="glass sect graph-table">
        <summary>Table view ({graph.edges.length} relations)</summary>
        <table className="tbl">
          <thead><tr><th>From</th><th>Relation</th><th>To</th><th>Evidence</th></tr></thead>
          <tbody>
            {graph.edges.map((e) => (
              <tr key={e.id}><td>{title[e.source_id]}</td><td>{EDGE_LABEL[e.type]}</td><td>{title[e.target_id]}</td><td>{e.evidence}</td></tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
