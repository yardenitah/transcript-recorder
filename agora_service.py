import logging
from typing import Optional

from agora.rtc.agora_base import RtcConnectionPublishConfig, AudioSubscriptionOptions
from agora.rtc.agora_service import AgoraService, AgoraServiceConfig
from agora.rtc.rtc_connection import RTCConnConfig
from agora.rtc.rtc_connection_observer import IRtcConnectionObserver  # <--- Import added
from audio_observer import PcmAudioObserver

logger = logging.getLogger(__name__)


# --- New Class to Track Users ---
class MyConnectionObserver(IRtcConnectionObserver):
    def __init__(self):
        super().__init__()

    def on_user_joined(self, connection, uid, elapsed):
        # This log will show whenever a user joins the channel
        logger.info(f"👤 USER JOINED! UID: {uid}")

    def on_user_offline(self, connection, uid, reason):
        logger.info(f"👋 USER LEFT! UID: {uid}, Reason: {reason}")

    def on_connected(self, connection, info, reason):
        logger.info(f"🌐 Bot Connected to Channel! (Reason: {reason})")

    def on_disconnected(self, connection, info, reason):
        logger.info("❌ Bot Disconnected from Channel")


class AgoraManager:
    def __init__(self) -> None:
        self.agora_service: Optional[AgoraService] = None
        self.connection = None
        self.audio_observer: Optional[PcmAudioObserver] = None
        self.conn_observer: Optional[MyConnectionObserver] = None  # <--- Added

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
        logger.info(f"✅ Agora Service initialized with APP_ID={app_id}")

    def start_connection(self, channel_name: str, uid: str, token: str) -> bool:
        if not self.agora_service:
            logger.error("❌ Agora Service not initialized!")
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

            # --- REGISTER USER OBSERVER ---
            self.conn_observer = MyConnectionObserver()
            self.connection.register_observer(self.conn_observer)

            logger.info("✅ RTC connection object created & Observer registered")

            # 3. Register Audio Observer
            self.audio_observer = PcmAudioObserver(save_to_file=False)
            ret_observer = self.connection.register_audio_frame_observer(self.audio_observer, 15, 0)

            if ret_observer < 0:
                logger.error(f"❌ Failed to register audio observer, code={ret_observer}")
                return False
            else:
                logger.info("✅ Audio Frame Observer registered successfully")

            # 4. Set Audio Parameters
            try:
                local_user = self.connection.get_local_user()
                local_user.set_playback_audio_frame_parameters(16000, 1, 0, 160)
                local_user.set_mixed_audio_frame_parameters(16000, 1, 160)
                local_user.set_playback_audio_frame_before_mixing_parameters(16000, 1)

                local_user.subscribe_all_audio()
                logger.info("✅ Audio parameters set (16k, Mono)")

            except Exception as e:
                logger.warning(f"⚠️ Warning setting audio parameters: {e}")

            # 5. Connect
            logger.info(f"🔄 Connecting to Agora channel: {channel_name}, uid: {uid}")
            ret = self.connection.connect(token, channel_name, uid)

            if ret < 0:
                logger.error(f"❌ Agora connect() failed with code {ret}")
                return False

            logger.info("🚀 Agora connection initiated!")
            return True

        except Exception as e:
            logger.error(f"❌ Critical error: {e}")
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

            # Unregister connection observer
            if self.conn_observer:
                try:
                    self.connection.unregister_observer(self.conn_observer)
                except Exception:
                    pass

            self.connection.disconnect()
            self.connection = None
            logger.info("🛑 Disconnected from Agora")