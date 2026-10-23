"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import AnswerView from "./AnswerView";
import { ask } from "@/lib/api";
import type { Answer, Citation, Filters } from "@/lib/types";

type Turn = { q: string; a?: Answer; error?: string };

/** Conversation state for an ask box. `initial` is asked once on mount (the homepage hands questions over). */
export function useAsk(filters: Filters, initial?: string) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const asked = useRef(false); // dev Strict Mode runs effects twice; ask only once

  async function submit(q: string) {
    q = q.trim();
    if (!q || busy) return;
    setBusy(true);
    setTurns((t) => [...t, { q }]);
    const done = (patch: Partial<Turn>) => setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, ...patch } : x)));
    try {
      done({ a: await ask(q, filters) });
    } catch (e) {
      done({ error: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (initial && !asked.current) {
      asked.current = true;
      submit(initial);
    }
  }, [initial]); // eslint-disable-line react-hooks/exhaustive-deps

  return { turns, busy, submit };
}

export function Conversation({ turns, busy, onCite, active, empty }: {
  turns: Turn[]; busy: boolean; onCite: (c: Citation) => void; active?: string | null; empty: React.ReactNode;
}) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth", block: "end" }), [turns, busy]);
  if (turns.length === 0) return <div className="empty-chat"><span className="chat-mark" aria-hidden="true"><svg viewBox="0 0 32 32"><circle cx="14" cy="14" r="8" /><path d="m20 20 7 7M11 14h6M14 11v6" /></svg></span>{empty}</div>;
  return (
    <div className="chat" aria-live="polite">
      {turns.map((t, i) => (
        <Fragment key={i}>
          <div className="q">{t.q}</div>
          {t.a && <AnswerView a={t.a} onCite={onCite} active={active} />}
          {t.error && <div className="a error" role="alert">⚠ {t.error}</div>}
        </Fragment>
      ))}
      {busy && <div className="a thinking" role="status"><span className="sr-only">Searching the space…</span><i /><i /><i /></div>}
      <div ref={end} />
    </div>
  );
}

export function Composer({ onAsk, busy, examples, placeholder, disabled = false }: {
  onAsk: (q: string) => void; busy: boolean; examples: string[]; placeholder: string; disabled?: boolean;
}) {
  const [q, setQ] = useState("");
  const send = () => { if (!disabled && !busy && q.trim()) { onAsk(q.trim()); setQ(""); } };
  return (
    <div className="composer">
      {examples.length > 0 && <div className="chips">
        {examples.map((ex) => <button key={ex} type="button" className="chip" title={ex} onClick={() => onAsk(ex)} disabled={busy || disabled}>{ex}</button>)}
      </div>}
      <form onSubmit={(e) => { e.preventDefault(); send(); }}>
        <textarea rows={2} value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} maxLength={500} aria-label="Question" disabled={disabled}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }} />
        <button className="btn" aria-label="Send question" disabled={disabled || busy || !q.trim()}><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 15V5M5 10l5-5 5 5" /></svg></button>
      </form>
      <span className="composer-hint">{disabled ? "Add documents to your space to enable questions." : "Enter to ask · Shift + Enter for a new line"}</span>
    </div>
  );
}
