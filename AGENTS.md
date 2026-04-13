# AGENTS.md — Maritime COP Prototype
## Skill-Driven Common Operating Picture · Architecture and Implementation Guide

---

## 0. Project Context

This prototype demonstrates an **agent-assisted Common Operating Picture (COP)** for maritime awareness built on a **skill-driven extensibility architecture**. The system is designed around a stable core platform that can be extended with new data sources, query behaviours, and map capabilities by dropping Markdown skill files into the `skills/` directory — no code changes required.

The interaction model has two channels:

- **Visual channel** → MapLibre map with ship overlays, tracks, and data panels registered by skills
- **Voice channel** → Whisper-transcribed commands, TTS responses, agent-mediated operations defined by skills

### Core design principle

The **platform** owns the map rendering, voice pipeline, selection state, conflict UI, and the agent loop. What varies — data sources, query behaviours, CRUD operations, and map layers — is defined entirely by skill files. The agent composes its system prompt at runtime from a base COP prompt plus the domain prompt fragments contributed by each active skill. The tool dispatcher routes agent tool calls to whichever skill registered a matching tool signature.

**The boundary rule**: skills declare intent and data contracts. The platform handles execution, transport, and rendering. When a skill needs conditional logic, that logic belongs in the platform layer, not the skill file.

The architecture is intentionally **prototype-scoped**: no auth, no streaming, no production scaling. The goal is a working end-to-end demo across five testable phases that also proves the extensibility model.

---

## 1. Stack Decisions (Locked)

| Layer | Technology | Notes |
|---|---|---|
| Map | MapLibre GL JS | Open-source, Tauri-compatible for Phase 5+ |
| Frontend | React (Vite) | Lightweight; vanilla JS acceptable if preferred |
| Backend | FastAPI (Python) | Async; skill loader, agent, and tool dispatcher hosted here |
| Agent | Provider-abstracted LLM backend | Start with OpenAI; runtime interface must be generic enough to swap in Ollama, Anthropic, or another model |
| Speech-to-Text | `openai-whisper` (local) | `faster-whisper` recommended for speed |
| TTS | Piper | Local backend-served WAV synthesis; frontend plays returned audio. Default voice: `models/en_US-ryan-high.onnx` |
| Storage | Parquet + DuckDB | DuckDB handles query pushdown without a DB server |
| Dependency mgmt | `uv` (Python), `pnpm` (Node) | |

---

## 2. Repository Structure

```
maritime-cop/
├── AGENTS.md                    ← this file
├── backend/
│   ├── main.py                  ← FastAPI app entry point
│   ├── agent.py                 ← Agent loop; composes prompt from base + skills
│   ├── config.py                ← Environment + provider settings
│   ├── skill_loader.py          ← Discovers and parses skills/ at startup
│   ├── tool_dispatcher.py       ← Routes agent tool calls to skill-registered handlers
│   ├── llm/
│   │   ├── base.py              ← Provider interface
│   │   ├── factory.py           ← Provider selection
│   │   └── openai_provider.py   ← First provider implementation
│   ├── skills/                  ← Drop-in skill files (one .md per data domain)
│   │   └── ais_positions.md     ← AIS data domain skill (see Section 4)
│   ├── sql/
│   │   ├── schema_registry.py   ← Approved query views + column metadata
│   │   ├── prompt_builder.py    ← Prompt assembly from skill + context
│   │   ├── validator.py         ← SQL safety checks
│   │   ├── executor.py          ← DuckDB SQL execution helpers
│   │   └── service.py           ← SQL generation + execution pipeline
│   ├── data/
│   │   ├── loader.py            ← DuckDB connection + query helpers
│   │   └── schema.py            ← Pydantic models
│   ├── voice/
│   │   └── transcribe.py        ← Whisper pipeline
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── Map.jsx          ← MapLibre wrapper; registers skill-declared layers
│   │   │   ├── VoiceButton.jsx
│   │   │   ├── ShipPanel.jsx    ← Identity + metadata display
│   │   │   ├── TrackLayer.jsx   ← GeoJSON LineString overlay
│   │   │   └── ConflictPanel.jsx
│   │   ├── hooks/
│   │   │   ├── useVoice.js      ← Mic capture + transcription lifecycle
│   │   │   └── useSelection.js  ← Map selection state
│   │   └── api.js               ← Backend fetch wrappers
│   ├── public/
│   └── package.json
├── models/
│   ├── en_US-ryan-high.onnx     ← Release-default Piper voice model
│   └── en_US-ryan-high.onnx.json
├── data/
│   ├── seed/                    ← Synthetic AIS Parquet files
│   └── generate_seed.py
└── tests/
    ├── backend/
    └── frontend/
```

---

## 3. Skill-Driven Architecture

### 3.1 Overview

The extensibility model has three components working together:

