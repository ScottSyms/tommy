# CLAUDE.md — Maritime COP Prototype
## Voice + Map + Agent · Phased Implementation Guide

---

## 0. Project Context

This prototype demonstrates an **agent-assisted Common Operating Picture (COP)** for maritime awareness. It validates a dual-channel interaction model:

- **Visual channel** → MapLibre map with ship overlays, tracks, and data panels
- **Voice channel** → Whisper-transcribed commands, TTS responses, agent-mediated CRUD

The architecture is intentionally **prototype-scoped**: no auth, no streaming, no production scaling. The goal is a working end-to-end demo across five testable phases.

---

## 1. Stack Decisions (Locked)

| Layer | Technology | Notes |
|---|---|---|
| Map | MapLibre GL JS | Open-source, Tauri-compatible for Phase 5+ |
| Frontend | React (Vite) | Lightweight; vanilla JS acceptable if preferred |
| Backend | FastAPI (Python) | Async; tool-calling agent hosted here |
| Agent | Provider-abstracted LLM backend | Start with OpenAI; keep the runtime interface generic enough to swap in Ollama, Anthropic, or another model later |
| Speech-to-Text | `openai-whisper` (local) | `faster-whisper` recommended for speed |
| TTS | Browser `speechSynthesis` | Phase 1; swap for Coqui/Piper in Phase 3 |
| Storage | Parquet + DuckDB | DuckDB handles query pushdown without a DB server |
| Dependency mgmt | `uv` (Python), `pnpm` (Node) | |

---

## 2. Repository Structure

```
maritime-cop/
├── CLAUDE.md                  ← this file
├── backend/
│   ├── main.py                ← FastAPI app entry point
│   ├── agent.py               ← Tool-calling agent logic
│   ├── config.py              ← environment + provider settings
│   ├── llm/
│   │   ├── base.py            ← provider interface
│   │   ├── factory.py         ← provider selection
│   │   └── openai_provider.py ← first SQL-generation provider
│   ├── sql/
│   │   ├── analytics_skill.md ← app-level SQL skill/spec file
│   │   ├── schema_registry.py ← approved query views + column metadata
│   │   ├── prompt_builder.py  ← prompt assembly using skill + context
│   │   ├── validator.py       ← SQL safety checks
│   │   ├── executor.py        ← DuckDB SQL execution helpers
│   │   └── service.py         ← SQL generation + execution pipeline
│   ├── tools/
│   │   ├── identity.py        ← get_ship_identity
│   │   ├── history.py         ← get_position_history
│   │   ├── destinations.py    ← get_recent_destinations
│   │   └── crud.py            ← add / edit / delete / merge positions
│   ├── data/
│   │   ├── loader.py          ← DuckDB connection + query helpers
│   │   └── schema.py          ← Pydantic models
│   ├── voice/
│   │   └── transcribe.py      ← Whisper pipeline
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── Map.jsx        ← MapLibre wrapper
│   │   │   ├── VoiceButton.jsx
│   │   │   ├── ShipPanel.jsx  ← Identity + metadata display
│   │   │   ├── TrackLayer.jsx ← GeoJSON LineString overlay
│   │   │   └── ConflictPanel.jsx
│   │   ├── hooks/
│   │   │   ├── useVoice.js    ← mic capture + transcription
│   │   │   └── useSelection.js← map selection state
│   │   └── api.js             ← backend fetch wrappers
│   ├── public/
│   └── package.json
├── data/
│   ├── seed/                  ← synthetic AIS Parquet files
│   └── generate_seed.py       ← seed data generator script
└── tests/
    ├── backend/
    └── frontend/
```

---

## 3. Data Model

### 3.1 AIS Core Schema

```python
# schema.py
from pydantic import BaseModel
from datetime import datetime

class Position(BaseModel):
    position_id: str       # UUID
    mmsi: int
    imo: int | None
    timestamp: datetime
    lat: float
    lon: float
    sog: float             # Speed over ground (knots)
    cog: float             # Course over ground (degrees)
    heading: float | None
    nav_status: int | None # AIS navigational status code
    ship_type: int | None
    flag: str | None
    destination: str | None

class ShipIdentity(BaseModel):
    mmsi: int
    imo: int | None
    name: str | None
    call_sign: str | None
    ship_type: int | None
    flag: str | None
    length: float | None
    beam: float | None
```

