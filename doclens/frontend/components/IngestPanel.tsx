"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ChangeEvent, type CSSProperties } from "react";
import { getJob, startIngest, uploadDocuments } from "@/lib/api";
import type { Job } from "@/lib/types";
import styles from "./IngestPanel.module.css";

const STAGES = [
  { id: "parse", label: "Read files" },
  { id: "vlm", label: "Read visuals" },
  { id: "chunk", label: "Split passages" },
  { id: "embed", label: "Index content" },
  { id: "relations", label: "Link sources" },
  { id: "claims", label: "Extract claims" },
];

/** Starts an ingest and polls its job until it finishes, then refreshes the dashboard counts. */
export default function IngestPanel({ initial }: { initial: Job | null }) {
  const router = useRouter();
  const fileInput = useRef<HTMLInputElement>(null);
  const [job, setJob] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const running = job?.status === "queued" || job?.status === "running";
  const active = starting || uploading || running;

  useEffect(() => {
    if (!running || !job) return;
    const t = setInterval(async () => {
      try {
        const j = await getJob(job.id);
        setJob(j);
        setError(null);
        if (j.status === "done" || j.status === "error") router.refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    }, 1000);
    return () => clearInterval(t);
  }, [running, job?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = async () => {
    if (active) return;
    setError(null);
    setStarting(true);
    try {
      setJob(await startIngest());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  };

  const addDocuments = async (event: ChangeEvent<HTMLInputElement>) => {
    const input = event.currentTarget;
    const files = Array.from(input.files ?? []);
    if (!files.length) return;
    let added = false;
    setError(null);
    setUploading(true);
    try {
      await uploadDocuments(files);
      added = true;
      setStarting(true);
      setJob(await startIngest());
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(added ? `Documents were added, but indexing could not start. Sync the folder to retry. ${message}` : message);
    } finally {
      setStarting(false);
      setUploading(false);
      input.value = "";
    }
  };

  const at = starting ? -1 : STAGES.findIndex((s) => s.id === job?.stage);
  const status = starting || uploading ? "queued" : job?.status;
  const failed = !!error || status === "error";
  const stages = STAGES.filter((s) => s.id !== "vlm" || job?.stage === "vlm");
  const progress = Math.round(Math.min(1, Math.max(0, job?.progress ?? 0)) * 100);
  const title = failed ? "Sync needs your attention" : uploading ? "Adding documents" : active ? "Updating your library" : status === "done" ? "Folder sync complete" : "Ready to update";
  const message = error || (status === "error" ? job?.message : uploading ? "Saving your files and preparing them for search." : active ? "You can keep using your workspace while documents are processed." : status === "done" ? "Run again whenever you add or change documents." : "Add files here or sync a folder to prepare documents for search.");
  return (
    <section id="library-sync" className={styles.panel} aria-label="Document ingestion" tabIndex={-1}>
      <div className={styles.header}>
        <div>
          <h3><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" /></svg>Update your library</h3>
          <p>Add up to 10 PDF, Markdown, or plain text files (50 MB max), or sync a folder. Unchanged files are skipped.</p>
        </div>
        <div className={styles.actions}>
          <input ref={fileInput} className={styles.fileInput} type="file" accept=".pdf,.md,.markdown,.txt" multiple onChange={addDocuments} />
          <button className={styles.action} onClick={() => fileInput.current?.click()} disabled={active} aria-busy={uploading}>
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 4v12M4 10h12" /></svg>
            {uploading ? "Adding…" : "Add documents"}
          </button>
          <button className={styles.action} onClick={start} disabled={active} aria-busy={starting || running}>
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M16 7a6.5 6.5 0 0 0-11-2L3 7m0-4v4h4M4 13a6.5 6.5 0 0 0 11 2l2-2m0 4v-4h-4" /></svg>
            {starting || running ? "Syncing…" : failed ? "Try again" : "Sync folder"}
          </button>
        </div>
      </div>
      <ol className={styles.steps} aria-label="Processing steps" style={{ "--stage-count": stages.length } as CSSProperties}>
        {stages.map((s) => {
          const i = STAGES.indexOf(s);
          const state = status === "done" ? "done" : status === "queued" ? "pending" : i < at ? "done" : i === at ? (status === "error" ? "error" : "current") : "pending";
          return <li key={s.id} data-state={state} aria-current={state === "current" ? "step" : undefined}>
            <span className={styles.node} aria-hidden="true">{state === "done" ? <svg viewBox="0 0 20 20"><path d="m5 10 3 3 7-7" /></svg> : state === "error" ? <svg viewBox="0 0 20 20"><path d="m6 6 8 8m0-8-8 8" /></svg> : <span />}</span>
            <span>{s.label}<span className="sr-only">: {state}</span></span>
          </li>;
        })}
      </ol>
      {status === "running" && at >= 0 && <div className={styles.progress}>
        <div><span>{STAGES[at].label}</span><span>{progress}%</span></div>
        <div className={styles.track} role="progressbar" aria-label={`${STAGES[at].label} progress`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}><span style={{ transform: `scaleX(${progress / 100})` }} /></div>
      </div>}
      <div className={styles.summary} data-tone={failed ? "error" : status === "done" ? "done" : "neutral"} role={failed ? "alert" : "status"}>
        <span className={styles.statusDot} aria-hidden="true" />
        <div><strong>{title}</strong><p>{message}</p></div>
      </div>
      {status === "done" && job?.message && <details className={styles.details}>
        <summary>View processing details</summary>
        <p>{job.message.split("; ").join("\n")}</p>
      </details>}
    </section>
  );
}
