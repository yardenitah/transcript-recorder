# import logging
# from typing import Optional
#
# # Try to import the correct Observer class name for version 2.4.1 (IRTC...)
# # with a fallback to the older name (IRtc...)
# try:
#     from agora.rtc.rtc_connection_observer import IRTCConnectionObserver as IRtcConnectionObserver
# except ImportError:
#     from agora.rtc.rtc_connection_observer import IRtcConnectionObserver
#
# from agora.rtc.agora_base import RtcConnectionPublishConfig, AudioSubscriptionOptions
# from agora.rtc.agora_service import AgoraService, AgoraServiceConfig
# from agora.rtc.rtc_connection import RTCConnConfig
# from audio_observer import PcmAudioObserver
#
# # Logger setup
# logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)
#
#
# class ConnLogger(IRtcConnectionObserver):
#     """
#     Observer class to track real-time connection events and user presence.
#     """
#
#     def __init__(self):
#         super().__init__()
#         self.users = set()
#         self.published = set()
#         self.state = None
#
#     def on_user_joined(self, *args):
#         # Handling dynamic arguments as different SDK versions send different params (uid, elapsed)
#         uid = args[1] if len(args) > 1 else args[0]
#         logger.info(f"👤 [Conn] User joined: uid={uid}")
#         self.users.add(uid)
#
#     def on_user_left(self, *args):
#         uid = args[1] if len(args) > 1 else args[0]
#         logger.info(f"👤 [Conn] User left: uid={uid}")
#         self.users.discard(uid)
#         self.published.discard(uid)
#
#     def on_connection_state_changed(self, *args):
#         # Triggered when connection state changes (connecting, connected, failed, etc.)
#         logger.info(f"🔌 [Conn] State changed")
#
#     def get_status(self):
#         """Returns collected connection status for the API."""
#         return {
#             "users": list(self.users),
#             "published": list(self.published),
#         }
#
#
# class AgoraManager:
#     def __init__(self) -> None:
#         self.agora_service: Optional[AgoraService] = None
#         self.connection = None
#         self.audio_observer: Optional[PcmAudioObserver] = None
#         self.connection_observer: Optional["ConnLogger"] = None
#
#     def initialize(self, app_id: str) -> None:
#         logger.debug(f"🔹 [Manager] Init Engine APP_ID={app_id}")
#         config = AgoraServiceConfig()
#         config.enable_audio_processor = 1
#         config.enable_audio_device = 0  # Headless mode (no physical sound card)
#         config.enable_video = 0
#         config.context = 0
#
#         # Handle different field names for app_id in different SDK versions
#         try:
#             config.app_id = app_id
#         except AttributeError:
#             pass
#         try:
#             config.appid = app_id
#         except AttributeError:
#             pass
#
#         self.agora_service = AgoraService()
#         self.agora_service.initialize(config)
#         logger.info("✅ [Manager] Service Initialized (Headless Mode)")
#
#     def start_connection(self, channel_name: str, uid: str, token: str) -> bool:
#         logger.info(f"🔹 [Manager] Connecting: Channel='{channel_name}' / UID='{uid}'")
#         if not self.agora_service:
#             logger.error("❌ [Manager] Service not initialized!")
#             return False
#
#         try:
#             # 1. Connection configuration
#             con_config = RTCConnConfig()
#             con_config.auto_subscribe_audio = 1
#             con_config.client_role_type = 1  # Broadcaster
#
#             # Use Live Broadcasting profile (1)
#             con_config.channel_profile = 1
#
#             # 2. Create Connection
#             pub_config = RtcConnectionPublishConfig()
#             self.connection = self.agora_service.create_rtc_connection(con_config, pub_config)
#             logger.debug("✅ [Manager] Connection Object Created")
#
#             # 3. Register Connection Observer
#             self.connection_observer = ConnLogger()
#             try:
#                 self.connection.register_observer(self.connection_observer)
#             except Exception as e:
#                 logger.warning(f"⚠️ [Manager] Could not register connection observer: {e}")
#
#             # 4. Audio Observer Setup
#             self.audio_observer = PcmAudioObserver(save_to_file=False)
#             mask = 12  # Mixed (4) + BeforeMixing (8)
#             self.connection.register_audio_frame_observer(self.audio_observer, mask, 0)
#
#             # 5. Audio Parameters Setup
#             local_user = self.connection.get_local_user()
#
#             # Set PCM parameters for 16kHz mono (Required for Soniox)
#             # Agora AI confirmed this IS the correct way to set format for callbacks
#             local_user.set_playback_audio_frame_before_mixing_parameters(1, 16000)
#             local_user.set_mixed_audio_frame_parameters(16000, 1, 160)
#
#             # 6. Audio Subscription (Corrected based on Agora AI)
#             # subscribe_all_audio does NOT take arguments in v2.4.1
#             ret_sub = local_user.subscribe_all_audio()
#
#             if ret_sub < 0:
#                 logger.error(f"❌ [Manager] subscribe_all_audio failed: {ret_sub}")
#
#             # 7. Final Connect call
#             ret = self.connection.connect(token, channel_name, uid)
#             if ret < 0:
#                 logger.error(f"❌ [Manager] Connect failed with code: {ret}")
#                 return False
#
#             logger.info(f"🚀 [Manager] Connection Initiated (Code: {ret})")
#             return True
#
#         except Exception as e:
#             logger.error(f"❌ [Manager] Critical Error during connection: {e}")
#             return False
#
#     def stop_connection(self) -> None:
#         if self.connection:
#             self.connection.disconnect()
#             self.connection = None
#             logger.info("🛑 [Manager] Disconnected")
#
#     def get_status(self):
#         """Aggregates all status info for the /status endpoint."""
#         status = {"connected": self.connection is not None}
#         if self.connection_observer:
#             status["connection"] = self.connection_observer.get_status()
#         if self.audio_observer:
#             status["audio"] = self.audio_observer.get_status()
#         return status