### 3.2 Storage

- **Format**: Parquet, partitioned by `date` (YYYY-MM-DD folders)
- **Engine**: DuckDB with `hive_partitioning=True`
- **Seed data**: ~50,000 synthetic positions across 200 MMSIs, spanning 7 days at roughly 10-minute intervals
- **Identity contract**: each MMSI has stable identity fields for the full seed window: `imo`, `name`, `call_sign`, `ship_type`, `flag`, `length`, `beam`
- **Metadata storage**: ship identity may live in the same Parquet rows for prototype simplicity, but the API contract must treat identity as logically distinct from time-varying position data
- **Bounding box index**: add `lat`/`lon` min–max per partition in a sidecar metadata file for fast spatial pruning

### 3.3 Data Mutability

- **Seed Parquet is immutable**: generated AIS seed data is never edited in place
- **Prototype write path**: Phase 4 CRUD and merge operations persist either in-memory or in a small local overlay store; reads must compose base seed data with overlay mutations
- **Conflict handling target**: duplicate timestamps intentionally seeded for conflict testing should be resolved against the overlay layer rather than rewriting historical partitions

```python
# loader.py pattern
import duckdb

conn = duckdb.connect()

def query_history(mmsi: int, hours: int) -> list[dict]:
    return conn.execute("""
        SELECT * FROM read_parquet('data/seed/**/*.parquet', hive_partitioning=true)
        WHERE mmsi = ?
          AND timestamp >= now() - INTERVAL (?) HOUR
        ORDER BY timestamp
    """, [mmsi, hours]).df().to_dict(orient="records")
```

---

## 4. Phased Implementation Plan

### Delivery Rule

- Complete each phase with the smallest working slice that satisfies its test criteria
- Defer optional polish until the next phase unless it is required to keep the demo coherent
- Prefer deterministic UI logic for obvious commands like showing a selected ship or loading a 24h track; reserve the LLM for ambiguous or conversational requests
- For exploratory analytics questions, prefer a guarded schema-registered text-to-SQL path behind `/agent/query` rather than expanding the deterministic router indefinitely

---

### Phase 1 — Static Map + Ship Data
**Goal**: Map renders ships from seed data. Click a ship, see its identity panel.  
**No voice, no agent yet.**

**MVP cut line**: ship markers render, selection works, and core read APIs return stable shapes. Fancy styling, clustering, and map polish are out of scope.

#### Tasks

1. **Generate seed data** (`data/generate_seed.py`)
   - 200 synthetic MMSIs with realistic lat/lon tracks (North Atlantic / Halifax approaches)
   - Output: `data/seed/date=YYYY-MM-DD/positions.parquet`
   - Include one intentional duplicate timestamp per MMSI for Phase 4 conflict testing

2. **Backend: FastAPI skeleton**
   - `GET /ships` → returns latest position per MMSI as GeoJSON FeatureCollection
   - `GET /ships/{mmsi}` → returns identity + last known position
   - `GET /ships/{mmsi}/history?hours=24` → returns GeoJSON LineString plus ordered source positions

3. **Frontend: MapLibre map**
   - Initialize map centred on Halifax approaches (lat 44.5, lon -63.5, zoom 6)
   - Add GeoJSON source + circle layer for ship positions
   - On click: populate `ShipPanel` with identity data from `GET /ships/{mmsi}`

4. **Frontend: ShipPanel component**
   - Display: MMSI, name, flag, ship type, nav status, SOG, COG, last seen

#### Phase 1 Test Criteria
- [ ] Map loads with ≥ 100 ship markers
- [ ] Clicking a marker populates ShipPanel without page reload
- [ ] `GET /ships/{mmsi}/history` returns ordered positions for any seeded MMSI
- [ ] DuckDB query for 24h history completes in < 500ms on seed dataset

---

### Phase 2 — Track Visualization + Selection State
**Goal**: Selected ship shows 24h track as a line overlay. Multi-ship selection scaffolded.

**MVP cut line**: one selected ship, one rendered track, one stable `selectionContext`, and one destinations read path. Directional arrows and opacity gradients are optional polish after the core track flow is stable.

