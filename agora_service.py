import logging
from typing import Optional

# Import necessary Agora classes
from agora.rtc.agora_base import RtcConnectionPublishConfig, AudioSubscriptionOptions
from agora.rtc.agora_service import AgoraService, AgoraServiceConfig
from agora.rtc.rtc_connection import RTCConnConfig
from audio_observer import PcmAudioObserver

# Set up logging
logger = logging.getLogger(__name__)


class AgoraManager:
    def __init__(self) -> None:
        self.agora_service: Optional[AgoraService] = None
        self.connection = None
        self.audio_observer: Optional[PcmAudioObserver] = None

    def initialize(self, app_id: str) -> None:
        """
        Initializes the Agora Service engine.
        """
        config = AgoraServiceConfig()
        config.enable_audio_processor = 1
        config.enable_audio_device = 0  # Disable audio device (server mode)
        config.enable_video = 0
        config.context = 0

        # Handle different SDK versions regarding app_id naming
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
        logger.info(f"✅ Agora Service initialized with APP_ID={app_id}")

    def start_connection(self, channel_name: str, uid: str, token: str) -> bool:
        """
        Creates the RTC connection, registers the observer, and joins the channel.
        """
        if not self.agora_service:
            logger.error("❌ Agora Service not initialized!")
            return False

        try:
            # 1. Configuration
            con_config = RTCConnConfig()
            con_config.auto_subscribe_audio = 1
            con_config.auto_subscribe_video = 0
            # Set to BROADCASTER (1) to ensure active participation permissions on server
            con_config.client_role_type = 1
            con_config.channel_profile = 1  # LIVE_BROADCASTING

            # 2. Create Connection
            pub_config = RtcConnectionPublishConfig()
            self.connection = self.agora_service.create_rtc_connection(
                con_config, pub_config
            )
            logger.info("✅ RTC connection object created")

            # 3. Register Audio Observer
            self.audio_observer = PcmAudioObserver(save_to_file=False)

            # Mask 15 covers: Playback, Record, Mixed, and BeforeMixing frames
            ret_observer = self.connection.register_audio_frame_observer(self.audio_observer, 15, 0)

            if ret_observer < 0:
                logger.error(f"❌ Failed to register audio observer, code={ret_observer}")
                return False
            else:
                logger.info("✅ Audio Frame Observer registered successfully")

            # 4. Set Audio Parameters (CRITICAL STEP)
            try:
                local_user = self.connection.get_local_user()

                # Configure expected audio format: 16000Hz, Mono, PCM
                # Parameters: (sample_rate, channels, mode, samples_per_call)
                local_user.set_playback_audio_frame_parameters(16000, 1, 0, 160)
                local_user.set_mixed_audio_frame_parameters(16000, 1, 160)
                local_user.set_playback_audio_frame_before_mixing_parameters(16000, 1)

                # Explicitly subscribe to audio
                local_user.subscribe_all_audio()

                logger.info("✅ Audio parameters set (16k, Mono) and subscribed to all audio")

            except Exception as e:
                logger.warning(f"⚠️ Warning while setting audio parameters: {e}")

            # 5. Connect to Channel
            logger.info(f"🔄 Connecting to Agora channel: {channel_name}, uid: {uid}...")
            ret = self.connection.connect(token, channel_name, uid)

            if ret < 0:
                logger.error(f"❌ Agora connect() failed with code {ret}")
                return False

            logger.info("🚀 Agora connection established successfully!")
            return True

        except Exception as e:
            logger.error(f"❌ Critical error starting Agora connection: {e}")
            import traceback
            traceback.print_exc()
            return False

    def stop_connection(self) -> None:
        """
        Disconnects and cleans up resources.
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
            logger.info("🛑 Disconnected from Agora")