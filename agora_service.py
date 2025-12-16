# agora_service.py
import logging
from typing import Optional

from agora.rtc.agora_base import RtcConnectionPublishConfig

from agora.rtc.agora_service import AgoraService, AgoraServiceConfig
from agora.rtc.rtc_connection import RTCConnConfig
from audio_observer import PcmAudioObserver

# Try to import AgoraPublishConfig (exists only in SDK 1.x).
# In SDK 2.x this class does not exist, so we fallback to None.
logger = logging.getLogger(__name__)


class AgoraManager:
    def __init__(self) -> None:
        self.agora_service: Optional[AgoraService] = None
        self.connection = None
        self.audio_observer: Optional[PcmAudioObserver] = None

    def initialize(self, app_id: str) -> None:
        """
        Initialize Agora service with the given APP ID.
        """
        config = AgoraServiceConfig()
        config.enable_audio_processor = 1
        config.enable_audio_device = 0
        config.enable_video = 0
        config.context = 0

        # Different SDK versions use different field names, so we try both.
        # One of them will be ignored if it does not exist.
        try:
            config.app_id = app_id  # SDK 1.x style
        except AttributeError:
            pass

        try:
            config.appid = app_id  # SDK 2.x style
        except AttributeError:
            pass

        self.agora_service = AgoraService()
        self.agora_service.initialize(config)
        logger.info(f"Agora Service initialized with APP_ID={app_id}")

    def start_connection(self, channel_name: str, uid: str, token: str) -> bool:
        """
        Create an RTC connection, register the audio observer, and connect to the channel.
        """
        if not self.agora_service:
            logger.error("Agora Service not initialized!")
            return False

        try:
            # 1. RTC connection config
            con_config = RTCConnConfig()
            con_config.auto_subscribe_audio = 1
            con_config.auto_subscribe_video = 0
            con_config.client_role_type = 1   # BROADCASTER
            con_config.channel_profile = 1    # LIVE_BROADCASTING

            # 2. Create connection.
            #    - SDK 1.x: create_rtc_connection(config, publish_config)
            #    - SDK 2.x: create_rtc_connection(config)
            # Likely SDK 1.x
            pub_config = RtcConnectionPublishConfig()  # type: ignore
            self.connection = self.agora_service.create_rtc_connection(
                con_config, pub_config
            )
            logger.info("RTC connection created using publish_config (SDK 1.x style)")

            # 3. Register audio observer
            self.audio_observer = PcmAudioObserver(save_to_file=False)
            ret_observer = self.connection.register_audio_frame_observer(self.audio_observer)

            if ret_observer < 0:
                logger.error(f"Failed to register audio observer, code={ret_observer}")
                return False

            # 4. Connect to Agora
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
        """
        Disconnect and clean up the Agora connection.
        """
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
