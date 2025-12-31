
import logging, os, time, json, asyncio, boto3
# Try to import the Token Builder
try:
    from agora_token_builder import RtcTokenBuilder
except ImportError:
    logging.warning("⚠️ agora_token_builder not found! Handoff will fail.")

logger = logging.getLogger(__name__)

# --- Environment Configuration ---
APP_ID = os.getenv("AGORA_APP_ID")
APP_CERT = os.getenv("AGORA_APP_CERTIFICATE")
# Lifecycle limit: How long the Lambda runs before triggering a handoff (Default: 10 mins)
LIFECYCLE_LIMIT_SECONDS = int(os.getenv("LIFECYCLE_LIMIT_SECONDS", 600))


def create_api_gateway_event(body_dict):
    """
    Wraps the payload to simulate a standard API Gateway HTTP request for Mangum.
    Required because we invoke the Lambda directly using boto3.
    """
    return {
        "resource": "/start",
        "path": "/start",
        "httpMethod": "POST",
        "headers": {"Content-Type": "application/json"},
        "multiValueHeaders": {},
        "queryStringParameters": None,
        "body": json.dumps(body_dict),
        "isBase64Encoded": False
    }


async def lifecycle_manager(current_channel: str, current_uid: str, agora_manager):
    """
    Background task: Counts down time, then spawns a replacement Lambda instance.
    Accepts 'agora_manager' instance to stop the connection when handoff is complete.
    """
    logger.info(f"⏰ Timer started. Handoff in {LIFECYCLE_LIMIT_SECONDS}s.")

    # 1. Wait for the defined duration
    await asyncio.sleep(LIFECYCLE_LIMIT_SECONDS)

    logger.info("⏰ Time is up! Spawning new bot...")

    if not APP_ID or not APP_CERT:
        logger.error("❌ Missing Config (App ID or Certificate). Cannot spawn replacement.")
        return

    try:
        # 2. Prepare new identity (UID + 1) and new token
        next_uid = str(int(current_uid) + 1)
        token_expiration = int(time.time()) + 3600

        # Generate token locally (Fast & Reliable)
        new_token = RtcTokenBuilder.buildTokenWithUid(
            APP_ID, APP_CERT, current_channel, int(next_uid), 2, token_expiration
        )

        # 3. Prepare payload for the new Lambda instance
        payload = {
            "channel_name": current_channel,
            "uid": next_uid,
            "token": new_token,
            "is_handoff": True  # Critical flag: tells the new bot to verify audio
        }

        function_name = os.environ.get('AWS_LAMBDA_FUNCTION_NAME')

        # 4. Invoke the new Lambda and wait for response (RequestResponse)
        lambda_client = boto3.client('lambda')
        logger.info(f"📞 Calling self: {function_name}")

        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',  # Wait for the new instance to respond with OK
            Payload=json.dumps(create_api_gateway_event(payload))
        )

        # 5. If the new instance responded 200 (OK), we disconnect
        if response.get('StatusCode') == 200:
            logger.info("✅ Handoff success! Shutting down current instance.")
            agora_manager.stop_connection()  # Stop the Agora Engine
            await asyncio.sleep(2)  # Allow graceful disconnect
            os._exit(0)  # Terminate the process
        else:
            logger.error("⚠️ Handoff failed. Staying alive as backup.")

    except Exception as e:
        logger.error(f"❌ Error in handoff process: {e}")