#### Tasks

1. **Frontend: refactor selection into `useSelection` first**
   - Move selection state out of ad hoc `App.jsx` handlers into `useSelection`
   - Exposes `selectedMMSI`, `select(mmsi)`, `deselect()`, and `selectionContext`
   - `selectionContext` = `{ mmsi, name, lastPosition }`
   - Log `selectionContext` on every selection change for Phase 2 verification

2. **Backend: `GET /ships/{mmsi}/destinations`**
   - Return last N distinct `destination` values in recency order
   - Response shape:

   ```json
   [
     { "destination": "Halifax", "last_seen": "2026-04-09T11:50:00Z" }
   ]
   ```

3. **Frontend: simple `TrackLayer` first**
   - On ship select: fetch `GET /ships/{mmsi}/history?hours=24`
   - Render a single stable `LineString` layer
   - Remove the old track immediately when the selection changes or clears
   - Treat duplicate timestamps deterministically using backend ordering; do not add special merge logic yet

4. **Optional polish only after the base line is stable**
   - Timestamp-weighted opacity
   - Directional arrow markers derived from `cog`
   - Skip these if they introduce stale layers, flicker, or ambiguous visuals around duplicate timestamps

5. **Frontend: keep map lifecycle isolated**
   - `Map.jsx` should create the map once
   - Ship source updates, track source updates, and selection styling updates should be handled in separate effects
   - Do not couple map construction to changing `ships`, `selectedMMSI`, or track state

#### Phase 2 Test Criteria
- [ ] Selecting a ship renders a continuous 24h track line
- [ ] Track clears on deselect and updates when a different ship is selected with no stale layers
- [ ] `selectionContext` is logged on every selection
- [ ] `GET /ships/{mmsi}/destinations?limit=5` returns deduplicated destinations in recency order
- [ ] Directional arrows, if implemented, do not break the base track rendering

---

### Phase 3 — Voice Input Pipeline
**Goal**: Mic button → Whisper transcription → text displayed in UI. No agent yet.

**MVP cut line**: browser mic capture, backend transcription, transcript display, and visible recording/transcribing/error states. TTS remains a stub until Phase 4, and transcripts do not trigger map or agent actions yet.

#### Tasks

1. **Backend: `POST /voice/transcribe`**
   - Accepts `multipart/form-data` with `audio` field (WebM/Opus from browser)
   - Loads `faster-whisper` model (`base.en` for speed)
   - Must decode browser-recorded WebM/Opus input reliably
   - Returns `{ transcript: str, language: str, confidence: float }`

   ```python
   # transcribe.py
   from faster_whisper import WhisperModel
   model = WhisperModel("base.en", device="cpu", compute_type="int8")

   def transcribe(audio_bytes: bytes) -> dict:
       segments, info = model.transcribe(audio_bytes)
       text = " ".join(s.text for s in segments).strip()
       return {"transcript": text, "language": info.language, "confidence": 0.0}
   ```

2. **Frontend: `VoiceButton` component**
   - Push-to-talk: `pointerdown` → record, `pointerup` / `pointercancel` → stop or cancel
   - Uses `MediaRecorder` API with `audio/webm;codecs=opus`
   - Display transcript in a chat-style rail below the map
   - Show visible UI states for recording, uploading, transcribing, and error

3. **Frontend: `useVoice` hook**
   - Manages `MediaRecorder` lifecycle only
   - Exposes `isRecording`, `isTranscribing`, `error`, `startRecording()`, `stopRecording()`, `cancelRecording()`
   - Uses the same centralized backend API base configuration as the rest of the frontend
   - `App.jsx` owns `chatHistory`; on transcript received the app appends a timestamped user utterance
   - Ignore empty or too-short recordings rather than appending junk transcript

4. **TTS stub**: browser `speechSynthesis.speak(utterance)` for all agent responses (Phase 4+)

5. **Runtime note**
   - Frontend and backend must run on known local ports, or the frontend `VITE_API_BASE_URL` must be updated to match the active backend