**Skill loader** (`skill_loader.py`) scans `backend/skills/` at startup and parses each `.md` file into a structured skill manifest containing: source declaration, tool signatures, domain prompt fragment, map layer registrations, and SQL view declarations. The loader makes active skills available to the agent and tool dispatcher.

**Agent** (`agent.py`) composes the full system prompt at runtime by concatenating the base COP prompt with the domain prompt fragment from each active skill. Tool definitions passed to the LLM are the union of all tool signatures registered across active skills. The agent never contains domain-specific knowledge — that lives entirely in skill files.

**Tool dispatcher** (`tool_dispatcher.py`) receives tool call requests from the agent and routes them to the execution handler registered by the appropriate skill. Handlers are thin wrappers that call into `sql/service.py`, `data/loader.py`, or an external REST endpoint as declared by the skill.

### 3.2 Skill File Structure

Each skill file is a Markdown document with a YAML front matter block followed by four required sections. The platform parses these sections at startup; prose and examples are read by the agent as part of its domain prompt.

```markdown
---
skill: ais_positions
version: 1.0
source_type: parquet          # parquet | rest | overlay
source_path: data/seed/**/*.parquet
map_layers:
  - id: ship_positions
    type: circle
    toggle: true
  - id: ship_track
    type: line
    toggle: true
---

## Source

[Schema description, partition strategy, access pattern, mutability rules]

## Tools

[Tool signatures as a table: name | inputs | outputs | constraints]

## Domain prompt

[Natural language instructions the agent follows when handling queries
against this data source: grammar, caution rules, reply style, conflict
handling, fallback behaviour]

## SQL views

[Approved view names, column meanings, domain rules, worked examples,
safety constraints for text-to-SQL queries]
```

The platform reads the YAML front matter for source wiring and map layer registration. It reads the `## Domain prompt` section as a system prompt fragment appended to the base COP prompt. It reads the `## Tools` section to register tool signatures with the dispatcher. The `## SQL views` section is injected into the SQL prompt builder when the skill's source type is `parquet`.

### 3.3 Adding a New Data Domain

To add a new data domain to the COP:

1. Create `backend/skills/<domain_name>.md` following the structure above
2. Declare the source and any map layers in the YAML front matter
3. Write the tool signatures table
4. Write the domain prompt governing agent behaviour for this source
5. If querying via DuckDB, declare approved views and SQL guidance
6. Restart the backend — the skill loader picks it up automatically

No changes to `agent.py`, `tool_dispatcher.py`, or any frontend code are required unless the skill introduces a new map layer type not yet supported by `Map.jsx`.

### 3.4 Skill Design Constraints

- Skills declare intent and contracts. Execution logic lives in the platform.
- A skill tool signature must map to a generic execution path: DuckDB query, REST call, or Parquet overlay write. If it needs custom logic, add a named handler to `tool_dispatcher.py` and reference it in the skill front matter.
- Domain prompt fragments are appended, not merged. Keep them self-contained and avoid contradicting the base COP prompt.
- Map layer IDs declared in a skill must be unique across all active skills.
- SQL views declared in a skill are registered with `schema_registry.py` at startup. Raw Parquet paths are never exposed to the model.

---

## 4. AIS Positions Skill (`skills/ais_positions.md`)

This is the first skill file and the reference implementation. Its content is shown here in full as the authoritative spec for how skill files are written.

````markdown
---
skill: ais_positions
version: 1.0
source_type: parquet
source_path: data/seed/**/*.parquet
map_layers:
  - id: ship_positions
    type: circle
    toggle: false          # always visible; not user-togglable
  - id: ship_track
    type: line
    toggle: true
  - id: ship_track_points
    type: circle
    toggle: true
---

## Source

AIS position and identity data stored as Parquet, partitioned by `date` (YYYY-MM-DD folders).
DuckDB with `hive_partitioning=True` handles query pushdown.

Seed data: ~50,000 synthetic positions across 200 MMSIs, spanning 7 days at 10-minute intervals.
Each MMSI has stable identity fields for the full seed window: `imo`, `name`, `call_sign`,
`ship_type`, `flag`, `length`, `beam`.

**Mutability**: seed Parquet is immutable. ADD/EDIT/DELETE operations persist to an in-memory
overlay store. Reads compose base seed data with overlay mutations. Duplicate timestamps are
seeded intentionally for conflict testing; resolve against the overlay layer, never rewrite
historical partitions.

**Bounding box index**: `lat`/`lon` min–max per partition in a sidecar metadata file for
spatial pruning on viewport-filtered queries.

## Tools

