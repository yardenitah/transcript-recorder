import asyncio
import os
import logging
import boto3
import json
import time

# ✅ Import the NEW builder
from agora_token_builder import RtcTokenBuilder2

logger = logging.getLogger(__name__)

# Constants
LIFECYCLE_LIMIT = int(os.getenv("LIFECYCLE_LIMIT_SECONDS", 600))
LAMBDA_FUNCTION_NAME = os.getenv("AWS_LAMBDA_FUNCTION_NAME")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")


async def lifecycle_manager(channel_name, current_uid, agora_manager):
    """
    Waits for X seconds, then spawns a replacement bot (Lambda) and kills the current one.
    """
    logger.info(f"⏰ Timer started. Handoff in {LIFECYCLE_LIMIT}s.")

    # 1. Wait for the lifecycle limit
    await asyncio.sleep(LIFECYCLE_LIMIT)

    logger.info("⏰ Time is up! Starting Handoff Sequence...")

    try:
        # 2. Prepare Config for the New Bot
        APP_ID = os.getenv("AGORA_APP_ID")
        APP_CERT = os.getenv("AGORA_APP_CERTIFICATE")

        # --- DEBUG LOGS ---
        logger.info(f"🕵️ [Handoff] Checking Environment Variables:")
        logger.info(f"   - AGORA_APP_ID exists? {bool(APP_ID)}")
        logger.info(f"   - AGORA_APP_CERTIFICATE exists? {bool(APP_CERT)}")
        logger.info(f"   - Current UID: {current_uid} (Type: {type(current_uid)})")

        if not APP_ID or not APP_CERT:
            logger.error("❌ CRITICAL: AGORA Credentials missing from Environment!")
            return

        # Generate a new UID (increment by 1)
        try:
            new_uid_int = int(current_uid) + 1
            logger.info(f"🔢 [Handoff] Calculated New UID: {new_uid_int}")
        except Exception as e:
            logger.warning(f"⚠️ [Handoff] Could not increment UID ({e}). Using random int.")
            new_uid_int = int(time.time()) % 10000

        # ✅ Generate Token using RtcTokenBuilder2 (Protocol 007)
        expiration_time_in_seconds = 3600

        logger.info("⚙️ [Handoff] Calling RtcTokenBuilder2...")
        try:
            new_token = RtcTokenBuilder2.build_token_with_uid(
                APP_ID,
                APP_CERT,
                channel_name,
                new_uid_int,  # Must be INT
                1,  # Role Publisher
                expiration_time_in_seconds
            )
            logger.info(f"✅ [Handoff] Token Received! (Starts with: {new_token[:10]}...)")
            logger.info(f"🔑 FULL TOKEN: {new_token}")

        except Exception as build_err:
            logger.error(f"❌ [Handoff] Token Builder CRASHED: {build_err}")
            return  # Stop here if token failed

        # 3. Invoke AWS Lambda
        logger.info("☁️ [Handoff] Preparing AWS Boto3 Client...")
        client = boto3.client('lambda', region_name=AWS_REGION)

        payload = {
            "channel_name": channel_name,
            "uid": str(new_uid_int),
            "token": new_token,
            "is_handoff": True
        }

        logger.info(f"📞 [Handoff] Invoking Lambda: {LAMBDA_FUNCTION_NAME}")

        # Note: This might still fail with AccessDenied in Docker, but we want to see it try.
        response = client.invoke(
            FunctionName=LAMBDA_FUNCTION_NAME,
            InvocationType='Event',
            Payload=json.dumps(payload)
        )

        logger.info(f"✅ [Handoff] Invoke Status Code: {response['StatusCode']}")

    except Exception as e:
        logger.error(f"❌ [Handoff] General Error: {e}")

    finally:
        logger.info("👋 [Handoff] Process complete. Old bot retiring in 5s...")
        await asyncio.sleep(5)
        agora_manager.stop_connection()