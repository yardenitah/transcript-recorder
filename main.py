import logging
import os
import traceback
import asyncio

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agora_service import AgoraManager
from mangum import Mangum

# Import the lifecycle logic from the separate file
from handoff_manager import lifecycle_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# --- CORS Configuration ---
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
    is_handoff: bool = False

# --- Environment Configuration ---
APP_ID = os.getenv("AGORA_APP_ID")
if not APP_ID:
    APP_ID = "5deec9e3974849299a1e0a770fcca06d"
    logger.warning("AGORA_APP_ID not found, using hardcoded default.")

# Initialize the Agora Service
agora_manager = AgoraManager()
agora_manager.initialize(APP_ID)


# --- Endpoints ---

@app.get("/agora-config")
def get_agora_config():
    return {
        "app_id": APP_ID,
        "channel": os.getenv("AGORA_CHANNEL_NAME", "test123"),
        "token": os.getenv("AGORA_TOKEN", ""),
        "recorder_uid": os.getenv("AGORA_RECORDER_UID", "555")
    }


@app.post("/start")
async def start_bot(request: ConnectionRequest, background_tasks: BackgroundTasks):
    try:
        # 1. Start the lifecycle timer in the background
        # We pass 'agora_manager' so the timer can stop it later
        asyncio.create_task(lifecycle_manager(request.channel_name, request.uid, agora_manager))

        # 2. Connect to Agora
        success = agora_manager.start_connection(
            channel_name=request.channel_name,
            uid=request.uid,
            token=request.token,
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to connect to Agora")

        # 3. If we are the "Relief" bot (Handoff) - verify audio reception before sending OK
        if request.is_handoff:
            logger.info("⏳ [Handoff] Verifying audio stream...")
            for _ in range(15):  # Try for 15 seconds
                stats = agora_manager.get_status()
                # If audio frames are received -> Success
                if stats.get('audio', {}).get('frame_count', 0) > 5:
                    logger.info("✅ [Handoff] Audio verified! Sending OK.")
                    return {"status": "connected", "verified": True}
                await asyncio.sleep(1)

            # If no audio detected -> Fail (so the old instance won't disconnect)
            logger.warning("⚠️ [Handoff] Audio verification failed.")
            raise HTTPException(status_code=500, detail="Audio verification failed")

        return {"status": "connected", "channel": request.channel_name, "uid": request.uid}

    except Exception as e:
        logger.error(f"Error in /start: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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