| Tool | Inputs | Outputs | Constraints |
|---|---|---|---|
| `get_ship_identity` | `mmsi: int` | `ShipIdentity` object | None |
| `get_position_history` | `mmsi: int`, `time_range_hours: int` | GeoJSON LineString + ordered positions | Max 168 hours |
| `get_recent_destinations` | `mmsi: int`, `limit: int` | `[{destination, last_seen}]` | Max limit 20 |
| `get_ships_in_bbox` | `min_lon, min_lat, max_lon, max_lat: float` | GeoJSON FeatureCollection (latest positions) | Viewport-scoped |
| `add_position` | `mmsi: int`, `lat: float`, `lon: float`, `timestamp: datetime` | `{position_id: str}` | Writes to overlay only |
| `edit_position` | `position_id: str`, `updates: dict` | Updated position record | Overlay only; requires confirmation |
| `delete_position` | `position_id: str` | `{deleted: true}` | Overlay only; requires confirmation |
| `merge_positions` | `position_id_1: str`, `position_id_2: str` | Merged record or `ConflictReport` | Returns conflict report if timestamps within 30s |

## Domain prompt

You are operating on AIS ship position and identity data. Apply the following rules for all
queries against this data source.

**Intent resolution**: Always resolve the user's command to one of SELECT, QUERY, ADD, EDIT,
DELETE, or MERGE before calling a tool. If intent is ambiguous, ask exactly one clarifying
question. If a required parameter is missing, ask for it — never guess.

**Implicit subject**: When the user does not state an MMSI or vessel name, use the currently
selected vessel from the map selection context as the implicit subject. If nothing is selected
and the command requires a vessel, ask the user to select one.

**Identity preference**: Always prefer vessel names in spoken and displayed replies when
identity is known. Use MMSI only as supporting detail or for disambiguation.

**CRUD caution**: ADD, EDIT, and DELETE operations modify the overlay store. Before executing,
confirm with the user in one sentence. Never silently modify data.

**Conflict handling**: If `merge_positions` returns a `ConflictReport`, describe the conflict
in one sentence, propose the default resolution (most recent wins), and await user confirmation.
Do not proceed with a merge silently.

**Reply style**: Keep all spoken responses under 3 sentences. Be direct and precise. For
analytics results, lead with the answer, then the supporting detail.

**Track rendering**: Do not auto-render a 24-hour track when a vessel is selected. Tracks
are rendered only after an explicit voice or UI command.

**Fallback**: For exploratory analytics questions that are not a known operational command,
fall back to schema-registered text-to-SQL via the `## SQL views` section below.

## SQL views

**Approved views** (never expose raw Parquet paths to the model):

- `cop_ship_positions` — all position records with full fields
- `cop_ship_identity` — stable identity fields per MMSI
- `cop_latest_ship_positions` — one row per MMSI, most recent position

**Column reference**:

| View | Key columns | Notes |
|---|---|---|
| `cop_ship_positions` | `mmsi`, `timestamp`, `lat`, `lon`, `sog`, `cog`, `heading`, `nav_status`, `destination` | Time-varying |
| `cop_ship_identity` | `mmsi`, `imo`, `name`, `call_sign`, `ship_type`, `flag`, `length`, `beam` | Stable per MMSI |
| `cop_latest_ship_positions` | All of the above joined | Use for "current" state queries |

**SQL discipline**:
- Allow only `SELECT` or `WITH ... SELECT`. One statement. No DDL or DML.
- Alias every relation in joins. Qualify `mmsi`, `timestamp`, `lat`, `lon`, `name`,
  `destination` in all multi-relation queries to avoid DuckDB binder ambiguity.
- Bound all result sets: `LIMIT 100` unless the user requests an aggregate.
- Reject queries referencing any table or path not in the approved view list.

**Domain rules**:
- `nav_status = 0` means underway using engine.
- `sog` is knots. Flag `sog > 30` as anomalous for most vessel types.
- `destination` is self-reported by the vessel and may be empty, misspelled, or stale.
- `ship_type` is an ITU/AIS integer code. Do not expose raw codes in replies; map to
  human-readable categories where known (e.g. 70 = cargo, 80 = tanker).

**Worked example**:

User asks: "How many vessels entered Halifax in the last 24 hours?"

```sql
WITH recent AS (
  SELECT p.mmsi, i.name, p.destination, p.timestamp
  FROM cop_ship_positions AS p
  JOIN cop_ship_identity AS i ON i.mmsi = p.mmsi
  WHERE p.timestamp >= now() - INTERVAL 24 HOUR
    AND lower(p.destination) LIKE '%halifax%'
)
SELECT count(DISTINCT recent.mmsi) AS vessel_count
FROM recent
LIMIT 1
```

Reply: "Fourteen vessels reported Halifax as destination in the last 24 hours."
````

---

## 5. Data Model

### 5.1 AIS Core Schema

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

class ConflictReport(BaseModel):
    conflict_type: str          # e.g. "timestamp_collision"
    message: str
    position_1: dict
    position_2: dict
    suggested_resolution: str   # "keep_most_recent" | "keep_other" | "manual"
