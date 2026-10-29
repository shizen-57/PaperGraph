"""SQLite store (stdlib sqlite3). Each row keeps the full Pydantic model as JSON plus the columns we filter on."""
import json
import sqlite3
import threading
from pathlib import Path
from typing import TypeVar

import numpy as np
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)  # not PEP 695 syntax: Kaggle runs Python 3.11

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
LABELS = ROOT / "labels"

SCHEMA = """
CREATE TABLE IF NOT EXISTS spaces    (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, space_id TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS elements  (doc_id TEXT NOT NULL, id TEXT NOT NULL, seq INTEGER NOT NULL, data TEXT NOT NULL,
                                      PRIMARY KEY (doc_id, id));
CREATE TABLE IF NOT EXISTS chunks    (id TEXT PRIMARY KEY, doc_id TEXT NOT NULL, seq INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS claims    (id TEXT PRIMARY KEY, doc_id TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS extractions (doc_id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS relations (id TEXT PRIMARY KEY, space_id TEXT NOT NULL, source_id TEXT NOT NULL,
                                      target_id TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS answers   (id TEXT PRIMARY KEY, space_id TEXT NOT NULL, created REAL NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs      (id TEXT PRIMARY KEY, space_id TEXT NOT NULL, created REAL NOT NULL, data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS chunks_doc ON chunks (doc_id, seq);
CREATE INDEX IF NOT EXISTS claims_doc ON claims (doc_id);
"""


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        # the API runs ingestion in a worker thread, so one shared connection behind a lock
        # ponytail: global lock; fine for one local user
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self.lock = threading.Lock()

    def exec(self, sql: str, params=(), many: bool = False):
        with self.lock, self.conn:
            return (self.conn.executemany if many else self.conn.execute)(sql, params)

    def rows(self, sql: str, params=()) -> list[tuple]:
        with self.lock:
            return self.conn.execute(sql, params).fetchall()

    def models(self, cls: type[T], sql: str, params=()) -> list[T]:
        """sql must select the data column first."""
        return [cls.model_validate_json(r[0]) for r in self.rows(sql, params)]

    def one(self, cls: type[T], sql: str, params=()) -> T | None:
        found = self.models(cls, sql, params)
        return found[0] if found else None


def dump(m: BaseModel) -> str:
    return m.model_dump_json()


def emb_path(results: Path, doc_id: str) -> Path:
    return results / "emb" / f"{doc_id}.npy"


def write_emb(results: Path, doc_id: str, matrix: np.ndarray) -> None:
    """One row per chunk, in chunk seq order."""
    emb_path(results, doc_id).parent.mkdir(parents=True, exist_ok=True)
    np.save(emb_path(results, doc_id), matrix)


def read_emb(results: Path, doc_id: str) -> np.ndarray | None:
    p = emb_path(results, doc_id)
    return np.load(p) if p.exists() else None


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def read_json(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
