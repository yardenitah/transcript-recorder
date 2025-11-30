from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    AGORA_APP_ID: str
    AGORA_APP_CERTIFICATE: str
    AGORA_CHANNEL_NAME: str
    AGORA_TOKEN: str
    AGORA_RECORDER_UID: str

    class Config:
        env_file = ".env"


settings = Settings()

app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # allow all origins (for dev)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ====== 1) Models for session join (similar to the C# flow) ======

class SessionJoinDetails(BaseModel):
    app_id: str
    local_uid: int
    token: str
    room_id: str


class SessionConfig(BaseModel):
    room_id: str
    local_uid: int
    remote_uid: int


# ====== 2) New endpoint: /session/join ======

@app.post("/session/join", response_model=SessionJoinDetails)
def join_session(cfg: SessionConfig):
    """
    Simulate the C# CreateSessionAndStartRecording behavior:
    Returns the Agora parameters needed by the client to join a room.
    For now this is a simplified version: no DB and no real recording start.
    """
    return SessionJoinDetails(
        app_id=settings.AGORA_APP_ID,
        local_uid=cfg.local_uid,
        token=settings.AGORA_TOKEN,
        room_id=cfg.room_id,
    )


# ====== 3) Old endpoint: /agora-config (still here for quick testing) ======

@app.get("/agora-config")
def get_agora_config():
    """
    Simple endpoint to expose Agora configuration to the frontend.
    This is only for local testing. In production, use a proper token-generation flow.
    """
    return {
        "app_id": settings.AGORA_APP_ID,
        "channel": settings.AGORA_CHANNEL_NAME,
        "recorder_uid": settings.AGORA_RECORDER_UID,
        "token": settings.AGORA_TOKEN,
    }


# ====== 4) WebSocket for raw audio frames ======

@app.websocket("/audio-stream")
async def audio_stream(websocket: WebSocket):
    await websocket.accept()
    print("✅ Audio WebSocket connected")
    try:
        # First message from client is a small JSON meta with the UID
        meta = await websocket.receive_text()
        print(f"ℹ️ Got meta from client: {meta}")

        # Next messages are raw audio bytes
        while True:
            data = await websocket.receive_bytes()
            print(f"🎧 Received audio chunk of {len(data)} bytes")
    except WebSocketDisconnect:
        print("❌ Audio WebSocket disconnected")