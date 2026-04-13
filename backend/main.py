from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.agent import run_agent_query
from backend.data.loader import (
    DataNotLoadedError,
    get_latest_ship_features,
    get_recent_destinations,
    get_ship_detail,
    get_ship_history,
)
from backend.tools.crud import (
    add_position,
    delete_position,
    edit_position,
    merge_positions,
)
from backend.voice.transcribe import TranscriptionError, transcribe_audio
from backend.voice.speak import SpeechSynthesisError, synthesize_speech


app = FastAPI(title="Maritime COP Prototype", version="0.1.0")
# Tauri compatibility note: the API remains stateless and does not depend on browser APIs.


class AgentQueryRequest(BaseModel):
    transcript: str
    selection_context: dict | None = None
    chat_history: list[dict] = Field(default_factory=list)
    conversation_memory: dict | None = None


class MergeRequest(BaseModel):
    position_id_1: str
    position_id_2: str
    resolution: str | None = None


class PositionCreateRequest(BaseModel):
    mmsi: int
    lat: float
    lon: float
    timestamp: str


class PositionUpdateRequest(BaseModel):
    updates: dict


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def error_response(
    error_type: str, message: str, suggested_action: str
) -> dict[str, str]:
    return {
        "error_type": error_type,
        "message": message,
        "suggested_action": suggested_action,
    }


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/voice/transcribe")
async def voice_transcribe(audio: UploadFile = File(...)) -> dict:
    content_type = audio.content_type or ""
    if "audio/" not in content_type and content_type != "application/octet-stream":
        raise HTTPException(
            status_code=400,
            detail=error_response(
                "invalid_audio",
                "Expected an audio upload in multipart/form-data.",
                "Record a short audio clip and try again.",
            ),
        )

    try:
        audio_bytes = await audio.read()
        suffix = ".webm"
        if audio.filename and "." in audio.filename:
            suffix = f".{audio.filename.rsplit('.', 1)[-1]}"
        return transcribe_audio(audio_bytes, suffix=suffix)
    except TranscriptionError as exc:
        raise HTTPException(
            status_code=422,
            detail=error_response(
                "transcription_failed",
                str(exc),
                "Try a shorter recording or repeat the utterance clearly.",
            ),
        ) from exc


@app.post("/voice/speak")
async def voice_speak(request: SpeechRequest) -> Response:
    try:
        audio_bytes = synthesize_speech(request.text)
        return Response(content=audio_bytes, media_type="audio/wav")
    except SpeechSynthesisError as exc:
        raise HTTPException(
            status_code=503,
            detail=error_response(
                "speech_synthesis_failed",
                str(exc),
                "Install Piper locally and configure the Piper model path before retrying.",
            ),
        ) from exc


@app.post("/agent/query")
async def agent_query(request: AgentQueryRequest) -> dict:
    try:
        return run_agent_query(
            request.transcript,
            request.selection_context,
            request.chat_history[-6:],
            request.conversation_memory,
        )
    except DataNotLoadedError as exc:
        raise HTTPException(
            status_code=503,
            detail=error_response(
                "seed_data_missing",
                str(exc),
                "Generate the synthetic dataset before starting the API.",
            ),
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive API contract
        raise HTTPException(
            status_code=500,
            detail=error_response(
                "agent_error",
                "The maritime assistant failed to complete that request.",
                "Try the request again or reselect the vessel.",
            ),
        ) from exc


@app.get("/ships")
async def list_ships(bbox: str | None = Query(default=None)) -> dict:
    try:
        return get_latest_ship_features(parse_bbox(bbox) if bbox else None)
    except DataNotLoadedError as exc:
        raise HTTPException(
            status_code=503,
            detail=error_response(
                "seed_data_missing",
                str(exc),
                "Generate the synthetic dataset before starting the API.",
            ),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=error_response(
                "invalid_bbox",
                str(exc),
                "Use bbox=minLon,minLat,maxLon,maxLat with valid coordinates.",
            ),
        ) from exc


@app.get("/ships/{mmsi}")
async def ship_detail(mmsi: int) -> dict:
    try:
        detail = get_ship_detail(mmsi)
    except DataNotLoadedError as exc:
        raise HTTPException(
            status_code=503,
            detail=error_response(
                "seed_data_missing",
                str(exc),
                "Generate the synthetic dataset before starting the API.",
            ),
        ) from exc

    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=error_response(
                "not_found",
                f"Ship {mmsi} was not found",
                "Select another vessel or verify the MMSI.",
            ),
        )

    return detail


