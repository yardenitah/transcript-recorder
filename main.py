import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from typing import Dict

load_dotenv()

# Global mapping from Agora UID to see better  speaker label
uid_to_speaker: Dict[int, str] = {}
next_speaker_index: int = 1

def get_or_assign_speaker(uid: int) -> str:
    """
    Map each new UID to a label like 'speaker1', 'speaker2', etc.
    """
    global next_speaker_index

    if uid not in uid_to_speaker:
        uid_to_speaker[uid] = f"speaker{next_speaker_index}"
        next_speaker_index += 1

    return uid_to_speaker[uid]


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/agora-config")
def get_agora_config():
    return {
        "app_id": settings.AGORA_APP_ID,
        "channel": settings.AGORA_CHANNEL_NAME,
        "recorder_uid": settings.AGORA_RECORDER_UID,
        "token": settings.AGORA_TOKEN,
    }


@app.websocket("/audio-stream")
async def audio_stream(websocket: WebSocket):
    await websocket.accept()
    print("✅ Audio WebSocket connected")

    client_uid = None
    client_speaker_label = None

    try:
        while True:
            message = await websocket.receive()

            msg_type = message.get("type")

            # Handle client disconnect cleanly
            if msg_type == "websocket.disconnect":
                print(f"❌ WebSocket disconnect received (UID={client_uid}, speaker={client_speaker_label})")
                break

            # Text messages: meta info (like Agora UID)
            if "text" in message and message["text"] is not None:
                try:
                    meta = json.loads(message["text"])
                    if meta.get("type") == "meta":
                        client_uid = meta.get("uid")
                        client_speaker_label = get_or_assign_speaker(client_uid)
                        print(f"ℹ️ Got meta from client: UID={client_uid}, label={client_speaker_label}")
                except json.JSONDecodeError:
                    print("⚠️ Received non-JSON text message")

            # Binary messages: raw audio bytes
            if "bytes" in message and message["bytes"] is not None:
                audio_bytes = message["bytes"]

                if client_uid is not None:
                    speaker_label = client_speaker_label or uid_to_speaker.get(client_uid, "unknown")
                    print(
                        f"🎧 {speaker_label} | UID={client_uid} | Received audio chunk of {len(audio_bytes)} bytes"
                    )
                else:
                    print(f"🎧 UID=(unknown) | Received audio chunk of {len(audio_bytes)} bytes")

    except RuntimeError as e:
        print(f"⚠️ RuntimeError on receive (UID={client_uid}, speaker={client_speaker_label}): {e}")
    except WebSocketDisconnect:
        print(f"❌ Audio WebSocket disconnected (UID={client_uid}, speaker={client_speaker_label})")
    finally:
        print(f"🔚 WebSocket handler finished for UID={client_uid}, speaker={client_speaker_label}")