```

### 5.2 Storage

- **Format**: Parquet, partitioned by `date` (YYYY-MM-DD folders)
- **Engine**: DuckDB with `hive_partitioning=True`
- **Seed data**: ~50,000 synthetic positions across 200 MMSIs, 7 days, 10-minute intervals
- **Overlay store**: in-memory dict keyed by `position_id`; reads compose base Parquet with overlay
- **Bounding box index**: lat/lon min–max sidecar per partition for spatial pruning

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

### 5.3 Data Mutability

- Seed Parquet is immutable — never edited in place
- Phase 4 CRUD operations persist in-memory or in a small local overlay store
- Reads compose base seed data with overlay mutations
- Conflict resolution posts to `POST /positions/merge` with `resolution: "keep_1" | "keep_2" | "manual"`

---

## 6. Backend: Skill Loader and Tool Dispatcher

### 6.1 Skill Loader (`skill_loader.py`)

```python
import yaml
import pathlib
from dataclasses import dataclass, field

@dataclass
class SkillManifest:
    name: str
    version: str
    source_type: str          # parquet | rest | overlay
    source_path: str | None
    map_layers: list[dict]
    domain_prompt: str        # extracted ## Domain prompt section
    tool_signatures: list[dict]  # extracted ## Tools table rows
    sql_views: str | None     # extracted ## SQL views section, if present

def load_skills(skills_dir: str = "backend/skills") -> list[SkillManifest]:
    manifests = []
    for path in pathlib.Path(skills_dir).glob("*.md"):
        raw = path.read_text()
        front_matter, body = _parse_front_matter(raw)
        manifests.append(SkillManifest(
            name=front_matter["skill"],
            version=front_matter.get("version", "1.0"),
            source_type=front_matter.get("source_type", "parquet"),
            source_path=front_matter.get("source_path"),
            map_layers=front_matter.get("map_layers", []),
            domain_prompt=_extract_section(body, "Domain prompt"),
            tool_signatures=_parse_tools_table(_extract_section(body, "Tools")),
            sql_views=_extract_section(body, "SQL views"),
        ))
    return manifests
```

### 6.2 Tool Dispatcher (`tool_dispatcher.py`)

```python
# Generic execution paths — no domain-specific logic here
EXECUTION_PATHS = {
    "parquet": execute_duckdb_query,
    "rest":    execute_rest_call,
    "overlay": execute_overlay_write,
}

def dispatch(tool_name: str, inputs: dict, skills: list[SkillManifest]) -> dict:
    for skill in skills:
        for sig in skill.tool_signatures:
            if sig["name"] == tool_name:
                handler = NAMED_HANDLERS.get(tool_name) or EXECUTION_PATHS[skill.source_type]
                return handler(sig, inputs, skill)
    raise ToolNotFoundError(f"No skill registered tool: {tool_name}")
```

Named handlers for tools that need specific query construction (e.g. `get_position_history` building a GeoJSON LineString) live in `tool_dispatcher.py`, not in skill files. The skill file declares the signature; the platform provides the execution.

### 6.3 Agent Prompt Composition (`agent.py`)

```python
BASE_PROMPT = """
You are a maritime COP assistant. You help analysts query, edit, and understand
ship data through natural language.

Always resolve commands to one of: SELECT, QUERY, ADD, EDIT, DELETE, MERGE.
If the user's intent is ambiguous, ask exactly one clarifying question.
If a required parameter is missing, ask for it — do not guess.
If a conflict is detected during MERGE or EDIT, return a structured conflict
report rather than proceeding silently.

The user's current map selection context will be provided with each query.
Keep all spoken responses under 3 sentences. Be direct and precise.
"""

def build_system_prompt(skills: list[SkillManifest]) -> str:
    fragments = [BASE_PROMPT]
    for skill in skills:
        fragments.append(f"\n---\n# {skill.name} skill\n{skill.domain_prompt}")
    return "\n".join(fragments)
```

---

## 7. API Reference

```
POST /voice/transcribe          → { transcript, language }
POST /voice/speak               → audio/wav response body
POST /agent/query               → { reply, action, payload }

GET  /skills                    → [ SkillManifest summary ] (active skills)
GET  /ships                     → GeoJSON FeatureCollection (latest positions)
GET  /ships?bbox=...            → Filtered by viewport
GET  /ships/{mmsi}              → ShipIdentity + last position
GET  /ships/{mmsi}/history      → GeoJSON LineString (query param: hours)
GET  /ships/{mmsi}/destinations → [ { destination, last_seen } ] (query param: limit)

POST   /positions               → { position_id }
PUT    /positions/{id}          → Updated Position
DELETE /positions/{id}          → { deleted: true }
POST   /positions/merge         → Merged Position | ConflictReport

