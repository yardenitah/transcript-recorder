import asyncio
import os
import logging
import boto3
import json
import time

# ✅ Import the RAW AccessToken class
from agora_token_builder import AccessToken

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

        if not APP_ID or not APP_CERT:
            logger.error("❌ CRITICAL: AGORA Credentials missing from Environment!")
            return

        # Generate a new UID (increment by 1)
        try:
            new_uid_int = int(current_uid) + 1
            logger.info(f"🔢 [Handoff] Calculated New UID: {new_uid_int}")
        except Exception as e:
            logger.warning(f"⚠️ [Handoff] Could not increment UID. Using random int.")
            new_uid_int = int(time.time()) % 10000

        # ✅ CRITICAL FIX: Match C# Behavior Exactly
        # C#: new AccessToken(..., uid.ToString())
        # Python: AccessToken(..., str(uid))
        uid_as_string = str(new_uid_int)

        logger.info(f"⚙️ [Handoff] Building LOW-LEVEL Token for UID STRING: '{uid_as_string}'")

        # Instantiate the low-level builder directly
        token_builder = AccessToken(APP_ID, APP_CERT, channel_name, uid_as_string)

        # Add Privileges manually (Join + Publish Audio/Video/Data)
        expiration_time_in_seconds = 3600
        current_timestamp = int(time.time())
        privilege_expired_ts = current_timestamp + expiration_time_in_seconds

        token_builder.addPrivilege(AccessToken.kJoinChannel, privilege_expired_ts)
        token_builder.addPrivilege(AccessToken.kPublishAudioStream, privilege_expired_ts)
        token_builder.addPrivilege(AccessToken.kPublishVideoStream, privilege_expired_ts)
        token_builder.addPrivilege(AccessToken.kPublishDataStream, privilege_expired_ts)

        # Build the final string
        new_token = token_builder.build()

        logger.info(f"✅ [Handoff] Token Generated! Length: {len(new_token)}")
        logger.info(f"🔑 FULL TOKEN: {new_token}")

        # 3. Invoke AWS Lambda
        client = boto3.client('lambda', region_name=AWS_REGION)

        payload = {
            "channel_name": channel_name,
            # We send it as string in payload, but the receiver (main.py) handles types usually
            "uid": uid_as_string,
            "token": new_token,
            "is_handoff": True
        }

        logger.info(f"📞 [Handoff] Invoking Lambda: {LAMBDA_FUNCTION_NAME}")

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