"""Data shapes shared by ingestion, the API and eval. Mirror of frontend/lib/types.ts: change both together."""
from typing import Literal

from pydantic import BaseModel, Field as PField

ElementType = Literal["text", "table", "figure", "chart", "caption"]
FileType = Literal["pdf", "image", "pptx", "md", "txt"]
ClaimType = Literal["contribution", "limitation", "method", "dataset", "result", "future_work"]
RelationType = Literal["supersedes", "cites", "same_topic", "feedback_on"]
Verification = Literal["verified", "unverified"]
ConfidenceLabel = Literal["High", "Medium", "Low", "Unverified", "Insufficient"]
FieldKind = Literal["text", "date", "amount", "number", "percent"]
FieldStatus = Literal["verified", "unverified", "missing"]  # missing: the document doesn't state it, nothing to verify
CheckStatus = Literal["pass", "fail", "skipped"]
DocType = Literal["invoice", "spec_sheet", "financial_report"]


class BBox(BaseModel):
    """PDF points, TOP-LEFT origin (parse.py converts from Docling's bottom-left)."""
    x0: float
    y0: float
    x1: float
    y1: float


class Table(BaseModel):
    header: list[str]
    rows: list[list[str]]


class Element(BaseModel):
    id: str  # unique within its document
    doc_id: str
    type: ElementType
    page: int  # 1-based; md/txt files are one "page"
    bbox: BBox | None  # None for md/txt
    line: int | None = None  # md/txt: 1-based line where the paragraph starts
    text: str  # paragraph, caption + table markdown, or VLM summary
    heading: str | None = None  # section path, e.g. "3 Method > 3.2 Client selection"
    table: Table | None = None
    crop_url: str | None = None  # set by the API for figures and charts


# --- Knowledge space ---

class Space(BaseModel):
    id: str = PField(pattern=r"^[a-z0-9][a-z0-9_-]{0,40}$")
    name: str
    root: str  # absolute folder path on this machine


class Document(BaseModel):
    id: str  # derived from the relative path, URL-safe
    space_id: str
    title: str
    path: str  # relative to the space root, forward slashes
    folder: str  # first path segment: papers / drafts / supervisor / notes / ...
    file_type: FileType
    file_hash: str
    lang: Literal["en", "ja"]
    pages: int
    page_sizes: list[tuple[float, float]]  # (width, height) in points per page; [] for md/txt
    year: int | None = None
    version_label: str | None = None  # "v2" from problem_formulation_v2.pdf
    stages_done: list[str] = []  # ingestion stages finished since the last parse (resumability)


class Chunk(BaseModel):
    id: str  # "{doc_id}:c{seq}"
    doc_id: str
    seq: int  # order within the document
    page_start: int
    page_end: int
    section_path: str
    text: str
    element_ids: list[str]


class Claim(BaseModel):
    id: str
    doc_id: str
    claim_type: ClaimType
    claim: str
    quote: str
    page: int | None
    element_id: str | None
    bbox: BBox | None
    quote_match: float
    verification: Verification


class Relation(BaseModel):
    id: str
    source_id: str
    target_id: str
    type: RelationType
    evidence: str  # why the edge exists, shown when the edge is clicked
    confidence: float


class Job(BaseModel):
    id: str
    space_id: str
    status: Literal["queued", "running", "done", "error"]
    stage: str = ""
    progress: float = 0.0  # 0..1 within the current stage
    message: str = ""


# --- API shapes ---

class DocumentSummary(Document):
    claims: int
    verified_claims: int
    relations: int


class DocumentDetail(DocumentSummary):
    file_url: str
    elements: list[Element]
    claim_list: list[Claim]
    relation_list: list[Relation]


class SpaceSummary(BaseModel):
    space: Space
    counts: dict[str, int]  # documents, chunks, claims, relations
    folders: dict[str, int]
    recent: list[dict]  # [{id, question, confidence_label}]
    last_job: Job | None


class Filters(BaseModel):
    folders: list[str] | None = None
    doc_ids: list[str] | None = None
    years: list[int] | None = None


