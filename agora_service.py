import logging, inspect, threading, time, os, requests
from typing import Optional
# Try to import the correct Observer class name for version 2.4.1 (IRTC...)
# with a fallback to the older name (IRtc...)
try:
    from agora.rtc.rtc_connection_observer import IRTCConnectionObserver as IRtcConnectionObserver
except ImportError:
    from agora.rtc.rtc_connection_observer import IRtcConnectionObserver

from agora.rtc.agora_base import RtcConnectionPublishConfig, AudioSubscriptionOptions
from agora.rtc.agora_service import AgoraService, AgoraServiceConfig
from agora.rtc.rtc_connection import RTCConnConfig
from agora.rtc.local_user_observer import IRTCLocalUserObserver
from agora_token_builder import RtcTokenBuilder, Role_Subscriber
from audio_observer import PcmAudioObserver

# Logger setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Enable SDK's internal logging for audio frame observer
sdk_logger = logging.getLogger('agora.rtc._ctypes_handle._audio_frame_observer')
sdk_logger.setLevel(logging.DEBUG)
sdk_logger.addHandler(logging.StreamHandler())


class AgoraManager:
    def __init__(self) -> None:
        self.agora_service: Optional[AgoraService] = None
        self.connection = None
        self.audio_observer: Optional[PcmAudioObserver] = None
        self.connection_observer: Optional["ConnLogger"] = None
        self.local_user_observer: Optional["LocalUserLogger"] = None

    def initialize(self, app_id: str) -> None:
        logger.debug(f"🔹 [Manager] Init Engine APP_ID={app_id}")
        config = AgoraServiceConfig()
        config.enable_audio_processor = 1
        config.enable_audio_device = 0  # Headless mode (no physical sound card)
        config.enable_video = 0
        config.context = 0
        # Handle different field names for app_id in different SDK versions
        try:
            config.app_id = app_id
        except AttributeError:
            pass
        try:
            config.appid = app_id
        except AttributeError:
            pass

        self.agora_service = AgoraService()
        self.agora_service.initialize(config)
        logger.info("✅ [Manager] Service Initialized (Headless Mode)")

    def start_connection(self, channel_name: str, uid: str, token: str) -> bool:
        logger.info(f"🔹 [Manager] Connecting: Channel='{channel_name}' / UID='{uid}'")
        logger.info("[DEBUG] IRtcConnectionObserver callbacks: %s",[m for m in dir(IRtcConnectionObserver) if m.startswith("on_")])

        if not self.agora_service:
            logger.error("❌ [Manager] Service not initialized!")
            return False

        try:
            # 1. Connection configuration
            con_config = RTCConnConfig()
            con_config.auto_subscribe_audio = 1
            con_config.client_role_type = 1  # Broadcaster

            # Use Live Broadcasting profile (1)
            con_config.channel_profile = 1

            # 2. Create Connection
            pub_config = RtcConnectionPublishConfig()
            self.connection = self.agora_service.create_rtc_connection(con_config, pub_config)
            logger.debug("✅ [Manager] Connection Object Created")
            logger.info(f"connect signature: {inspect.signature(self.connection.connect)}")
            try:
                logger.debug("[Manager][SAFETY BELT] step one")
                # 3. Register Connection Observer
                self.connection_observer = ConnLogger()
                logger.debug("[Manager][SAFETY BELT] step two")
                try:
                    self.connection.register_observer(self.connection_observer)
                    logger.debug("[Manager][SAFETY BELT] step three")
                except Exception as e:
                    logger.warning(f"⚠️ [Manager] Could not register connection observer: {e}")

                # 3b. Register Local User Observer (for audio subscription events)
                logger.debug("[Manager][SAFETY BELT] step four")
                self.local_user_observer = LocalUserLogger()
                logger.debug("[Manager][SAFETY BELT] step five")
                try:
                    ret_local_obs = self.connection.register_local_user_observer(self.local_user_observer)
                    logger.info(f"[DEBUG] register_local_user_observer ret={ret_local_obs}")
                except Exception as e:
                    logger.warning(f"⚠️ [Manager] Could not register local user observer: {e}")
            except Exception as e:
                logger.error(f"❌ [Manager][SAFETY BELT] Oh my oh my!!! 😱 {e}")

            # 4. Get local user first
            local_user = self.connection.get_local_user()
            logger.info(f"[DEBUG] local_user obtained: {local_user}")

            # 5. Set PCM parameters BEFORE registering observer (order matters!)
            # Set PCM parameters for 16kHz mono (Required for Soniox)
            r1 = local_user.set_playback_audio_frame_before_mixing_parameters(1, 16000)
            r2 = local_user.set_mixed_audio_frame_parameters(16000, 1, 160)
            logger.info(f"[DEBUG] set_before_mixing ret={r1}, set_mixed ret={r2}")

            if r1 < 0 or r2 < 0:
                logger.error(f"❌ [Manager] Audio parameters setup failed: r1={r1}, r2={r2}")

            # 6. Audio Observer Setup (AFTER parameters)
            # self.audio_observer = PcmAudioObserver(save_to_file=False)
            self.audio_observer = PcmAudioObserver(save_to_file=False, separate_streams=True)
            logger.info(f"[DEBUG] PcmAudioObserver created: {self.audio_observer}")


            try:
                # Register observer: params are (observer, enable_vad, vad_configure)
                # SDK v2.4.0 automatically enables all callbacks - no mask needed
                ret_obs = self.connection.register_audio_frame_observer(self.audio_observer, 0, None)
                logger.info(f"[DEBUG] register_audio_frame_observer ret={ret_obs}")

                if ret_obs < 0:
                    logger.error(f"❌ [Manager] Audio observer registration FAILED with code: {ret_obs}")
                    return False
                else:
                    logger.info(f"✅ [Manager] Audio observer registered successfully")
            except Exception as e:
                logger.error(f"[DEBUG] register_audio_frame_observer FAILED: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return False

            # 7. Audio Subscription (Corrected based on Agora AI)
            # subscribe_all_audio does NOT take arguments in v2.4.1
            ret_sub = local_user.subscribe_all_audio()
            logger.info(f"[DEBUG] subscribe_all_audio ret={ret_sub}")

            if ret_sub < 0:
                logger.error(f"❌ [Manager] subscribe_all_audio failed: {ret_sub}")
            else:
                logger.info(f"✅ [Manager] subscribe_all_audio succeeded")

            # 8. Final Connect call
            ret = self.connection.connect(token, channel_name, uid)
            if ret < 0:
                logger.error(f"❌ [Manager] Connect failed with code: {ret}")
                return False

            logger.info(f"🚀 [Manager] Connection Initiated (Code: {ret})")
            logger.info(f"⚠️ [Manager] NOTE: Audio callbacks will only fire when REMOTE USERS publish audio!")
            self.start_handoff_timer(channel_name, uid) # start timer
            return True

        except Exception as e:
            logger.error(f"❌ [Manager] Critical Error during connection: {e}")
            return False

    def stop_connection(self) -> None:
        if self.connection:
            self.connection.disconnect()
            self.connection = None
            logger.info("🛑 [Manager] Disconnected")

    def get_status(self):
        """Aggregates all status info for the /status endpoint."""
        status = {"connected": self.connection is not None}
        if self.connection_observer:
            status["connection"] = self.connection_observer.get_status()
        if self.audio_observer:
            status["audio"] = self.audio_observer.get_status()
        return status

    def start_handoff_timer(self, channel_name: str, current_bot_uid: str):
        """ Starts a 10-minute timer. When time is up, triggers the next bot. """
        handoff_time = 600  # 10 minutes
        logger.info(f"⏱️ [Handoff] Timer started. Replacement in {handoff_time}s.")
        timer = threading.Timer(handoff_time, self._trigger_new_bot, args=[channel_name, current_bot_uid])
        timer.daemon = True
        timer.start()

    def _trigger_new_bot(self,channel_name: str, current_bot_uid: str):
        logger.warning("⚠️ [Handoff] Time is up! Calling next bot...")
        # Get configuration from Env Vars
        lambda_url = os.environ.get("TRANSCRIPT_LAMBDA_URL")
        app_id = os.environ.get("AGORA_APP_ID")
        app_cert = os.environ.get("AGORA_APP_CERTIFICATE")  # Must be set in Pulumi/Env

        if not lambda_url or not app_id or not app_cert:
            logger.error("❌ [Handoff] Missing Config (URL/AppID/Cert). Cannot spawn replacement!")
            return

        # 1. Calculate new UID (Increment by 1 to avoid collision)
        next_uid = str(int(current_bot_uid) + 1)

        # 2. Generate a valid Token for the new UID using App Certificate
        expiration_in_seconds = 3600 * 24
        current_timestamp = int(time.time())
        privilege_expired_ts = current_timestamp + expiration_in_seconds

        logger.info(f"🔑 Generating token for UID {next_uid}...")
        new_token = RtcTokenBuilder.buildTokenWithUid(
            app_id, app_cert, channel_name, int(next_uid), Role_Subscriber, privilege_expired_ts
        )

        # 3. Prepare payload for the new bot
        payload = { "channel_name": channel_name, "uid": next_uid, "token": new_token, "is_handoff": True}
        try:
            logger.info(f"📞 [Handoff] Dialing next bot at: {lambda_url}")
            # TASK 3 (Sender side): Wait up to 40s for the new bot to confirm it hears audio
            response = requests.post(lambda_url, json=payload, timeout=40)

            if response.status_code == 200:
                logger.info("✅ [Handoff] Success! Replacement is working. Shutting down.")
                self.stop_connection()
                time.sleep(2)
                os._exit(0)
            else:
                logger.error(f"❌ [Handoff] Replacement failed! Status: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ [Handoff] Failed to trigger replacement: {e}")




""" Observer class to track real-time connection events and user presence user joined or lest. 
 crate instances  in AgoraManager class"""
class ConnLogger(IRtcConnectionObserver):

    def __init__(self):
        super().__init__()
        self.users = set()
        self.published = set()
        self.state = None

    def on_user_joined(self, *args):
        # Handling dynamic arguments as different SDK versions send different params (uid, elapsed)
        uid = args[1] if len(args) > 1 else args[0]
        logger.info(f"👤 [Conn] User joined: uid={uid}")
        self.users.add(uid)

    def on_user_left(self, *args):
        uid = args[1] if len(args) > 1 else args[0]
        reason = args[2] if len(args) > 2 else "Unknown"
        logger.info(f"👤 [Conn] User left: uid={uid}, reason={reason}")
        if uid in self.users:
            self.users.remove(uid)

        self.users.discard(uid)
        self.published.discard(uid)

        if len(self.users) == 0:
            logger.warning("📉 All users left. Initiating graceful shutdown...")
            #TODO - no users in meeting so save tranmscript to DB an termin the process
            threading.Timer(3.0, lambda: os._exit(0)).start()

    def on_connection_state_changed(self, *args):
        # Triggered when connection state changes (connecting, connected, failed, etc.)
        logger.info(f"🔌 [Conn] State changed")

    def get_status(self):
        """Returns collected connection status for the API."""
        return {
            "users": list(self.users),
            "published": list(self.published),
        }


"""Observer for local user events - critical for audio subscription debugging."""
class LocalUserLogger(IRTCLocalUserObserver):
    def on_user_audio_track_subscribed(self, agora_local_user, user_id, agora_remote_audio_track):
        logger.info(f"🎵 [LocalUser] Audio track subscribed: user_id={user_id}, track={agora_remote_audio_track}")

    def on_audio_subscribe_state_changed(self, agora_local_user, channel, user_id, old_state, new_state, elapse_since_last_state):
        logger.info(f"🔄 [LocalUser] Audio subscribe state changed: user_id={user_id}, old={old_state}, new={new_state}")

    def on_first_remote_audio_frame(self, agora_local_user, user_id, elapsed):
        logger.info(f"🎤 [LocalUser] First remote audio frame: user_id={user_id}, elapsed={elapsed}ms")

    def on_first_remote_audio_decoded(self, agora_local_user, user_id, elapsed):
        logger.info(f"🔊 [LocalUser] First remote audio decoded: user_id={user_id}, elapsed={elapsed}ms")

    def on_user_audio_track_state_changed(self, agora_local_user, user_id, agora_remote_audio_track, state, reason, elapsed):
        logger.info(f"📡 [LocalUser] Audio track state changed: user_id={user_id}, state={state}, reason={reason}")