#### Phase 3 Test Criteria
- [ ] Push-to-talk records audio and displays transcript in < 3s on `base.en` model
- [ ] Transcript rail shows timestamped history of utterances
- [ ] Permission denial and transcription failures produce visible errors
- [ ] Empty or cancelled recordings do not append transcript entries
- [ ] Whisper handles accented English and naval terminology adequately (manual QA)
- [ ] Pointer-event push-to-talk works on desktop and touch-capable browsers
- [ ] Audio capture works in both Chrome and Firefox

---

### Phase 4 — Agent Integration (Tool-Calling)
**Goal**: Voice transcript + selection context → agent → tool execution → visual + voice response.

**MVP cut line**: selected-ship identity queries, 24h track requests, recent destinations, and one conflict flow. Full CRUD breadth matters less than proving the interaction loop end to end.

#### Tasks

1. **Backend: Agent layer** (`agent.py`)

   Tool registry — implement each tool against DuckDB:

   | Tool | Inputs | Returns |
   |---|---|---|
   | `get_ship_identity` | `mmsi` | ShipIdentity object |
   | `get_position_history` | `mmsi`, `time_range_hours` | List of positions as GeoJSON |
   | `get_recent_destinations` | `mmsi`, `limit` | List of `{destination, last_seen}` |
   | `add_position` | `mmsi`, `lat`, `lon`, `timestamp` | New position_id |
   | `edit_position` | `position_id`, `updates` | Updated record |
   | `delete_position` | `position_id` | Confirmation |
   | `merge_positions` | `position_id_1`, `position_id_2` | Merged record or conflict report |

2. **Backend: `POST /agent/query`**

   ```python
   # Request body
   {
     "transcript": str,
     "selection_context": {
       "mmsi": int | None,
       "name": str | None,
       "last_position": object | None
     }
   }

   # Response body
   {
     "reply": str,           # Spoken/displayed response
     "action": str | None,   # e.g. "SHOW_TRACK", "SHOW_PANEL", "SHOW_CONFLICT"
     "payload": object | None # Data needed to execute the action on frontend
    }
    ```

   Include up to the last 6 chat turns in the backend agent call. A turn is:

   ```json
   {
     "role": "user" | "assistant",
     "text": "...",
     "timestamp": "2026-04-09T12:00:00Z"
   }
   ```

3. **Agent system prompt** (in `agent.py`):

   ```
   You are a maritime COP assistant. You help analysts query, edit, and understand
   AIS ship data through natural language.

   Always resolve commands to one of: SELECT, QUERY, ADD, EDIT, DELETE, MERGE.
   If the user's intent is ambiguous, ask exactly one clarifying question.
   If a required parameter is missing, ask for it — do not guess.
   If a conflict is detected during MERGE or EDIT, return a structured conflict
   report rather than proceeding silently.

   The user's current map selection context will be provided with each query.
   Prefer the selected ship as the implicit subject when MMSI is not stated.
   Keep all spoken responses under 3 sentences. Be direct and precise.
   ```

4. **Frontend: wire agent into voice pipeline**
   - After transcription: POST to `/agent/query` with transcript + `selectionContext`
   - On response:
     - Append `reply` to chat rail, speak via TTS
     - Dispatch `action` to map: `SHOW_TRACK` → fetch + render track, `SHOW_PANEL` → update ShipPanel, `SHOW_CONFLICT` → open ConflictPanel

5. **Frontend: `ConflictPanel` component**
   - Renders two conflicting records side-by-side
   - Buttons: **Keep Most Recent**, **Keep Other**, **Merge Manually**, **Cancel**
   - On resolution: POST back to `/positions/merge` with user choice

#### Conflict Report Shape

```json
{
  "conflict_type": "timestamp_collision",
  "message": "These positions conflict on timestamp within 30 seconds of each other.",
  "position_1": { "position_id": "..." },
  "position_2": { "position_id": "..." },
  "suggested_resolution": "keep_most_recent"
}
```

#### Phase 4 Test Criteria
- [ ] "What is this vessel?" with a ship selected → ShipPanel populated, spoken summary
- [ ] "Show the last 24 hours" → track rendered on map
- [ ] "Show the last 5 destinations" → destinations listed in ShipPanel
- [ ] "Add a position here" without coordinates → agent asks for lat/lon
- [ ] Merging two positions with conflicting timestamps → ConflictPanel opens with both records
- [ ] Agent never silently fails — all errors produce a spoken response