@app.get("/ships/{mmsi}/history")
async def ship_history(mmsi: int, hours: int = 24) -> dict:
    try:
        history = get_ship_history(mmsi, hours)
    except DataNotLoadedError as exc:
        raise HTTPException(
            status_code=503,
            detail=error_response(
                "seed_data_missing",
                str(exc),
                "Generate the synthetic dataset before starting the API.",
            ),
        ) from exc

    if history is None:
        raise HTTPException(
            status_code=404,
            detail=error_response(
                "not_found",
                f"History for ship {mmsi} was not found",
                "Select another vessel or verify the MMSI.",
            ),
        )

    return history


@app.get("/ships/{mmsi}/destinations")
async def ship_destinations(mmsi: int, limit: int = 5) -> list[dict]:
    try:
        destinations = get_recent_destinations(mmsi, limit)
    except DataNotLoadedError as exc:
        raise HTTPException(
            status_code=503,
            detail=error_response(
                "seed_data_missing",
                str(exc),
                "Generate the synthetic dataset before starting the API.",
            ),
        ) from exc

    if not destinations:
        raise HTTPException(
            status_code=404,
            detail=error_response(
                "not_found",
                f"Destinations for ship {mmsi} were not found",
                "Select another vessel or verify the MMSI.",
            ),
        )

    return destinations


@app.post("/positions")
async def create_position(request: PositionCreateRequest) -> dict:
    position = add_position(request.mmsi, request.lat, request.lon, request.timestamp)
    return {"position_id": position["position_id"]}


@app.put("/positions/{position_id}")
async def update_position(position_id: str, request: PositionUpdateRequest) -> dict:
    position = edit_position(position_id, request.updates)
    if position is None:
        raise HTTPException(
            status_code=404,
            detail=error_response(
                "not_found",
                f"Position {position_id} was not found.",
                "Refresh the track and try the edit again.",
            ),
        )
    return position


@app.delete("/positions/{position_id}")
async def remove_position(position_id: str) -> dict:
    deleted = delete_position(position_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=error_response(
                "not_found",
                f"Position {position_id} was not found.",
                "Refresh the track and try the delete again.",
            ),
        )
    return {"deleted": True}


@app.post("/positions/merge")
async def merge_ship_positions(request: MergeRequest) -> dict:
    result = merge_positions(
        request.position_id_1,
        request.position_id_2,
        request.resolution,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=error_response(
                "not_found",
                "One or both positions could not be found.",
                "Refresh the track and try the merge again.",
            ),
        )
    return result


@app.post("/ingest/ais")
async def ingest_ais_stub() -> dict:
    return {
        "status": "inactive",
        "message": "Real-time AIS ingest is not enabled in this prototype.",
    }


@app.get("/alerts")
async def alerts_stub() -> dict:
    return {
        "alerts": [],
        "status": "inactive",
        "message": "Alerting is reserved for a later prototype phase.",
    }


def parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    parts = [part.strip() for part in bbox.split(",")]
    if len(parts) != 4:
        raise ValueError("Bounding box must have four comma-separated values.")

    min_lon, min_lat, max_lon, max_lat = (float(part) for part in parts)
    if min_lon >= max_lon or min_lat >= max_lat:
        raise ValueError("Bounding box min values must be less than max values.")
    if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
        raise ValueError("Bounding box longitude values must be between -180 and 180.")
    if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        raise ValueError("Bounding box latitude values must be between -90 and 90.")

    return min_lon, min_lat, max_lon, max_lat
