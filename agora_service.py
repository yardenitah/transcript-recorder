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
        logger.debug("🔹 [Manager] __init__ called")
        self.agora_service: Optional[AgoraService] = None
        self.connection = None
        self.audio_observer: Optional[PcmAudioObserver] = None

    def initialize(self, app_id: str) -> None:
        logger.debug(f"🔹 [Manager] initialize() called with APP_ID={app_id}")

        config = AgoraServiceConfig()
        config.enable_audio_processor = 1
        config.enable_audio_device = 0  # Headless for server
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
        logger.info("✅ [Manager] Agora Service initialized successfully")

    def start_connection(self, channel_name: str, uid: str, token: str) -> bool:
        logger.debug(f"🔹 [Manager] start_connection() called. Channel={channel_name}, UID={uid}")

        if not self.agora_service:
            logger.error("❌ [Manager] Agora Service is None!")
            return False

        try:
            # 1. Configuration
            logger.debug("🔹 [Manager] Configuring RTC Connection...")
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
            logger.debug("✅ [Manager] Connection object created")

            # 3. Register Audio Observer
            logger.debug("🔹 [Manager] Creating PcmAudioObserver...")
            self.audio_observer = PcmAudioObserver(save_to_file=False)

            # Mask 8 = BEFORE_MIXING (Raw remote streams)
            logger.debug("🔹 [Manager] Registering observer with mask 8 (BEFORE_MIXING)")
            ret_observer = self.connection.register_audio_frame_observer(self.audio_observer, 8, 0)

            if ret_observer < 0:
                logger.error(f"❌ [Manager] Failed to register observer! Code={ret_observer}")
                return False
            else:
                logger.info("✅ [Manager] Observer registered successfully (Mask: 8)")

            # 4. Set Audio Parameters
            try:
                logger.debug("🔹 [Manager] Setting Audio Parameters...")
                local_user = self.connection.get_local_user()

                # Enable BeforeMixing parameters
                logger.debug("🔹 [Manager] Calling set_playback_audio_frame_before_mixing_parameters(16000, 1)")
                local_user.set_playback_audio_frame_before_mixing_parameters(16000, 1)

                # Set others just in case
                local_user.set_playback_audio_frame_parameters(16000, 1, 1, 160)
                local_user.set_mixed_audio_frame_parameters(16000, 1, 160)

                logger.debug("🔹 [Manager] Subscribing to all audio...")
                local_user.subscribe_all_audio()

                logger.info("✅ [Manager] All Audio parameters set.")

            except Exception as e:
                logger.warning(f"⚠️ [Manager] Exception setting params: {e}")

            # 5. Connect
            logger.info(f"🔄 [Manager] Connecting to channel '{channel_name}'...")
            ret = self.connection.connect(token, channel_name, uid)

            if ret < 0:
                logger.error(f"❌ [Manager] Connect failed! Code={ret}")
                return False

            logger.info("🚀 [Manager] Connection initiated. Waiting for data...")
            return True

        except Exception as e:
            logger.error(f"❌ [Manager] Critical Exception: {e}")
            import traceback
            traceback.print_exc()
            return False

    def stop_connection(self) -> None:
        if self.connection:
            if self.audio_observer:
                try:
                    logger.debug("🔹 [Manager] Unregistering observer...")
                    self.connection.unregister_audio_frame_observer(self.audio_observer)
                except Exception as e:
                    logger.error(f"❌ [Manager] Error unregistering: {e}")

                self.audio_observer.stop()

            self.connection.disconnect()
            self.connection = None
