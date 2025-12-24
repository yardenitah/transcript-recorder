# import logging
# from typing import Optional
# import inspect
#
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
#         logger.info("[DEBUG] IRtcConnectionObserver callbacks: %s",[m for m in dir(IRtcConnectionObserver) if m.startswith("on_")])
#
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
#             logger.info(f"connect signature: {inspect.signature(self.connection.connect)}")
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
#             # mask = 12  # Mixed (4) + BeforeMixing (8)
#             mask = 15  # 1+2+4+8 => playback + record + mixed + before_mixing | its temp for debug
#             logger.info(f"register_audio_frame_observer signature: {inspect.signature(self.connection.register_audio_frame_observer)}")
#
#             try:
#                 # after this line the SDH should start calling the callback in service.py
#                 # ret_obs = self.connection.register_audio_frame_observer(self.audio_observer, mask, 0)
#                 ret_obs = self.connection.register_audio_frame_observer(self.audio_observer, mask, 0)
#                 logger.info(f"[DEBUG] register_audio_frame_observer ret={ret_obs}")
#             except Exception as e:
#                 logger.error(f"[DEBUG] register_audio_frame_observer FAILED: {e}")
#                 return False
#
#             # 5. Audio Parameters Setup
#             local_user = self.connection.get_local_user()
#
#             # Set PCM parameters for 16kHz mono (Required for Soniox)
#             # Agora AI confirmed this IS the correct way to set format for callbacks
#             r1 = local_user.set_playback_audio_frame_before_mixing_parameters(1, 16000)
#             r2 = local_user.set_mixed_audio_frame_parameters(16000, 1, 160)
#             logger.info(f"[DEBUG] set_before_mixing ret={r1}, set_mixed ret={r2}")
#
#             # 6. Audio Subscription (Corrected based on Agora AI)
#             # subscribe_all_audio does NOT take arguments in v2.4.1
#             ret_sub = local_user.subscribe_all_audio()
#             logger.info(f"[DEBUG] subscribe_all_audio ret={ret_sub}")
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

# import logging
# from typing import Optional
# import inspect
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
# class AgoraManager:
#     def __init__(self) -> None:
#         self.agora_service: Optional[AgoraService] = None
#         self.connection = None
#         self.audio_observer: Optional[PcmAudioObserver] = None
#         self.connection_observer: Optional["ConnLogger"] = None
#
#     def initialize(self, app_id: str) -> None:
#         logger.debug(f"🔹 [Manager] Init Engine APP_ID={app_id}")
#         logger.info(f"🤟🏻🤟🏻🤟🏻 Tal code")
#
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
#         logger.info("[DEBUG] IRtcConnectionObserver callbacks: %s",[m for m in dir(IRtcConnectionObserver) if m.startswith("on_")])
#
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
#             logger.info(f"connect signature: {inspect.signature(self.connection.connect)}")
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
#             # mask = 12  # Mixed (4) + BeforeMixing (8)
#             mask = 15  # 1+2+4+8 => playback + record + mixed + before_mixing | its temp for debug
#
#             try:
#                 # after this line the SDH should start calling the callback in service.py
#                 ret_obs = self.connection.register_audio_frame_observer(self.audio_observer, mask, 0)
#                 logger.info(f"[DEBUG] register_audio_frame_observer ret={ret_obs}")
#             except Exception as e:
#                 logger.error(f"[DEBUG] register_audio_frame_observer FAILED: {e}")
#                 return False
#
#             # 5. Audio Parameters Setup
#             local_user = self.connection.get_local_user()
#
#             # Set PCM parameters for 16kHz mono (Required for Soniox)
#             # Agora AI confirmed this IS the correct way to set format for callbacks
#             r1 = local_user.set_playback_audio_frame_before_mixing_parameters(1, 16000)
#             r2 = local_user.set_mixed_audio_frame_parameters(16000, 1, 160)
#             logger.info(f"[DEBUG] set_before_mixing ret={r1}, set_mixed ret={r2}")
#
#             # 6. Audio Subscription (Corrected based on Agora AI)
#             # subscribe_all_audio does NOT take arguments in v2.4.1
#             ret_sub = local_user.subscribe_all_audio()
#             logger.info(f"[DEBUG] subscribe_all_audio ret={ret_sub}")
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

import logging
from typing import Optional
import inspect

# Try to import the correct Observer class name for version 2.4.1 (IRTC...)
# with a fallback to the older name (IRtc...)
try:
    from agora.rtc.rtc_connection_observer import IRTCConnectionObserver as IRtcConnectionObserver