# Optional analytics shape returned via /agent/query payload
payload.insight.result_preview  → Small tabular preview of SQL results
```

### Agent query request/response

```python
# Request body
{
  "transcript": str,
  "selection_context": {
    "mmsi": int | None,
    "name": str | None,
    "last_position": object | None
  },
  "conversation_memory": {
    "active_vessel": object | None,
    "last_question": str | None,
    "last_assistant_reply": str | None,
    "last_analytics_question": str | None,
    "last_analytics_summary": str | None,
    "last_destination": str | None,
    "last_action": str | None
  },
  "chat_history": [           # Last 6 turns maximum
    {
      "role": "user" | "assistant",
      "text": str,
      "timestamp": str        # ISO 8601
    }
  ]
}

# Response body
{
  "reply": str,               # Spoken/displayed response
  "action": str | None,       # SHOW_TRACK | SHOW_PANEL | SHOW_CONFLICT | SHOW_INSIGHT
  "payload": object | None    # Data needed to execute the action on frontend
}
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

### Error contract

```json
{
  "error_type": "not_found",
  "message": "Ship 316001234 was not found",
  "suggested_action": "Select another vessel or verify the MMSI"
}
```

---

## 8. Phased Implementation Plan

### Delivery rule

Complete each phase with the smallest working slice that satisfies its test criteria. Defer polish until the next phase unless required to keep the demo coherent. Prefer deterministic UI logic for obvious commands; reserve the LLM for ambiguous or conversational requests.

---

### Phase 1 — Static Map + Ship Data
**Goal**: Map renders ships from seed data. Click a ship, see its identity panel. No voice, no agent yet.

**MVP cut line**: ship markers render, selection works, core read APIs return stable shapes.

#### Tasks

1. **Generate seed data** (`data/generate_seed.py`) — 200 synthetic MMSIs, North Atlantic / Halifax approaches, 7 days at 10-minute intervals. Include one intentional duplicate timestamp per MMSI for Phase 4 conflict testing.

2. **Backend: FastAPI skeleton** — `GET /ships` returning latest position per MMSI as GeoJSON FeatureCollection, `GET /ships/{mmsi}` returning identity + last known position, `GET /ships/{mmsi}/history?hours=24` returning GeoJSON LineString plus ordered positions.

3. **Backend: stub skill loader** — parse `skills/ais_positions.md` at startup and log the manifest. No agent integration yet; the loader exists so the startup pattern is established from Phase 1.

4. **Frontend: MapLibre map** — initialize centred on Halifax approaches (lat 44.5, lon −63.5, zoom 6). Add GeoJSON source + circle layer for ship positions. On click: populate `ShipPanel` with identity from `GET /ships/{mmsi}`.

5. **Frontend: ShipPanel component** — display MMSI, name, flag, ship type, nav status, SOG, COG, last seen.

#### Phase 1 Test Criteria
- [ ] Map loads with ≥ 100 ship markers
- [ ] Clicking a marker populates ShipPanel without page reload
- [ ] `GET /ships/{mmsi}/history` returns ordered positions for any seeded MMSI
- [ ] DuckDB query for 24h history completes in < 500ms on seed dataset
- [ ] Skill loader parses `ais_positions.md` without error and logs the manifest

---

### Phase 2 — Track Visualization + Selection State
**Goal**: Selected ship shows 24h track as a line overlay. Multi-ship selection scaffolded.

**MVP cut line**: one selected ship, one rendered track, one stable `selectionContext`, one destinations read path.

#### Tasks

1. **Frontend: refactor selection into `useSelection`** — expose `selectedMMSI`, `select(mmsi)`, `deselect()`, and `selectionContext = { mmsi, name, lastPosition }`. Log `selectionContext` on every selection change.

2. **Backend: `GET /ships/{mmsi}/destinations`** — last N distinct `destination` values in recency order.

3. **Frontend: `TrackLayer` component** — on ship select, fetch `GET /ships/{mmsi}/history?hours=24` and render a stable `LineString` layer. Remove the old track immediately when selection changes or clears. Handle duplicate timestamps deterministically using backend ordering.

4. **Frontend: keep map lifecycle isolated** — create the map instance once. Manage ship data, track data, and selection highlighting through independent source/layer updates.

#### Phase 2 Test Criteria
- [ ] Selecting a ship renders a continuous 24h track line
- [ ] Track clears on deselect and updates when a different ship is selected with no stale layers
- [ ] `selectionContext` is logged on every selection
- [ ] `GET /ships/{mmsi}/destinations?limit=5` returns deduplicated destinations in recency order

---

### Phase 3 — Voice Input Pipeline
**Goal**: Mic button → Whisper transcription → text displayed in UI. No agent yet.

**MVP cut line**: browser mic capture, backend transcription, transcript display, visible states. TTS stubbed until Phase 4.