class SearchRequest(BaseModel):
    query: str = PField(min_length=1, max_length=500)
    filters: Filters = Filters()
    k: int = PField(default=8, ge=1, le=50)


class SearchHit(BaseModel):
    chunk: Chunk
    document_title: str
    score: float  # dense cosine


class AskRequest(BaseModel):
    question: str = PField(min_length=1, max_length=500)
    filters: Filters = Filters()


class QuoteCheck(BaseModel):
    score: float  # 0..1
    found: bool
    element_id: str | None
    page: int | None
    bbox: BBox | None


class Citation(BaseModel):
    n: int
    chunk_id: str
    document_id: str
    document_title: str
    page: int
    element_id: str | None
    bbox: BBox | None
    type: ElementType
    quote: str
    quote_match: float
    verification: Verification
    crop_url: str | None = None
    table: Table | None = None


class Answer(BaseModel):
    id: str
    question: str
    answer: str
    confidence: float
    confidence_label: ConfidenceLabel
    citations: list[Citation]
    unverified_numbers: list[str]
    approximate: bool  # a cited source is a chart read by the VLM
    used_chunk_ids: list[str]
    relationship_path: list[str]
    latency_ms: int


class CompareRequest(BaseModel):
    doc_a: str
    doc_b: str


class Side(BaseModel):
    doc_id: str
    chunk_id: str
    page: int
    section_path: str
    text: str
    quote: str = ""
    quote_match: float = 0.0
    element_id: str | None = None
    bbox: BBox | None = None


class CompareRow(BaseModel):
    change: Literal["unchanged", "modified", "added", "removed"]
    a: Side | None
    b: Side | None
    similarity: float | None
    summary: str | None  # LLM one-liner for modified rows; None if no LLM


class CompareResult(BaseModel):
    a: Document
    b: Document
    rows: list[CompareRow]


# --- What the LLM is asked to return (guided JSON) ---

class ClaimOut(BaseModel):
    claim_type: ClaimType
    claim: str
    quote: str  # copied EXACTLY from the element
    element_id: str


class ClaimsOut(BaseModel):
    claims: list[ClaimOut]


class CitedQuote(BaseModel):
    n: int
    quote: str


class AnswerOut(BaseModel):
    answer: str  # with [n] markers
    citations: list[CitedQuote]


class ChangeOut(BaseModel):
    summary: str
    quote_a: str
    quote_b: str


class VLMResult(BaseModel):
    kind: Literal["chart", "figure"]
    summary: str  # for figures: description plus any visible labels
    table: Table | None = None  # charts only: the values read off the chart


# --- Structured extraction (extract.py) ---

class Cited(BaseModel):
    """One value as the LLM returns it: copied exactly as printed, with the quote and element it came from.
    All three keys are required and bounded: with optional keys and unbounded strings a constrained decoder lets a
    small model skip `value` and loop inside a string until it runs out of tokens."""
    value: str | None = PField(max_length=200)  # null when the document doesn't state it
    quote: str = PField(max_length=400)  # copied EXACTLY from the element, containing the value
    element_id: str = PField(max_length=12)


def not_stated() -> Cited:
    return Cited(value=None, quote="", element_id="")


class ExtractedField(BaseModel):
    """A Cited value after code has normalised it (normalize_ja.py) and verified it (verify.py)."""
    name: str  # "total", or "line_items[2].amount"
    kind: FieldKind
    raw: str | None  # as printed
    value: str | int | float | None  # normalised: ISO date, yen as int, ...
    tax: Literal["included", "excluded"] | None = None
    quote: str
    page: int | None
    element_id: str | None
    bbox: BBox | None
    quote_match: float  # 0..1, see verify.quote_score
    value_in_quote: bool
    status: FieldStatus


class Check(BaseModel):
    name: str
    status: CheckStatus
    message: str
    fields: list[str] = []  # names of the ExtractedFields involved, so the UI can mark them


class Extraction(BaseModel):
    doc_id: str
    doc_type: DocType
    fields: list[ExtractedField]
    checks: list[Check]
    model: str
    seconds: float


class ParseResult(BaseModel):
    parser: str
    title: str | None
    pages: int
    page_sizes: list[tuple[float, float]]
    elements: list[Element]