---

### Phase 5 — Polish + Extensibility Prep
**Goal**: Harden the shipped deterministic demo path, add bounding-box query, and document extension points.

**MVP cut line**: viewport filtering, structured errors, and one verified end-to-end demo path. Large-scale optimization only matters if the measured prototype actually misses the latency targets, and LLM-backed agent routing remains an optional backend swap behind the same `/agent/query` contract.

#### Tasks

1. **Spatial filtering**: add `GET /ships?bbox=minLon,minLat,maxLon,maxLat` — only return latest ship positions in the current map viewport
   - Frontend should fetch on map `moveend`, not continuously during drag

2. **Performance**: profile DuckDB queries at 10M row scale using `EXPLAIN ANALYZE`; add partition pruning if p95 latency > 1s
   - Measure both base Parquet reads and overlay-composed selected-ship reads

3. **Error handling hardening**:
   - All backend action paths return structured `{ error_type, message, suggested_action }` where appropriate
   - Cover `/agent/query`, `/voice/transcribe`, `/positions/*`, and frontend action dispatch failures
   - Agent surfaces actionable voice prompt for every error type (unclear intent, not found, conflict)

4. **COP Grammar coverage test**: run each command below through the voice pipeline and verify the correct backend action path is called:
   - "Show me this ship"
   - "What is this vessel?"
   - "Show last 24 hours track"
   - "Show last 5 destinations"
   - "Add a position here"
   - "Edit this position"
   - "Delete this track"
   - "Merge these two tracks"
   - If edit/delete are not fully conversational yet, complete those flows here or explicitly narrow the verified grammar set to the implemented commands

5. **Extension stubs** (code-complete but inactive):
   - `POST /ingest/ais` → placeholder for real-time AIS feed
   - `GET /alerts` → placeholder for geofence / anomaly alerting
   - Tauri-compatibility note in `main.py`: API layer is stateless, no browser APIs used

6. **Browser hardening pass**
   - Manually verify the shipped browser path: ship selection, transcript rail updates, assistant reply + TTS, conflict panel resolution, and track refresh

7. **Selection consistency hardening**
   - Ensure selection changes do not leave stale panel, track, or conflict state behind
   - Conflict resolution should refresh only the currently selected vessel

8. **Schema-registered SQL analytics extension**
   - Add an app-level SQL skill/spec file in Markdown, owned by the backend and independent of any single model provider
   - Route exploratory analytics questions through the deterministic router first, then fall back to text-to-SQL when the request is not a known operational command
   - Generated SQL must be shown visibly in the frontend along with a summarized result preview

#### SQL Analytics Extension Guidelines

- **Skill/spec artifact**: add `backend/sql/analytics_skill.md` with the approved views, column meanings, domain rules, SQL safety rules, output contract, and worked examples
- **Stable semantic surface**: expose only backend-owned analytical views such as `cop_ship_positions`, `cop_ship_identity`, and `cop_latest_ship_positions`; never expose raw Parquet paths to the model
- **Provider abstraction**: all model calls should go through a provider interface so OpenAI can be swapped out for Ollama, Anthropic, or another model later without changing `/agent/query`
- **Config model**: load provider choice, model name, and API credentials from environment-backed backend config rather than hardcoding a vendor in the agent logic
- **Fallback routing**: deterministic command handling remains first; text-to-SQL is the fallback for ad-hoc analytics like destination history, counts, extrema, and timing follow-ups
- **SQL validation**: allow only read-only `SELECT` or `WITH ... SELECT`, one statement, approved views only, and bounded result sets; reject DDL/DML and unsafe keywords before execution
- **Visible SQL**: frontend insight payloads should include generated SQL and a small result preview so analysts can inspect how the answer was derived
- **Follow-up context**: use recent chat turns plus selection context to resolve follow-ups like `When?`, `How many times?`, and `What was the max?` before building the SQL prompt

