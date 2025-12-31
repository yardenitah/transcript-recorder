import logging, os, time, json, asyncio, boto3

from agora_token_builder import build_token_with_uid

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

    logger.info("⏰ Time is up! Spawning new bot...")

    try:
        # 2. Prepare Config for the New Bot
        APP_ID = os.getenv("AGORA_APP_ID")
        APP_CERT = os.getenv("AGORA_APP_CERTIFICATE")

        if not APP_ID or not APP_CERT:
            logger.error("❌ Missing Agora Config (App ID or Cert). Cannot spawn replacement.")
            return

        # Generate a new UID (increment by 1 so they don't collide)
        # If current is '100', new will be '101'
        try:
            new_uid = str(int(current_uid) + 1)
        except:
            new_uid = str(int(time.time()) % 10000)

        # ✅ Generate a fresh Token using our custom builder
        expiration_time_in_seconds = 3600
        current_timestamp = int(time.time())
        privilege_expired_ts = current_timestamp + expiration_time_in_seconds

        # Role 1 = Host/Publisher
        new_token = build_token_with_uid(APP_ID, APP_CERT, channel_name, new_uid, 1, privilege_expired_ts)

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
        # Optional: Wait a few seconds for overlap before cutting
        await asyncio.sleep(5)
        agora_manager.stop_connection()