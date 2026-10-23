"use client";

import { groupByFolder } from "@/lib/api";
import type { DocumentSummary } from "@/lib/types";

/** Folder tree with checkboxes. Nothing ticked = search everything. */
export default function DocTree({ docs, selected, onChange }: {
  docs: DocumentSummary[]; selected: Set<string>; onChange: (s: Set<string>) => void;
}) {
  const groups = groupByFolder(docs);
  const toggle = (ids: string[], on: boolean) => {
    const next = new Set(selected);
    ids.forEach((id) => (on ? next.add(id) : next.delete(id)));
    onChange(next);
  };
  return (
    <nav className="tree" aria-label="Documents to search">
      <div className="tree-head">
        <span>{selected.size ? `${selected.size} selected` : "Searching everything"}</span>
        {selected.size > 0 && <button onClick={() => onChange(new Set())}>Clear</button>}
      </div>
      {Object.entries(groups).map(([folder, ds]) => {
        const ids = ds.map((d) => d.id);
        const all = ids.every((id) => selected.has(id));
        return (
          <div key={folder} className="tree-folder">
            <label className="tree-row folder">
              <input type="checkbox" checked={all} onChange={(e) => toggle(ids, e.target.checked)} />
              <span>{folder}/</span><em>{ds.length}</em>
            </label>
            {ds.map((d) => (
              <label key={d.id} className="tree-row" title={d.path}>
                <input type="checkbox" checked={selected.has(d.id)} onChange={(e) => toggle([d.id], e.target.checked)} />
                <span>{d.title}</span>
                {d.version_label && <em>{d.version_label}</em>}
              </label>
            ))}
          </div>
        );
      })}
    </nav>
  );
}
