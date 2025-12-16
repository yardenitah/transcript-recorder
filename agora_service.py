import logging
from typing import Optional

from agora.rtc.agora_base import RtcConnectionPublishConfig

from agora.rtc.agora_service import AgoraService, AgoraServiceConfig
from agora.rtc.rtc_connection import RTCConnConfig
from audio_observer import PcmAudioObserver

logger = logging.getLogger(__name__)


class AgoraManager:
    def __init__(self) -> None:
        self.agora_service: Optional[AgoraService] = None
        self.connection = None
        self.audio_observer: Optional[PcmAudioObserver] = None

    def initialize(self, app_id: str) -> None:
        config = AgoraServiceConfig()
        config.enable_audio_processor = 1
        config.enable_audio_device = 0
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
        logger.info(f"Agora Service initialized with APP_ID={app_id}")

    def start_connection(self, channel_name: str, uid: str, token: str) -> bool:
        if not self.agora_service:
            logger.error("Agora Service not initialized!")
            return False

        try:
            # 1. Config
            con_config = RTCConnConfig()
            con_config.auto_subscribe_audio = 1
            con_config.auto_subscribe_video = 0
            con_config.client_role_type = 1
            con_config.channel_profile = 1

            # 2. Create Connection
            pub_config = RtcConnectionPublishConfig()  # type: ignore
            self.connection = self.agora_service.create_rtc_connection(
                con_config, pub_config
            )
            logger.info("RTC connection created successfully")

            # 3. Register Observer
            self.audio_observer = PcmAudioObserver(save_to_file=False)
            ret_observer = self.connection.register_audio_frame_observer(self.audio_observer, 0, 0)

            if ret_observer < 0:
                logger.error(f"Failed to register audio observer, code={ret_observer}")
                return False

            # --- TENTATIVE FIX: Set Audio Parameters via Local User ---
            try:
                # בדרך כלל הפונקציה נמצאת בתוך get_local_user()
                local_user = self.connection.get_local_user()
                local_user.set_playback_audio_frame_parameters(16000, 1, 0, 320)
                logger.info("✅ Audio parameters set via get_local_user()!")
            except AttributeError:
                logger.warning("⚠️ set_playback_audio_frame_parameters not found on LocalUser.")

                # --- DEBUG: הדפסת כל הפונקציות הקיימות כדי שלא ננחש ---
                logger.info("🔍 DEBUG: Available methods on 'connection':")
                logger.info(dir(self.connection))
            except Exception as e:
                logger.warning(f"⚠️ Failed to set audio parameters: {e}")
            # -----------------------------------------------------------

            # 4. Connect
            logger.info(f"Connecting to Agora: channel={channel_name}, uid={uid}")
            ret = self.connection.connect(token, channel_name, uid)

            if ret < 0:
                logger.error(f"Agora connect() failed with code {ret}")
                return False

            logger.info("Agora connection established successfully")
            return True

        except Exception as e:
            logger.error(f"Error starting Agora connection: {e}")
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
            logger.info("Disconnected from Agora")