except ImportError:
    from agora.rtc.rtc_connection_observer import IRtcConnectionObserver

from agora.rtc.agora_base import RtcConnectionPublishConfig, AudioSubscriptionOptions
from agora.rtc.agora_service import AgoraService, AgoraServiceConfig
from agora.rtc.rtc_connection import RTCConnConfig
from agora.rtc.local_user_observer import IRTCLocalUserObserver
from audio_observer import PcmAudioObserver

# Logger setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Enable SDK's internal logging for audio frame observer
sdk_logger = logging.getLogger('agora.rtc._ctypes_handle._audio_frame_observer')
sdk_logger.setLevel(logging.DEBUG)
sdk_logger.addHandler(logging.StreamHandler())


class AgoraManager:
    def __init__(self) -> None:
        self.agora_service: Optional[AgoraService] = None
        self.connection = None
        self.audio_observer: Optional[PcmAudioObserver] = None
        self.connection_observer: Optional["ConnLogger"] = None
        self.local_user_observer: Optional["LocalUserLogger"] = None

    def initialize(self, app_id: str) -> None:
        logger.debug(f"🔹 [Manager] Init Engine APP_ID={app_id}")
        config = AgoraServiceConfig()
        config.enable_audio_processor = 1
        config.enable_audio_device = 0  # Headless mode (no physical sound card)
        config.enable_video = 0
        config.context = 0

        # Handle different field names for app_id in different SDK versions
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
        logger.info("✅ [Manager] Service Initialized (Headless Mode)")

    def start_connection(self, channel_name: str, uid: str, token: str) -> bool:
        logger.info(f"🔹 [Manager] Connecting: Channel='{channel_name}' / UID='{uid}'")
        logger.info("[DEBUG] IRtcConnectionObserver callbacks: %s",[m for m in dir(IRtcConnectionObserver) if m.startswith("on_")])

        if not self.agora_service:
            logger.error("❌ [Manager] Service not initialized!")
            return False

        try:
            # 1. Connection configuration
            con_config = RTCConnConfig()
            con_config.auto_subscribe_audio = 1
            con_config.client_role_type = 1  # Broadcaster

            # Use Live Broadcasting profile (1)
            con_config.channel_profile = 1

            # 2. Create Connection
            pub_config = RtcConnectionPublishConfig()
            self.connection = self.agora_service.create_rtc_connection(con_config, pub_config)
            logger.debug("✅ [Manager] Connection Object Created")
            logger.info(f"connect signature: {inspect.signature(self.connection.connect)}")
            try:
                logger.debug("[Manager][SAFETY BELT] step one")
                # 3. Register Connection Observer
                self.connection_observer = ConnLogger()
                logger.debug("[Manager][SAFETY BELT] step two")
                try:
                    self.connection.register_observer(self.connection_observer)
                    logger.debug("[Manager][SAFETY BELT] step three")
                except Exception as e:
                    logger.warning(f"⚠️ [Manager] Could not register connection observer: {e}")

                # 3b. Register Local User Observer (for audio subscription events)
                logger.debug("[Manager][SAFETY BELT] step four")
                self.local_user_observer = LocalUserLogger()
                logger.debug("[Manager][SAFETY BELT] step five")
                try:
                    ret_local_obs = self.connection.register_local_user_observer(self.local_user_observer)
                    logger.info(f"[DEBUG] register_local_user_observer ret={ret_local_obs}")
                except Exception as e:
                    logger.warning(f"⚠️ [Manager] Could not register local user observer: {e}")
            except Exception as e:
                logger.error(f"❌ [Manager][SAFETY BELT] Oh my oh my!!! 😱 {e}")

            # 4. Get local user first
            local_user = self.connection.get_local_user()
            logger.info(f"[DEBUG] local_user obtained: {local_user}")

            # 5. Set PCM parameters BEFORE registering observer (order matters!)
            # Set PCM parameters for 16kHz mono (Required for Soniox)
            r1 = local_user.set_playback_audio_frame_before_mixing_parameters(1, 16000)
            r2 = local_user.set_mixed_audio_frame_parameters(16000, 1, 160)
            logger.info(f"[DEBUG] set_before_mixing ret={r1}, set_mixed ret={r2}")

            if r1 < 0 or r2 < 0:
                logger.error(f"❌ [Manager] Audio parameters setup failed: r1={r1}, r2={r2}")

            # 6. Audio Observer Setup (AFTER parameters)
            self.audio_observer = PcmAudioObserver(save_to_file=False)
            logger.info(f"[DEBUG] PcmAudioObserver created: {self.audio_observer}")

            try:
                # Register observer: params are (observer, enable_vad, vad_configure)
                # SDK v2.4.0 automatically enables all callbacks - no mask needed
                ret_obs = self.connection.register_audio_frame_observer(self.audio_observer, 0, None)
                logger.info(f"[DEBUG] register_audio_frame_observer ret={ret_obs}")

                if ret_obs < 0:
                    logger.error(f"❌ [Manager] Audio observer registration FAILED with code: {ret_obs}")
                    return False
                else:
                    logger.info(f"✅ [Manager] Audio observer registered successfully")
            except Exception as e:
                logger.error(f"[DEBUG] register_audio_frame_observer FAILED: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return False

            # 7. Audio Subscription (Corrected based on Agora AI)
            # subscribe_all_audio does NOT take arguments in v2.4.1
            ret_sub = local_user.subscribe_all_audio()
            logger.info(f"[DEBUG] subscribe_all_audio ret={ret_sub}")

            if ret_sub < 0:
                logger.error(f"❌ [Manager] subscribe_all_audio failed: {ret_sub}")
            else:
                logger.info(f"✅ [Manager] subscribe_all_audio succeeded")

            # 8. Final Connect call
            ret = self.connection.connect(token, channel_name, uid)
            if ret < 0:
                logger.error(f"❌ [Manager] Connect failed with code: {ret}")
                return False

            logger.info(f"🚀 [Manager] Connection Initiated (Code: {ret})")
            logger.info(f"⚠️ [Manager] NOTE: Audio callbacks will only fire when REMOTE USERS publish audio!")
            return True

        except Exception as e:
            logger.error(f"❌ [Manager] Critical Error during connection: {e}")
            return False

    def stop_connection(self) -> None:
        if self.connection:
            self.connection.disconnect()
            self.connection = None
            logger.info("🛑 [Manager] Disconnected")

    def get_status(self):
        """Aggregates all status info for the /status endpoint."""
        status = {"connected": self.connection is not None}
        if self.connection_observer:
            status["connection"] = self.connection_observer.get_status()
        if self.audio_observer:
            status["audio"] = self.audio_observer.get_status()
        return status

class LocalUserLogger(IRTCLocalUserObserver):
    """
    Observer for local user events - critical for audio subscription debugging.
    """
    def on_user_audio_track_subscribed(self, agora_local_user, user_id, agora_remote_audio_track):
        logger.info(f"🎵 [LocalUser] Audio track subscribed: user_id={user_id}, track={agora_remote_audio_track}")

    def on_audio_subscribe_state_changed(self, agora_local_user, channel, user_id, old_state, new_state, elapse_since_last_state):
        logger.info(f"🔄 [LocalUser] Audio subscribe state changed: user_id={user_id}, old={old_state}, new={new_state}")

    def on_first_remote_audio_frame(self, agora_local_user, user_id, elapsed):
        logger.info(f"🎤 [LocalUser] First remote audio frame: user_id={user_id}, elapsed={elapsed}ms")

    def on_first_remote_audio_decoded(self, agora_local_user, user_id, elapsed):
        logger.info(f"🔊 [LocalUser] First remote audio decoded: user_id={user_id}, elapsed={elapsed}ms")

    def on_user_audio_track_state_changed(self, agora_local_user, user_id, agora_remote_audio_track, state, reason, elapsed):
        logger.info(f"📡 [LocalUser] Audio track state changed: user_id={user_id}, state={state}, reason={reason}")


class ConnLogger(IRtcConnectionObserver):
    """
    Observer class to track real-time connection events and user presence.
    """

    def __init__(self):
        super().__init__()
        self.users = set()
        self.published = set()
        self.state = None

    def on_user_joined(self, *args):
        # Handling dynamic arguments as different SDK versions send different params (uid, elapsed)
        uid = args[1] if len(args) > 1 else args[0]
        logger.info(f"👤 [Conn] User joined: uid={uid}")
        self.users.add(uid)

    def on_user_left(self, *args):
        uid = args[1] if len(args) > 1 else args[0]
        logger.info(f"👤 [Conn] User left: uid={uid}")
        self.users.discard(uid)
        self.published.discard(uid)

    def on_connection_state_changed(self, *args):
        # Triggered when connection state changes (connecting, connected, failed, etc.)
        logger.info(f"🔌 [Conn] State changed")

    def get_status(self):
        """Returns collected connection status for the API."""
        return {
            "users": list(self.users),
            "published": list(self.published),
        }