#### Tasks

1. **Backend: `POST /voice/transcribe`** — accepts `multipart/form-data` with `audio` field (WebM/Opus). Loads `faster-whisper` model (`small.en` on CPU). Returns `{ transcript, language, confidence }`. Use VAD enabled, deterministic temperature, maritime-oriented initial prompt.

```python
from faster_whisper import WhisperModel
model = WhisperModel("small.en", device="cpu", compute_type="int8")

def transcribe(audio_bytes: bytes) -> dict:
    segments, info = model.transcribe(audio_bytes)
    text = " ".join(s.text for s in segments).strip()
    return {"transcript": text, "language": info.language, "confidence": 0.0}
```

2. **Frontend: `VoiceButton` component** — push-to-talk via `pointerdown`/`pointerup`. Uses `MediaRecorder` with `audio/webm;codecs=opus`. Displays transcript in a chat-style rail below the map. Shows recording, uploading, transcribing, and error states.

3. **Frontend: `useVoice` hook** — manages `MediaRecorder` lifecycle only. Exposes `isRecording`, `isTranscribing`, `error`, `startRecording()`, `stopRecording()`, `cancelRecording()`. App.jsx owns `chatHistory`. Ignore empty or too-short recordings.

4. **Backend: `POST /voice/speak`** — Piper synthesis returning WAV. Configure binary path, model path, and config path from environment-backed settings. Default voice: `models/en_US-ryan-high.onnx`. Frontend requests synthesized audio and plays it directly.

#### Phase 3 Test Criteria
- [ ] Push-to-talk records audio and displays transcript at acceptable latency on `small.en` CPU
- [ ] Transcript rail shows timestamped history of utterances
- [ ] Permission denial and transcription failures produce visible errors
- [ ] Empty or cancelled recordings do not append transcript entries
- [ ] Whisper handles accented English and naval terminology adequately (manual QA)
- [ ] Audio capture works in both Chrome and Firefox
- [ ] Piper TTS can synthesize and play a short reply string

---

### Phase 4 — Agent Integration with Skill Dispatch
**Goal**: Voice transcript + selection context → agent (prompt composed from active skills) → tool dispatch → visual + voice response.

**MVP cut line**: selected-ship identity queries, 24h track requests, recent destinations, one conflict flow. Prove the skill-driven agent loop end to end.

#### Tasks

1. **Backend: wire skill loader into agent** — at startup, load all skills, build the composed system prompt, and register all tool signatures with the tool dispatcher. The agent must have no hardcoded domain knowledge.

2. **Backend: `POST /agent/query`** — receives transcript + selection context + conversation memory + last 6 chat turns. Calls the LLM with the composed system prompt and registered tool signatures. Dispatches tool calls through `tool_dispatcher.py`. Returns `{ reply, action, payload }`.

3. **Backend: tool handlers for `ais_positions` tools** — implement each tool as a named handler in `tool_dispatcher.py`, calling into `data/loader.py` for reads and the overlay store for writes. The skill file declares the signature; these handlers provide the execution.

4. **Frontend: wire agent into voice pipeline** — after transcription, POST to `/agent/query` with transcript + `selectionContext` + session `conversation_memory`. On response: append `reply` to chat rail, speak via TTS, dispatch `action` to map (`SHOW_TRACK`, `SHOW_PANEL`, `SHOW_CONFLICT`, `SHOW_INSIGHT`).

5. **Frontend: marker selection semantics** — clicking a vessel marker loads identity + last known position context only. Do not auto-fetch or auto-render a 24h track on selection. Tracks render only after an explicit command.

6. **Frontend: `ConflictPanel` component** — renders two conflicting records side-by-side. Buttons: **Keep Most Recent**, **Keep Other**, **Merge Manually**, **Cancel**. On resolution: POST to `/positions/merge` with user choice.

#### Conflict report shape

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
- [ ] Agent system prompt is composed from base prompt + `ais_positions.md` domain prompt at startup
- [ ] No domain-specific knowledge exists in `agent.py` — all COP grammar lives in the skill file
- [ ] "What is this vessel?" with a ship selected → ShipPanel populated, spoken summary
- [ ] "Show the last 24 hours" → track rendered on map
- [ ] "Show the last 5 destinations" → destinations listed in ShipPanel
- [ ] "Add a position here" without coordinates → agent asks for lat/lon
- [ ] Merging two positions with conflicting timestamps → ConflictPanel opens with both records
- [ ] Agent never silently fails — all errors produce a spoken response
- [ ] Tool dispatcher routes calls correctly with no domain logic in the dispatcher itself

---

### Phase 5 — Polish, SQL Analytics, and Extensibility Proof
**Goal**: Harden the demo path, add viewport filtering, prove the extensibility model with a second skill stub, and document the skill authoring contract.

