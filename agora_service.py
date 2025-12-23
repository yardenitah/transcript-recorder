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
        config.enable_audio_device = 0  # Headless - Must be 0 to prevent crash
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
        logger.info("✅ [Manager] Service Initialized")

    def start_connection(self, channel_name: str, uid: str, token: str) -> bool:
        logger.info(f"🔹 [Manager] Connecting: {channel_name} / {uid}")

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
            self.connection = self.agora_service.create_rtc_connection(
                con_config, pub_config
            )
            logger.debug("✅ [Manager] Connection Created")

            # 3. Audio Observer Setup
            self.audio_observer = PcmAudioObserver(save_to_file=False)

            # MASK 12 = Mixed(4) + BeforeMixing(8)
            # This listens to BOTH streams to ensure we catch audio
            mask = 12
            logger.debug(f"🔹 [Manager] Registering Observer MASK={mask}")
            ret_observer = self.connection.register_audio_frame_observer(self.audio_observer, mask, 0)

            if ret_observer < 0:
                logger.error(f"❌ [Manager] Register failed: {ret_observer}")
                return False
            else:
                logger.info(f"✅ [Manager] Observer Registered (Mask {mask})")

            # 4. Audio Params
            try:
                local_user = self.connection.get_local_user()

                # --- CRITICAL FIX: Order is (Channels, SampleRate) ---
                # Setting this for BeforeMixing (Mask 8)
                local_user.set_playback_audio_frame_before_mixing_parameters(1, 16000)

                # Setting this for Mixed (Mask 4)
                # Order: (SampleRate, Channels, SamplesPerCall)
                local_user.set_mixed_audio_frame_parameters(16000, 1, 160)

                local_user.subscribe_all_audio()
                logger.info("✅ [Manager] Params Set (1ch 16k)")

            except Exception as e:
                logger.warning(f"⚠️ [Manager] Params Warning: {e}")

            # 5. Connect
            ret = self.connection.connect(token, channel_name, uid)
            if ret < 0:
                logger.error(f"❌ Connect failed: {ret}")
                return False

            logger.info("🚀 [Manager] Connection Initiated!")
            return True

        except Exception as e:
            logger.error(f"❌ [Manager] Error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def stop_connection(self) -> None:
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