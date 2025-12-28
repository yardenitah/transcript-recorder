import logging, os, traceback, time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agora_service import AgoraManager

from mangum import Mangum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# --- CORS Configuration: Allows browser client access ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionRequest(BaseModel):
    channel_name: str
    uid: str
    token: str
    is_handoff: bool = False  # New flag for Task 3


# Load Agora App ID from environment
APP_ID = os.getenv("AGORA_APP_ID")
if not APP_ID:
    APP_ID = "5deec9e3974849299a1e0a770fcca06d"
    logger.warning("AGORA_APP_ID not found, using hardcoded default.")

# Initialize the Agora Service
agora_manager = AgoraManager()
agora_manager.initialize(APP_ID)


# --- Configuration Endpoint for the Browser Client ---
@app.get("/agora-config")
def get_agora_config():
    return {
        "app_id": APP_ID,
        "channel": os.getenv("AGORA_CHANNEL_NAME", "test123"),
        "token": os.getenv("AGORA_TOKEN", ""),
        "recorder_uid": os.getenv("AGORA_RECORDER_UID", "555")
    }


@app.post("/start")
def start_bot(request: ConnectionRequest):
    """
    Start an RTC connection to a specific Agora channel.
    """
    try:
        success = agora_manager.start_connection( channel_name=request.channel_name, uid=request.uid, token=request.token,)

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to connect to Agora (check logs)",
            )

        if request.is_handoff:
            logger.info("⏳ [Handshake] Waiting for audio verification...")
            for i in range(20): # Check for audio frames for up to 20 seconds
                stats = agora_manager.get_status()
                audio_stats = stats.get('audio', {})
                # If we received more than 10 frames, audio is working
                if audio_stats and audio_stats.get('frame_count', 0) > 10:
                    logger.info("✅ [Handshake] Audio verified! Sending OK.")
                    return {"status": "connected", "handoff_verified": True}

                time.sleep(1)

            logger.warning("⚠️ [Handshake] Audio not detected, but proceeding to keep session alive.")

        return {
            "status": "connected",
            "channel": request.channel_name,
            "uid": request.uid,
        }

    except HTTPException:
        raise
    except Exception as e:
        stack = traceback.format_exc()
        logger.error("CRITICAL ERROR in /start:\n%s", stack)
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "trace": stack,
            },
        )


@app.post("/stop")
def stop_bot():
    """ Stop the current RTC connection. """
    agora_manager.stop_connection()
    return {"status": "disconnected"}


@app.get("/status")
def status():
    """ Return connection + audio observer health info. """
    return agora_manager.get_status()


handler = Mangum(app)