**MVP cut line**: all 8 COP grammar commands verified, viewport filtering, analytics fallback working, second skill stub demonstrating drop-in extensibility.

#### Tasks

1. **Spatial filtering**: `GET /ships?bbox=minLon,minLat,maxLon,maxLat` — latest positions in viewport. Frontend fetches on map `moveend`, not during drag.

2. **Schema-registered SQL analytics** — route exploratory analytics questions through the deterministic router first, then fall back to text-to-SQL using the `## SQL views` section from the active skill. Show analytics summaries in ShipPanel; do not expose generated SQL in the operator UI.

3. **In-session follow-up context** — use last 6 chat turns + `conversation_memory` to resolve follow-ups like "When?", "How many?", "What was the max?" before building the SQL prompt.

4. **Error handling hardening** — all backend action paths return `{ error_type, message, suggested_action }`. Agent surfaces actionable voice prompt for every error type. Piper TTS failures degrade cleanly.

5. **Second skill stub** — create `skills/vessel_watchlist.md` as a stub (front matter + section headers, tool signatures declared but handlers not yet implemented) to demonstrate that a second skill can be dropped in, picked up by the loader, and registered without touching platform code.

6. **COP grammar coverage test** — run each command through the voice pipeline and verify the correct backend action path is called:
   - "Show me this ship" / "What is this vessel?"
   - "Show last 24 hours track"
   - "Show last 5 destinations"
   - "Add a position here"
   - "Edit this position"
   - "Delete this track"
   - "Merge these two tracks"

7. **Extension stubs** (code-complete but inactive):
   - `POST /ingest/ais` → placeholder for real-time AIS feed
   - `GET /alerts` → placeholder for geofence / anomaly alerting
   - Tauri-compatibility note in `main.py`: API layer is stateless, no browser APIs used

8. **Skill authoring guide** — add `SKILL_AUTHORING.md` at repo root documenting the four required sections, front matter schema, tool signature format, and the platform/skill boundary rule.

#### Phase 5 Test Criteria
- [ ] All 8 COP grammar commands invoke the correct tool via skill dispatch
- [ ] Viewport-filtered ship load < 200ms for typical zoom level
- [ ] Ad-hoc analytics questions fall back to schema-registered SQL without breaking deterministic commands
- [ ] In-session follow-up voice questions resolve against prior answers without page refresh
- [ ] Analytics summaries visible in ShipPanel; generated SQL not visible to operator
- [ ] `vessel_watchlist.md` stub picked up by loader and logged without errors
- [ ] Demo runs end-to-end: voice → agent → map update → spoken response, no manual intervention
- [ ] `SKILL_AUTHORING.md` exists and accurately describes the skill file contract

---

## 9. Agent COP Grammar

| User says | Normalized intent | Tool called |
|---|---|---|
| "Show me this ship" | SELECT | `get_ship_identity` |
| "What is this vessel?" | QUERY | `get_ship_identity` |
| "Show last 24 hours track" | QUERY | `get_position_history(hours=24)` |
| "Show last 5 destinations" | QUERY | `get_recent_destinations(limit=5)` |
| "Add a position here" | ADD | `add_position` |
| "Edit this position" | EDIT | `edit_position` |
| "Delete this track" | DELETE | `delete_position` (looped per position in track) |
| "Merge these two tracks" | MERGE | `merge_positions` repeated over candidate duplicates, or conflict report |

The grammar table lives here as documentation. The authoritative version for the agent is the `## Domain prompt` section of `skills/ais_positions.md`.

---

## 10. Conflict Resolution Protocol

**Trigger**: `merge_positions` returns `conflict_type` in response.

**Agent behaviour**:
1. Describe the conflict in one sentence (e.g. "These positions conflict on timestamp within 30 seconds of each other.")
2. Propose the default resolution (most recent wins)
3. Await user confirmation or override via `ConflictPanel`

**Frontend**: `ConflictPanel` renders both records with diff highlighting. Resolution posts to `POST /positions/merge` with `resolution: "keep_1" | "keep_2" | "manual"`.

**Semantic note**: voice commands may refer to "tracks" but merge is defined at the position level for this prototype.

---

## 11. Frontend State Ownership

- `App.jsx` owns high-level session state: `selectedMMSI`, `selectionContext`, `shipDetail`, `track`, `chatHistory`, `conversationMemory`, `conflictState`
- `useSelection` encapsulates selection updates and derives `selectionContext`
- `useVoice` encapsulates recording and transcription lifecycle; appends successful utterances into app-owned `chatHistory`
- `conversationMemory` is session-scoped only; cleared on page refresh; stores minimal structured context for follow-up voice references
- `Map.jsx` receives data and callbacks; must not become the source of truth for selected ship or track state
- `Map.jsx` reads active skill map layer declarations from `GET /skills` on startup and registers those layers; no layer IDs are hardcoded in the frontend
- Marker selection updates vessel context without implicitly loading history; tracks render only through explicit actions
- `ConflictPanel` is controlled by app state and renders from a structured conflict payload only