import logging
import os
from agora.rtc.agora_service import AgoraService, AgoraServiceConfig, RTCConnConfig, RtcConnectionPublishConfig
from agora.rtc.rtc_connection import IRTCConnectionObserver
from agora.rtc.audio_frame_observer import IAudioFrameObserver, AudioSubscriptionOptions
from audio_observer import PcmAudioObserver

# Logging
logger = logging.getLogger("agora_service")
logging.basicConfig(level=logging.DEBUG)


class ConnLogger(IRTCConnectionObserver):
    def on_connected(self, agora_rtc_conn, conn_info, reason):
        logger.info(f"✅ [Conn] Connected! ID={conn_info.id} User={conn_info.user_id}")

    def on_user_joined(self, agora_rtc_conn, uid):
        logger.info(f"👤 [Conn] User joined: uid={uid}")

    def on_user_left(self, agora_rtc_conn, uid, reason):
        logger.info(f"👋 [Conn] User left: uid={uid}")

    def on_connecting(self, agora_rtc_conn, conn_info, reason):
        logger.debug(f"⏳ [Conn] Connecting...")


class AgoraManager:
    def __init__(self):
        self.agora_service = None
        self.connection = None
        self.audio_observer = None

    def initialize(self, app_id: str):
        config = AgoraServiceConfig()
        config.app_id = app_id

        # --- SHINUI 1: Force Audio Device ---
        # גם אם אין רמקולים, אנחנו אומרים למנוע "יש לך התקן",
        # כדי שהוא יפעיל את לולאת העיבוד (Audio Pump).
        config.enable_audio_device = 1

        config.enable_audio_processor = 1
        config.enable_video = 0

        self.agora_service = AgoraService()
        self.agora_service.initialize(config)
        logger.info("✅ [Manager] Service Initialized (Force Audio Device Mode)")

    def start_connection(self, channel_name: str, uid: str, token: str) -> bool:
        logger.info(f"🔹 [Manager] Connecting: Channel='{channel_name}' / UID='{uid}'")

        try:
            # 1. Connection Config
            con_config = RTCConnConfig()
            con_config.auto_subscribe_audio = 1
            con_config.client_role_type = 1  # Broadcaster
            con_config.channel_profile = 1  # Live Broadcasting

            # --- SHINUI 2: Fix for TypeError ---
            # הגדרת סנריו מפורשת מונעת מה-SDK לנסות לנחש וליפול על NoneType
            con_config.audio_scenario = 0  # AUDIO_SCENARIO_DEFAULT

            # 2. Create Connection
            self.connection = self.agora_service.create_rtc_connection(con_config)

            # 3. Register Observer
            self.connection_observer = ConnLogger()
            self.connection.register_observer(self.connection_observer)

            # 4. Audio Observer
            self.audio_observer = PcmAudioObserver()

            # --- SHINUI 3: Mask Strategy ---
            # אנחנו מבקשים את כל סוגי הפריימים האפשריים (Mixed + Playback + BeforeMixing)
            # Mask 12 = (4: Mixed) + (8: BeforeMixing)
            # אבל בוא ננסה לתפוס הכל ע"י חיבור ביטים
            # POSITION_PLAYBACK(1) | POSITION_RECORD(2) | POSITION_MIXED(4) | POSITION_BEFORE_MIXING(8) = 15
            mask = 15
            self.connection.register_audio_frame_observer(self.audio_observer, mask, 0)

            # 5. Parameters
            local_user = self.connection.get_local_user()

            # ניסיון להגדיר פרמטרים, אבל בתוך TRY כדי שלא יפיל את הכל אם זה נכשל
            try:
                local_user.set_playback_audio_frame_before_mixing_parameters(1, 16000)
                local_user.set_mixed_audio_frame_parameters(16000, 1, 160)
            except Exception as e:
                logger.warning(f"⚠️ [Manager] Could not set audio params: {e}")

            # 6. Subscribe
            local_user.subscribe_all_audio()

            # 7. Connect
            ret = self.connection.connect(token, channel_name, uid)
            if ret < 0:
                logger.error(f"❌ Connect failed: {ret}")
                return False

            logger.info(f"🚀 [Manager] Connection Initiated")
            return True

        except Exception as e:
            logger.error(f"❌ [Manager] Error: {e}")
            return False

    def stop(self):
        if self.connection:
            self.connection.disconnect()
            self.connection.unregister_audio_frame_observer()
            self.connection = None
        if self.agora_service:
            self.agora_service.release()
            self.agora_service = None