import logging
from typing import Optional

from agora.rtc.agora_base import RtcConnectionPublishConfig, AudioSubscriptionOptions
from agora.rtc.agora_service import AgoraService, AgoraServiceConfig
from agora.rtc.rtc_connection import RTCConnConfig
from agora.rtc.rtc_connection_observer import IRtcConnectionObserver  # Import Observer
from audio_observer import PcmAudioObserver

# DEBUG level
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# --- NEW: Monitor User Joins ---
class MyConnectionObserver(IRtcConnectionObserver):
    def on_user_joined(self, connection, uid, elapsed):
        logger.info(f"👤 [Connection] Remote User JOINED! UID={uid}")

    def on_user_left(self, connection, uid, reason):
        logger.info(f"👋 [Connection] Remote User LEFT! UID={uid}")

    def on_connected(self, connection, info, reason):
        logger.info(f"✅ [Connection] Bot Connected to Channel!")

    def on_disconnected(self, connection, info, reason):
        logger.warning(f"⚠️ [Connection] Bot Disconnected!")


class AgoraManager:
    def __init__(self) -> None:
        self.agora_service: Optional[AgoraService] = None
        self.connection = None
        self.audio_observer: Optional[PcmAudioObserver] = None
        self.conn_observer: Optional[MyConnectionObserver] = None

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
        logger.info("✅ [Manager] Service Initialized")

    def start_connection(self, channel_name: str, uid: str, token: str) -> bool:
        logger.info(f"🔹 [Manager] Connecting: {channel_name} / {uid}")

        if not self.agora_service:
            logger.error("❌ [Manager] Service not initialized!")
            return False

        try:
            con_config = RTCConnConfig()
            con_config.auto_subscribe_audio = 1
            con_config.auto_subscribe_video = 0
            con_config.client_role_type = 1
            con_config.channel_profile = 1

            pub_config = RtcConnectionPublishConfig()
            self.connection = self.agora_service.create_rtc_connection(
                con_config, pub_config
            )
            logger.debug("✅ [Manager] Connection Created")

            # --- NEW: Register Connection Observer ---
            self.conn_observer = MyConnectionObserver()
            self.connection.register_observer(self.conn_observer)
            logger.info("✅ [Manager] Connection Observer Registered")

            # --- Audio Observer ---
            self.audio_observer = PcmAudioObserver(save_to_file=False)

            # --- MASK 12 (4 + 8) ---
            # Listen to BOTH Mixed(4) and BeforeMixing(8)
            mask = 12
            logger.debug(f"🔹 [Manager] Registering Observer MASK={mask} (Mixed+BeforeMixing)")
            ret_observer = self.connection.register_audio_frame_observer(self.audio_observer, mask, 0)

            if ret_observer < 0:
                logger.error(f"❌ [Manager] Register failed: {ret_observer}")
                return False
            else:
                logger.info(f"✅ [Manager] Observer Registered (Mask {mask})")

            # --- Audio Params ---
            try:
                local_user = self.connection.get_local_user()

                # Correct Order: (Channels, SampleRate)
                local_user.set_playback_audio_frame_before_mixing_parameters(1, 16000)

                # Mixed Params: (SampleRate, Channels, SamplesPerCall)
                local_user.set_mixed_audio_frame_parameters(16000, 1, 160)

                local_user.subscribe_all_audio()
                logger.info("✅ [Manager] Params Set (BeforeMixing + Mixed)")

            except Exception as e:
                logger.warning(f"⚠️ [Manager] Params Warning: {e}")

            # --- Connect ---
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

            if self.conn_observer:
                try:
                    self.connection.unregister_observer(self.conn_observer)
                except Exception:
                    pass

            self.connection.disconnect()
            self.connection = None
            logger.info("🛑 [Manager] Disconnected")