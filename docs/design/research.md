# Research evidence: ingestion and retrieval (P12-T05)

Status: implemented in P12-T05.
- **Code:** `backend/app/modules/research/`:
  - `models.py`: the `research_items` table (migration 0018);
  - `embedding.py`, `sources.py`, `service.py` and `api.py`.
- **AI tool:** `get_asset_research`.
- **Jobs:** `ingest_research`, daily at 03:00 UTC.
- **Decisions:** the P12 advance approval in EXECUTION_LOG.md, 2026-10-13: synthetic DEMO notes; EDGAR fixture-only; a replaceable embedding with a deterministic test model; text search as a backstop.

## 1. What an evidence item is

Public research about an instrument or a market. It is reference data: no row belongs to a user, and nothing about a user is stored with it.

| Field | Meaning |
|---|---|
| `source`, `source_id` | where it came from and its id there; unique together |
| `source_url` | where the source publishes it: **provenance only**. The app and the AI never fetch it (ai-governance.md: no model-generated or stored URL is fetched) |
| `licence_status` | `demo` (synthetic), `public_domain` (for example SEC EDGAR records), `unconfirmed` or `licensed` |
| `is_demo` | synthetic, labelled DEMO, never presented as live |
| `published_at`, `retrieved_at` | the source's time (as-of) and when we obtained it; the database refuses a retrieval time before publication |
| `asset_id` | the instrument it is about, when it is about one |
| `embedding`, `embedding_model` | the pgvector embedding and the model that made it |
| `search` | a generated full-text vector of title and summary |

Every item therefore has a source, a licence status and an as-of time (acceptance criterion).

## 2. Sources

| Source | What | Status |
|---|---|---|
| `DemoResearchSource` | 16 synthetic notes about the DEMO universe and one fictional currency note, each titled "DEMO note: ..." and with no advice wording (tested) | loaded daily, **only with fake market data**, like the DEMO universe |
| `EdgarSubmissionsSource` | filings of chosen forms (10-K, 10-Q, 8-K, 20-F, 6-K) from an EDGAR submissions document, with their archive links | **fixture-only**: tested on a synthetic document, never scheduled, no network. A live adapter would follow SEC fair access (a declared User-Agent, at most 10 requests a second) and needs approval |

**Ingestion:**
- **Idempotent:** one row per (source, source id). A changed text is updated and re-embedded; unchanged text keeps its first retrieval time.
- **Linking:** notes are linked to the public catalogue asset with their universe symbol. An unknown symbol is left unlinked and reported.

## 3. Embeddings

`Embedder` is a replaceable interface. Only `HashEmbedder` (`hash-v1`) exists:
- deterministic hashing of word unigrams and bigrams into 256 dimensions, L2-normalised;
- no external service.

It is good enough to test retrieval end to end. The production model is chosen before launch: an embedding API, which would receive **public research text only, never user data**, or a local model. `RESEARCH_EMBEDDER` names the model. Each row records its model, so a change of model means re-embedding.

## 4. Retrieval

`GET /api/v1/research`:
- With `q`, and optionally `asset_id`: the most relevant items. Relevance is the mean of cosine similarity (pgvector, HNSW index) and full-text rank (`websearch_to_tsquery`), from 0 to 1. Ties go to the newest, then the id.
- With `asset_id` only: that instrument's research, newest first.
- `limit` is at most 20.
- Neither `q` nor `asset_id` gives 422.

**User-agnostic:** sign-in is required, but no user data is read, so the same query gives every user the same answer (tested).

**AI tool:** `get_asset_research(asset_id)` returns the instrument's evidence, or `none`, for an asset the user can see; another user's private asset is not found. The model may quote only what is returned and never fetches a source URL.

## 5. Tests

- `tests/research/test_embedding_and_sources.py`: embedder determinism and similarity; the DEMO notes are labelled and free of advice wording; EDGAR parsing and form filtering.
- `tests/research/test_research_api.py`:
  - provenance on every row; idempotency; re-embedding on change; unknown symbols;
  - EDGAR rows; search ranking and the same answer for two users; an instrument's research;
  - validation; the tool (evidence, none, visibility); the job in both modes; the schedule.