#### Phase 5 Test Criteria
- [ ] All 8 COP grammar commands invoke the correct tool
- [ ] Viewport-filtered ship load < 200ms for typical zoom level
- [ ] Demo runs end-to-end: voice → agent → map update → spoken response with no manual intervention
- [ ] ConflictPanel resolves and persists the user's choice (in-memory for prototype)
- [ ] Conflict resolution refreshes the visible selected track
- [ ] Viewport filtering triggers on `moveend` without spamming requests during pan/zoom
- [ ] Browser demo path is manually verified end-to-end
- [ ] Ad-hoc analytics questions can fall back to schema-registered SQL generation without breaking deterministic operational commands
- [ ] Generated SQL is shown visibly in the ShipPanel along with a result preview

---

## 5. API Reference (FastAPI)

```
POST /voice/transcribe          → { transcript, language }
POST /agent/query               → { reply, action, payload }

GET  /ships                     → GeoJSON FeatureCollection (latest positions)
GET  /ships?bbox=...            → filtered by viewport
GET  /ships/{mmsi}              → ShipIdentity + last position
GET  /ships/{mmsi}/history      → GeoJSON LineString (query param: hours)
GET  /ships/{mmsi}/destinations → [ { destination, last_seen } ] (query param: limit)

POST   /positions               → { position_id }
PUT    /positions/{id}          → updated Position
DELETE /positions/{id}          → { deleted: true }
POST   /positions/merge         → merged Position | ConflictReport

# optional internal analytics shape returned via /agent/query payload
payload.insight.generated_sql   → generated SQL string for analyst inspection
payload.insight.result_preview  → small tabular preview of SQL results
```

### Example: `GET /ships/{mmsi}`

```json
{
  "identity": {
    "mmsi": 316001234,
    "imo": 9387421,
    "name": "MV ATLANTIC STAR",
    "call_sign": "CFAS",
    "ship_type": 70,
    "flag": "CA",
    "length": 225.0,
    "beam": 32.2
  },
  "last_position": {
    "position_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
    "timestamp": "2026-04-09T11:50:00Z",
    "lat": 44.61,
    "lon": -63.21,
    "sog": 12.4,
    "cog": 84.0,
    "heading": 83.0,
    "nav_status": 0,
    "destination": "Halifax"
  }
}
```

### Example: `GET /ships/{mmsi}/history?hours=24`

```json
{
  "mmsi": 316001234,
  "hours": 24,
  "track": {
    "type": "Feature",
    "geometry": {
      "type": "LineString",
      "coordinates": [[-63.9, 44.2], [-63.7, 44.4], [-63.21, 44.61]]
    },
    "properties": {
      "point_count": 3,
      "start_time": "2026-04-08T12:00:00Z",
      "end_time": "2026-04-09T11:50:00Z"
    }
  },
  "positions": [
    {
      "position_id": "...",
      "timestamp": "2026-04-08T12:00:00Z",
      "lat": 44.2,
      "lon": -63.9,
      "cog": 72.0
    }
  ]
}
```

### Example: `GET /ships/{mmsi}/destinations?limit=5`

```json
[
  { "destination": "Halifax", "last_seen": "2026-04-09T11:50:00Z" },
  { "destination": "Saint John", "last_seen": "2026-04-08T07:40:00Z" }
]
```

### Error Contract

All non-2xx API responses should return a predictable error shape:

```json
{
  "error_type": "not_found",
  "message": "Ship 316001234 was not found",
  "suggested_action": "Select another vessel or verify the MMSI"
}
```

---

## 6. Agent COP Grammar

| User says | Normalized intent | Tool(s) called |
|---|---|---|
| "Show me this ship" | SELECT | `get_ship_identity` |
| "What is this vessel?" | QUERY | `get_ship_identity` |
| "Show last 24 hours track" | QUERY | `get_position_history(hours=24)` |
| "Show last 5 destinations" | QUERY | `get_recent_destinations(limit=5)` |
| "Add a position here" | ADD | `add_position` |
| "Edit this position" | EDIT | `edit_position` |
| "Delete this track" | DELETE | `delete_position` (looped per position in track) |
| "Merge these two tracks" | MERGE | repeated `merge_positions` over candidate duplicate positions, or a conflict report if user intent must be narrowed |

---

## 7. Conflict Resolution Protocol

**Trigger**: `merge_positions` returns `conflict_type` in response.

**Agent behaviour**:
1. Describe the conflict in one sentence (e.g., "These positions conflict on timestamp within 30 seconds of each other.")
2. Propose a default resolution (most recent wins).
3. Await user confirmation or override via `ConflictPanel`.

