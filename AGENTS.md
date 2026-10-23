# Repository Guidelines

This workspace contains DocLens and a small adjacent demo. Treat `doclens/` as the active application unless a task says otherwise.

## Project Structure

- `doclens/backend/` contains the FastAPI service and document processing modules; `doclens/frontend/` contains the Next.js app (`app/`, `components/`, `lib/`, and `public/`).
- `doclens/tests/` holds pytest tests and fixtures. `data/`, `labels/`, `results/`, `assets/`, and `notebooks/` support ingestion and evaluation.
- `doclens_v1_archive/` is historical code. `fastshot/` is a standalone static page. Root-level Markdown files are project notes.

## Build, Test, and Development

Run Python commands from `doclens/`:

```bash
python -m pip install -r requirements.txt
pytest
uvicorn backend.app:app --port 8000
```

Set `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` in your shell to use model-backed features. In another terminal, run frontend commands from `doclens/frontend/`: `npm install`, `npm run dev` for local development, or `npm run build` for a production build. The frontend proxies API requests to port 8000 by default; set `API_URL` to change the target.

## Coding Style

Follow the surrounding code: use four spaces and `snake_case` for Python, `test_*.py` for test modules, and PascalCase for React component names. Keep TypeScript consistent with nearby TSX files. No formatter or linter command is configured in the frontend package.

## Testing

Run `pytest` from `doclens/`; use a focused file such as `pytest tests/test_verify.py` while iterating. Keep tests deterministic and use `tests/fixtures/` for sample inputs. The project does not define a coverage threshold.

## Commits and Pull Requests

This checkout has no Git history available to establish a commit convention. Use short, imperative commit subjects and keep commits focused. PRs should explain the change, link a related issue when applicable, and report validation performed. Include screenshots for user-visible frontend changes.

## Security and Local Data

Keep API credentials and private research material out of commits. `doclens/data/space/` is gitignored for local-only documents; public inputs should follow the metadata format in `doclens/data/sources.csv`.
