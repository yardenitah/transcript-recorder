import logging
from typing import Optional

from agora.rtc.agora_base import RtcConnectionPublishConfig, AudioSubscriptionOptions
from agora.rtc.agora_service import AgoraService, AgoraServiceConfig
from agora.rtc.rtc_connection import RTCConnConfig
from audio_observer import PcmAudioObserver

# DEBUG level
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class AgoraManager:
    def __init__(self) -> None:
        self.agora_service: Optional[AgoraService] = None
        self.connection = None
        self.audio_observer: Optional[PcmAudioObserver] = None

    def initialize(self, app_id: str) -> None:
        logger.debug(f"🔹 [Manager] Init Engine APP_ID={app_id}")

        config = AgoraServiceConfig()
        config.enable_audio_processor = 1
        config.enable_audio_device = 0  # Headless
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
        logger.info("✅ [Manager] Service Initialized (Headless)")

    def start_connection(self, channel_name: str, uid: str, token: str) -> bool:
        logger.info(f"🔹 [Manager] Connecting: Channel='{channel_name}' / UID='{uid}'/ Token='{token}'")

        if not self.agora_service:
            logger.error("❌ [Manager] Service not initialized!")
            return False

        try:
            # 1. Config
            con_config = RTCConnConfig()
            con_config.auto_subscribe_audio = 1
            con_config.auto_subscribe_video = 0
            con_config.client_role_type = 1
            con_config.channel_profile = 1

            # 2. Create Connection
            pub_config = RtcConnectionPublishConfig()
            logger.debug("🔹 [Manager] Creating RTC Connection object...")
            self.connection = self.agora_service.create_rtc_connection(con_config, pub_config)

            logger.debug("✅ [Manager] Connection Object Created")

            # 3. Audio Observer Setup
            logger.debug("🔹 [Manager] Initializing Audio Observer...")
            self.audio_observer = PcmAudioObserver(save_to_file=False)

            # MASK 12
            mask = 12
            logger.debug(f"🔹 [Manager] Registering Observer with MASK={mask} (Mixed | BeforeMixing)")
            ret_observer = self.connection.register_audio_frame_observer(self.audio_observer, mask, 0)

            if ret_observer < 0:
                logger.error(f"❌ [Manager] Register failed with code: {ret_observer}")
                return False
            else:
                logger.info(f"✅ [Manager] Observer Registered Successfully (Mask {mask})")

            # 4. Audio Params
            try:
                local_user = self.connection.get_local_user()

                logger.debug("🔹 [Manager] Setting BeforeMixing Params (1ch, 16000Hz)...")
                local_user.set_playback_audio_frame_before_mixing_parameters(1, 16000)

                logger.debug("🔹 [Manager] Setting Mixed Params (16000Hz, 1ch)...")
                local_user.set_mixed_audio_frame_parameters(16000, 1, 160)

                logger.debug("🔹 [Manager] Subscribing to all audio...")
                local_user.subscribe_all_audio()
                logger.info("✅ [Manager] All Audio Params Set")

            except Exception as e:
                logger.warning(f"⚠️ [Manager] Params Setting Warning: {e}")

            # 5. Connect
            logger.info(f"🔄 [Manager] Connecting to Agora network...")
            ret = self.connection.connect(token, channel_name, uid)

            if ret < 0:
                logger.error(f"❌ [Manager] Connect failed with code: {ret}")
                return False

            logger.info("🚀 [Manager] Connection Initiated! Waiting for callbacks...")
            return True

        except Exception as e:
            logger.error(f"❌ [Manager] Critical Exception: {e}")
            import traceback
            traceback.print_exc()
            return False

    def stop_connection(self) -> None:
        logger.info("🟠 [Manager] Start stop connection...")
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