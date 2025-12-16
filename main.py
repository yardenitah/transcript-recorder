# main.py
import logging
import os
import traceback

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agora_service import AgoraManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()


class ConnectionRequest(BaseModel):
    channel_name: str
    uid: str
    token: str


# Load Agora App ID from environment (with fallback for local testing)
APP_ID = os.getenv("AGORA_APP_ID")
if not APP_ID:
    APP_ID = "5deec9e3974849299a1e0a770fcca06d"
    logger.warning(
        "AGORA_APP_ID environment variable not found, using hardcoded APP_ID. "
        "Do NOT use this in production."
    )

# Create and initialize Agora service once on process startup
agora_manager = AgoraManager()
agora_manager.initialize(APP_ID)


@app.post("/start")
def start_bot(request: ConnectionRequest):
    """
    Start an RTC connection to a specific Agora channel.
    """
    try:
        success = agora_manager.start_connection(
            channel_name=request.channel_name,
            uid=request.uid,
            token=request.token,
        )

        if not success:
            # start_connection returned False – log and return 500
            raise HTTPException(
                status_code=500,
                detail="Failed to connect to Agora (check logs)",
            )

        return {
            "status": "connected",
            "channel": request.channel_name,
            "uid": request.uid,
        }

    except HTTPException:
        # Re-raise HTTPException as-is so FastAPI handles it correctly
        raise
    except Exception as e:
        # Any unexpected error – include traceback for debugging
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
    """
    Stop the current RTC connection and release resources.
    """
    agora_manager.stop_connection()
    return {"status": "disconnected"}