---

## 12. Non-Goals (Prototype Scope)

- No authentication or authorization
- No real-time AIS streaming (seed data only)
- No production database (DuckDB file-mode only)
- No multi-user sessions
- No mobile-optimized layout
- No full COP UI complexity (no AOR management, no OPORD integration)
- No hot-reload of skill files — restart required to pick up new or changed skills

---

## 13. Known Weak Spots to Watch

- **Whisper latency**: `small.en` on CPU improves quality but may add latency. If it misses the interaction target, consider `base.en`, `tiny.en`, or GPU acceleration.
- **Piper runtime availability**: Piper requires a local binary and model files. Startup must surface missing-path errors clearly.
- **DuckDB write contention**: DuckDB file-mode allows one writer. ADD/EDIT/DELETE ops must be serialized server-side. Use a simple asyncio lock around write operations.
- **MapLibre + React**: use `useRef` for the map instance; never re-render the map container div.
- **Map layer lifecycle**: create the MapLibre instance exactly once. Manage ship data, track data, and selection highlighting through independent source/layer updates.
- **Browser mic permissions**: HTTPS required in production. `localhost` is exempted for dev.
- **Agent context window**: pass only the last 6 turns of chat history to avoid token bloat.
- **Duplicate timestamps**: seeded duplicates are for conflict testing. Phase 2 track rendering uses deterministic ordering only; visual conflict handling belongs to Phase 4.
- **Text-to-SQL safety**: constrain generation to approved views, strict validation, and execution limits before touching DuckDB.
- **Ambiguous joined columns**: generated SQL can fail with DuckDB binder errors if joined relations share columns like `lat` or `timestamp`. The skill's SQL views section must require aliases and fully qualified references in multi-relation queries.
- **Skill prompt accumulation**: each active skill appends a domain prompt fragment to the system prompt. With many skills, the prompt grows. Keep domain prompt fragments concise; the base prompt is not a dumping ground.
- **Skill map layer ID collisions**: two skills declaring the same layer ID will cause a runtime error. The skill loader must validate uniqueness at startup.
- **Prompt portability**: keep skill files provider-agnostic. The same domain prompt fragment must work across OpenAI, Ollama, Anthropic, or a local model.
- **Frontend layer registration**: `Map.jsx` must not hardcode layer IDs. It reads them from `GET /skills` at startup. A skill stub with no handler must not crash the frontend if its layer is registered but empty.

---

## 14. Testing Strategy

- **Backend**: `pytest` for API route coverage, skill loader parsing, tool dispatcher routing, and data-layer queries against generated seed data
- **Skill loader tests**: assert that `ais_positions.md` parses to a valid manifest, that tool signatures match the expected table, and that the domain prompt fragment is non-empty
- **Frontend**: component smoke tests plus one interaction test for ship selection and one for transcript rail updates
- **Manual QA**: browser mic permissions, transcription quality, TTS behaviour, and voice-to-map interaction loop
- **Agent verification**: for COP grammar coverage, assert both returned action shape and invoked tool name where feasible
- **Extensibility test**: drop `vessel_watchlist.md` stub into `skills/`, restart, and assert the loader picks it up without errors and the agent system prompt contains the stub's domain prompt fragment

---

## 15. Dev Workflow

- Generate seed data before starting either app surface
- Backend: install with `uv`, run FastAPI locally. Skill loader runs at startup — check logs for manifest parse results.
- Frontend: install with `pnpm`, run the Vite dev server. Configure backend base URL in one place.
- Keep startup commands documented in `README.md` once scaffolding exists.
- To add a new data domain: write the skill file, restart the backend, verify the manifest in logs, test a voice command against the new domain.

---

## 16. Definition of Done (Full Prototype)

A complete demonstration session must show, without human intervention between steps:

1. Map loads with ship markers from seed data
2. Analyst clicks a ship → ShipPanel populates with identity data
3. Analyst says "Show last 24 hours" → track renders on map, spoken confirmation
4. Analyst says "Show last 5 destinations" → destinations listed, spoken
5. Analyst says "Merge these two tracks" on a seeded conflict pair → ConflictPanel opens, spoken explanation, analyst clicks **Keep Most Recent** → panel closes, track updates
6. Analyst says "What is this vessel?" on a different ship with nothing selected → agent asks which ship, analyst answers by clicking → ShipPanel updates
7. Analyst asks an exploratory analytics question (e.g. "How many vessels entered Halifax today?") → agent falls back to SQL analytics, result summarized in ShipPanel, spoken reply
8. Operator drops a second skill file into `skills/` and restarts → new domain visible in agent behaviour, no platform code changed
