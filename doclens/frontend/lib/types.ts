// Mirror of backend/schemas.py. Change both together.

export type BBox = { x0: number; y0: number; x1: number; y1: number }; // PDF points, top-left origin
export type Table = { header: string[]; rows: string[][] };
export type ElementType = "text" | "table" | "figure" | "chart" | "caption";
export type ClaimType = "contribution" | "limitation" | "method" | "dataset" | "result" | "future_work";
export type RelationType = "supersedes" | "cites" | "same_topic" | "feedback_on";
export type Verification = "verified" | "unverified";
export type ConfidenceLabel = "High" | "Medium" | "Low" | "Unverified" | "Insufficient";

export type Element = {
  id: string;
  doc_id: string;
  type: ElementType;
  page: number;
  bbox: BBox | null; // null for md/txt
  line: number | null;
  text: string;
  heading?: string | null;
  table?: Table | null;
  crop_url?: string | null;
};

export type Space = { id: string; name: string; root: string };

export type Document = {
  id: string;
  space_id: string;
  title: string;
  path: string;
  folder: string;
  file_type: "pdf" | "md" | "txt";
  file_hash: string;
  lang: "en" | "ja";
  pages: number;
  page_sizes: [number, number][];
  year: number | null;
  version_label: string | null;
  stages_done: string[];
};

export type DocumentSummary = Document & { claims: number; verified_claims: number; relations: number };

export type Claim = {
  id: string;
  doc_id: string;
  claim_type: ClaimType;
  claim: string;
  quote: string;
  page: number | null;
  element_id: string | null;
  bbox: BBox | null;
  quote_match: number;
  verification: Verification;
};

export type Relation = {
  id: string;
  source_id: string;
  target_id: string;
  type: RelationType;
  evidence: string;
  confidence: number;
};

export type DocumentDetail = DocumentSummary & {
  file_url: string;
  elements: Element[];
  claim_list: Claim[];
  relation_list: Relation[];
};

export type Job = {
  id: string;
  space_id: string;
  status: "queued" | "running" | "done" | "error";
  stage: string;
  progress: number;
  message: string;
};

export type SpaceSummary = {
  space: Space;
  counts: { documents: number; chunks: number; claims: number; relations: number };
  folders: Record<string, number>;
  recent: { id: string; question: string; confidence_label: ConfidenceLabel }[];
  last_job: Job | null;
};

export type Filters = { folders?: string[] | null; doc_ids?: string[] | null; years?: number[] | null };

export type Citation = {
  n: number;
  chunk_id: string;
  document_id: string;
  document_title: string;
  page: number;
  element_id: string | null;
  bbox: BBox | null;
  type: ElementType;
  quote: string;
  quote_match: number;
  verification: Verification;
  crop_url?: string | null;
  table?: Table | null;
};

export type Answer = {
  id: string;
  question: string;
  answer: string;
  confidence: number;
  confidence_label: ConfidenceLabel;
  citations: Citation[];
  unverified_numbers: string[];
  approximate: boolean;
  used_chunk_ids: string[];
  relationship_path: string[];
  latency_ms: number;
};

export type Side = {
  doc_id: string;
  chunk_id: string;
  page: number;
  section_path: string;
  text: string;
  quote: string;
  quote_match: number;
  element_id: string | null;
  bbox: BBox | null;
};

export type CompareRow = {
  change: "unchanged" | "modified" | "added" | "removed";
  a: Side | null;
  b: Side | null;
  similarity: number | null;
  summary: string | null;
};

export type CompareResult = { a: Document; b: Document; rows: CompareRow[] };

export type Graph = { nodes: DocumentSummary[]; edges: Relation[] };

/** What a source viewer highlights. `seq` changes on every click so the same spot can be re-flashed. */
export type Target = { page: number; bbox: BBox | null; elementId: string | null; seq: number };
