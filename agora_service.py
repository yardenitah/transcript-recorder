import logging
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
from audio_observer import PcmAudioObserver

# Logger setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ConnLogger(IRtcConnectionObserver):
    """
    Observer class to track real-time connection events and user presence.
    """

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
        logger.info(f"👤 [Conn] User left: uid={uid}")
        self.users.discard(uid)
        self.published.discard(uid)

    def on_connection_state_changed(self, *args):
        # Triggered when connection state changes (connecting, connected, failed, etc.)
        logger.info(f"🔌 [Conn] State changed")

    def get_status(self):
        """Returns collected connection status for the API."""
        return {
            "users": list(self.users),
            "published": list(self.published),
        }


class AgoraManager:
    def __init__(self) -> None:
        self.agora_service: Optional[AgoraService] = None
        self.connection = None
        self.audio_observer: Optional[PcmAudioObserver] = None
        self.connection_observer: Optional["ConnLogger"] = None

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

            # 3. Register Connection Observer
            self.connection_observer = ConnLogger()
            try:
                self.connection.register_observer(self.connection_observer)
            except Exception as e:
                logger.warning(f"⚠️ [Manager] Could not register connection observer: {e}")

            # 4. Audio Observer Setup
            self.audio_observer = PcmAudioObserver(save_to_file=False)
            mask = 12  # Mixed (4) + BeforeMixing (8)
            self.connection.register_audio_frame_observer(self.audio_observer, mask, 0)

            # 5. Audio Parameters Setup
            local_user = self.connection.get_local_user()

            # Set PCM parameters for 16kHz mono (Required for Soniox)
            # Agora AI confirmed this IS the correct way to set format for callbacks
            local_user.set_playback_audio_frame_before_mixing_parameters(1, 16000)
            local_user.set_mixed_audio_frame_parameters(16000, 1, 160)

            # 6. Audio Subscription (Corrected based on Agora AI)
            # subscribe_all_audio does NOT take arguments in v2.4.1
            ret_sub = local_user.subscribe_all_audio()

            if ret_sub < 0:
                logger.error(f"❌ [Manager] subscribe_all_audio failed: {ret_sub}")

            # 7. Final Connect call
            ret = self.connection.connect(token, channel_name, uid)
            if ret < 0:
                logger.error(f"❌ [Manager] Connect failed with code: {ret}")
                return False

            logger.info(f"🚀 [Manager] Connection Initiated (Code: {ret})")
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
