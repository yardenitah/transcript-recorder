import logging
from typing import Optional

# Import necessary Agora classes
from agora.rtc.agora_base import RtcConnectionPublishConfig, AudioSubscriptionOptions
from agora.rtc.agora_service import AgoraService, AgoraServiceConfig
from agora.rtc.rtc_connection import RTCConnConfig
from audio_observer import PcmAudioObserver

# Set logging to DEBUG to see everything
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class AgoraManager:
    def __init__(self) -> None:
        self.agora_service: Optional[AgoraService] = None
        self.connection = None
        self.audio_observer: Optional[PcmAudioObserver] = None

    def initialize(self, app_id: str) -> None:
        logger.debug(f"🔹 [Manager] Initializing Engine with APP_ID={app_id}...")

        config = AgoraServiceConfig()
        config.enable_audio_processor = 1

        # --- CRITICAL FIX: TRICK THE SERVER ---
        # We enable the audio device even on a headless server.
        # This forces the SDK to initialize the audio pipeline.
        config.enable_audio_device = 1

        config.enable_video = 0
        config.context = 0

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
        logger.info("✅ [Manager] Service Initialized (Audio Device ENABLED)")

    def start_connection(self, channel_name: str, uid: str, token: str) -> bool:
        logger.info(f"🔹 [Manager] Starting Connection: {channel_name} / {uid}")

        if not self.agora_service:
            logger.error("❌ [Manager] Service not initialized!")
            return False

        try:
            # 1. Config
            con_config = RTCConnConfig()
            con_config.auto_subscribe_audio = 1
            con_config.auto_subscribe_video = 0
            con_config.client_role_type = 1  # BROADCASTER
            con_config.channel_profile = 1  # LIVE_BROADCASTING

            # 2. Create Connection
            pub_config = RtcConnectionPublishConfig()
            self.connection = self.agora_service.create_rtc_connection(
                con_config, pub_config
            )
            logger.debug("✅ [Manager] Connection Created")

            # 3. Register Audio Observer
            logger.debug("🔹 [Manager] Registering Audio Observer...")
            self.audio_observer = PcmAudioObserver(save_to_file=False)

            # Mask 4 = MIXED AUDIO. This is the standard pipeline output.
            ret_observer = self.connection.register_audio_frame_observer(self.audio_observer, 4, 0)

            if ret_observer < 0:
                logger.error(f"❌ [Manager] Register failed: {ret_observer}")
                return False
            else:
                logger.info("✅ [Manager] Observer Registered (Mask 4 - MIXED)")

            # 4. Set Audio Parameters
            try:
                logger.debug("🔹 [Manager] Setting Audio Params...")
                local_user = self.connection.get_local_user()

                # Set Mixed Audio parameters (16k, Mono, 10ms)
                local_user.set_mixed_audio_frame_parameters(16000, 1, 160)

                # Also subscribe explicitly
                local_user.subscribe_all_audio()
                logger.info("✅ [Manager] Audio Params Set (Mixed Only)")

            except Exception as e:
                logger.warning(f"⚠️ [Manager] Audio Params Warning: {e}")

            # 5. Connect
            logger.info(f"🔄 [Manager] Connecting to channel...")
            ret = self.connection.connect(token, channel_name, uid)

            if ret < 0:
                logger.error(f"❌ [Manager] Connect failed: {ret}")
                return False

            logger.info("🚀 [Manager] Connection Initiated!")
            return True

        except Exception as e:
            logger.error(f"❌ [Manager] Critical Error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def stop_connection(self) -> None:
        logger.info("🔹 [Manager] Stopping...")
        if self.connection:
            if self.audio_observer:
                try:
                    self.connection.unregister_audio_frame_observer(self.audio_observer)
                except Exception:
                    pass
                self.audio_observer.stop()

            self.connection.disconnect()
            self.connection = None
            logger.info("🛑 [Manager] Disconnected")

            # BB 