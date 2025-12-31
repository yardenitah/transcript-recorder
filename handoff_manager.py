import asyncio
import os
import logging
import boto3
import json
import time

# Import our custom token builder script
from agora_token_builder import build_token_with_uid

logger = logging.getLogger(__name__)

# Constants
LIFECYCLE_LIMIT = int(os.getenv("LIFECYCLE_LIMIT_SECONDS", 600))
LAMBDA_FUNCTION_NAME = os.getenv("AWS_LAMBDA_FUNCTION_NAME")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")


def validate_token(token):
    """
    Sanity check for the generated token.
    """
    if not token or not isinstance(token, str):
        return False, "Token is empty or not a string"
    if len(token) < 50:
        return False, "Token is suspiciously short"
    return True, "OK"


async def lifecycle_manager(channel_name, current_uid, agora_manager):
    """
    Waits for X seconds, then spawns a replacement bot (Lambda) and kills the current one.
    """
    logger.info(f"⏰ Timer started. Handoff in {LIFECYCLE_LIMIT}s.")

    # 1. Wait for the lifecycle limit
    await asyncio.sleep(LIFECYCLE_LIMIT)

    logger.info("⏰ Time is up! Spawning new bot...")

    try:
        # 2. Prepare Config for the New Bot
        APP_ID = os.getenv("AGORA_APP_ID")
        APP_CERT = os.getenv("AGORA_APP_CERTIFICATE")

        # --- CHECK 1: Validate Credentials ---
        if not APP_ID:
            logger.error("❌ CRITICAL: AGORA_APP_ID is missing!")
            return
        if not APP_CERT:
            logger.error("❌ CRITICAL: AGORA_APP_CERTIFICATE is missing! Token generation will fail.")
            return

        logger.info(f"🔐 Credentials found. AppID: {APP_ID[:5]}... | Cert: {APP_CERT[:5]}...")

        # Generate a new UID (increment by 1 so they don't collide)
        try:
            new_uid = str(int(current_uid) + 1)
        except:
            new_uid = str(int(time.time()) % 10000)

        logger.info(f"🔢 Generating token for New UID: {new_uid}")

        # ✅ Generate a fresh Token using our custom builder
        expiration_time_in_seconds = 3600
        current_timestamp = int(time.time())
        privilege_expired_ts = current_timestamp + expiration_time_in_seconds

        # Role 1 = Host/Publisher
        new_token = build_token_with_uid(APP_ID, APP_CERT, channel_name, new_uid, 1, privilege_expired_ts)

        # --- CHECK 2: Validate Token Structure ---
        is_valid, reason = validate_token(new_token)
        if not is_valid:
            logger.error(f"❌ Token Generation FAILED: {reason}")
            return

        # --- CHECK 3: Print Token for manual verification ---
        logger.info(f"✅ Token Generated Successfully!")
        logger.info(f"🔑 NEW TOKEN: {new_token}")

        # 3. Invoke AWS Lambda
        client = boto3.client('lambda', region_name=AWS_REGION)

        payload = {
            "channel_name": channel_name,
            "uid": new_uid,
            "token": new_token,  # The newly generated token
            "is_handoff": True  # Mark this as a relief bot
        }

        logger.info(f"📞 Calling self: {LAMBDA_FUNCTION_NAME} with UID {new_uid}")

        # This will fail locally (in Docker) but verify the logic works
        response = client.invoke(
            FunctionName=LAMBDA_FUNCTION_NAME,
            InvocationType='Event',  # Async execution (don't wait for result)
            Payload=json.dumps(payload)
        )

        logger.info(f"✅ Spawn command sent! Status: {response['StatusCode']}")

    except Exception as e:
        logger.error(f"❌ Error in handoff process: {e}")

    finally:
        # 4. Graceful Shutdown
        logger.info("👋 Old bot retiring...")
        await asyncio.sleep(5)
        agora_manager.stop_connection()