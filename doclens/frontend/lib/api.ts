import type {
  Answer, CompareResult, DocumentDetail, DocumentSummary, Filters, Graph, Job, SpaceSummary,
} from "./types";

// Server components call FastAPI directly; the browser goes through the /api rewrite in next.config.ts.
const SERVER_API = process.env.API_URL ?? "http://localhost:8000";
const base = () => (typeof window === "undefined" ? SERVER_API : "/api");

/** The knowledge space this frontend shows. */
export const SPACE = process.env.NEXT_PUBLIC_SPACE ?? "thesis";

/** Backend paths like /files/x, as the browser must load them. */
export const browserUrl = (path: string) => `/api${path}`;

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(base() + path, { cache: "no-store", ...init });
  } catch {
    throw new ApiError(0, "Backend not reachable. Start it with: uvicorn backend.app:app --port 8000");
  }
  if (!r.ok) {
    const detail = await r.json().then((j) => j.detail, () => r.statusText);
    throw new ApiError(r.status, typeof detail === "string" ? detail : r.statusText);
  }
  return r.json();
}

const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const getSpace = () => request<SpaceSummary>(`/spaces/${SPACE}`);
export const getDocuments = () => request<DocumentSummary[]>(`/spaces/${SPACE}/documents`);
export const getDocument = (id: string) => request<DocumentDetail>(`/documents/${encodeURIComponent(id)}`);
export const getGraph = () => request<Graph>(`/spaces/${SPACE}/graph`);
export const getEval = () => request<Record<string, any>>(`/spaces/${SPACE}/eval`);
export const getJob = (id: string) => request<Job>(`/jobs/${id}`);
export const startIngest = () => post<Job>(`/spaces/${SPACE}/ingest`, {});
export const uploadDocuments = (files: File[]) => {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  return request<{ files: string[] }>(`/spaces/${SPACE}/documents/upload`, { method: "POST", body: form });
};
export const ask = (question: string, filters: Filters = {}) => post<Answer>(`/spaces/${SPACE}/ask`, { question, filters });
export const compare = (doc_a: string, doc_b: string) => post<CompareResult>(`/spaces/${SPACE}/compare`, { doc_a, doc_b });

export const groupByFolder = (docs: DocumentSummary[]) =>
  docs.reduce<Record<string, DocumentSummary[]>>((g, d) => ((g[d.folder] ??= []).push(d), g), {});