**Frontend**: `ConflictPanel` renders both records with diff highlighting. Resolution posts to `POST /positions/merge` with `resolution: "keep_1" | "keep_2" | "manual"`.

**Semantic note**: voice commands may refer to "tracks", but merge is defined at the position level for this prototype unless an explicit higher-level track merge flow is added later.

---

## 8. Non-Goals (Prototype Scope)

- No authentication or authorization
- No real-time AIS streaming (seed data only)
- No production database (DuckDB file-mode only)
- No multi-user sessions
- No mobile-optimized layout
- No full COP UI complexity (no AOR management, no OPORD integration)

---

## 9. Known Weak Spots to Watch

- **Whisper latency**: `base.en` on CPU is ~2–4s for 5s audio. If unacceptable, switch to `tiny.en` or use GPU.
- **DuckDB write contention**: DuckDB file-mode allows one writer. ADD/EDIT/DELETE ops must be serialized server-side. Use a simple asyncio lock around write operations.
- **MapLibre + React**: use `useRef` for the map instance; never re-render the map container div.
- **Map layer lifecycle**: create the MapLibre instance exactly once. Manage ship data, track data, and selection highlighting through independent source/layer updates to avoid stale overlays during later phases.
- **Browser mic permissions**: HTTPS required in production. Use `localhost` for dev — it's exempted.
- **Agent context window**: pass only the last 6 turns of chat history to avoid token bloat.
- **Duplicate timestamps**: seeded duplicates are for conflict testing. Phase 2 track rendering should use deterministic ordering only; visual conflict handling belongs to Phase 4.
- **Agent architecture**: the current implementation may use a deterministic router behind `/agent/query`. Treat LLM-backed tool-calling as a later backend swap unless Phase 5 explicitly adds it.
- **Demo seed requirement**: keep at least one duplicate timestamp per MMSI within the last 24 hours so the conflict demo remains testable.
- **Text-to-SQL safety**: raw SQL generation is flexible but must be constrained by approved analytical views, strict validation, and execution limits before it touches DuckDB.
- **Prompt portability**: keep the SQL skill/spec file provider-agnostic so the same backend-owned instructions can be reused across OpenAI, Ollama, Anthropic, or later local models.

---

## 10. Frontend State Ownership

- `App.jsx` owns high-level session state: `selectedMMSI`, `selectionContext`, `shipDetail`, `track`, `chatHistory`, `conflictState`
- `useSelection` encapsulates selection updates and derives `selectionContext`
- `useVoice` encapsulates recording and transcription lifecycle, but appends successful utterances into app-owned `chatHistory`
- `Map.jsx` receives data and callbacks; it should not become the source of truth for selected ship or track state
- `ConflictPanel` is controlled by app state and should render from a structured conflict payload only

---

## 11. Testing Strategy

- **Backend**: use `pytest` for API route coverage and data-layer queries against generated seed data
- **Frontend**: add component smoke tests plus one interaction test for ship selection and one for transcript rail updates
- **Manual QA**: reserve browser mic permissions, transcription quality, and TTS behavior for manual verification
- **Agent verification**: for COP grammar coverage, assert both returned action shape and invoked backend tool selection where feasible

---

## 12. Dev Workflow

- Generate seed data before starting either app surface
- Backend workflow: install with `uv`, run FastAPI locally, and expose a single local base URL to the frontend
- Frontend workflow: install with `pnpm`, run the Vite dev server, and configure the backend base URL in one place
- Keep startup commands documented in `README.md` once scaffolding exists

---

## 13. Definition of Done (Full Prototype)

A complete demonstration session must show, without human intervention between steps:

1. Map loads with ship markers from seed data
2. Analyst clicks a ship → ShipPanel populates
3. Analyst says "Show last 24 hours" → track renders on map, spoken confirmation
4. Analyst says "Show last 5 destinations" → destinations listed, spoken
5. Analyst says "Merge these two tracks" on a seeded conflict pair → ConflictPanel opens, spoken explanation, analyst clicks **Keep Most Recent** → panel closes, track updates
6. Analyst says "What is this vessel?" on a different ship with nothing selected → agent asks which ship, analyst answers by clicking → ShipPanel updates
