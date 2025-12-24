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
import os
import time
import inspect
from typing import Optional, Any

# Try to import correct Observer class name (depends on SDK version)
try:
    from agora.rtc.rtc_connection_observer import IRTCConnectionObserver as IRtcConnectionObserver
except ImportError:
    from agora.rtc.rtc_connection_observer import IRtcConnectionObserver

from agora.rtc.agora_base import RtcConnectionPublishConfig, AudioSubscriptionOptions
from agora.rtc.agora_service import AgoraService, AgoraServiceConfig
from agora.rtc.rtc_connection import RTCConnConfig

from audio_observer import PcmAudioObserver

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Hard "fingerprint" to verify THIS code runs inside Docker
BUILD_TAG = "🤟🏻🤟🏻🤟🏻 Tal code | build=2025-12-24 | svc=agora_service.py || 🤓 gpt fixed"


def _norm_uid(x: Any) -> str:
    """Best-effort normalize uid from Agora callbacks."""
    try:
        if isinstance(x, bytes):
            return x.decode("utf-8", errors="ignore")
        if isinstance(x, (int, float)):
            return str(int(x))
        # sometimes SDK passes a ctype/struct/string-like
        return str(x)
    except Exception:
        return repr(x)


class AgoraManager:
    def __init__(self) -> None:
        self.agora_service: Optional[AgoraService] = None
        self.connection = None
        self.audio_observer: Optional[PcmAudioObserver] = None
        self.connection_observer: Optional["ConnLogger"] = None
        self.local_user = None

    def initialize(self, app_id: str) -> None:
        logger.info(BUILD_TAG)
        logger.info(
            "Runtime: pid=%s hostname=%s cwd=%s time=%s",
            os.getpid(),
            os.environ.get("HOSTNAME"),
            os.getcwd(),
            time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        logger.debug("🔹 [Manager] Init Engine APP_ID=%s", app_id)

        config = AgoraServiceConfig()
        config.enable_audio_processor = 1
        config.enable_audio_device = 0  # headless mode (no physical sound card)
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

    def _register_audio_observer(self, mask_debug: int) -> int:
        """
        Register audio frame observer in a way that matches the installed SDK signature.
        In agora_python_server_sdk 2.4.1 it's usually:
            register_audio_frame_observer(observer, enable_vad, vad_configure)
        But we keep a safe fallback if signature differs.
        """
        if not self.connection:
            raise RuntimeError("connection is None")

        sig = inspect.signature(self.connection.register_audio_frame_observer)
        param_names = [p.name for p in sig.parameters.values()][1:]  # exclude self
        logger.info("[DEBUG] register_audio_frame_observer signature: %s", sig)
        logger.info("[DEBUG] register_audio_frame_observer params: %s", param_names)

        # Prefer the 2.4.1-style signature: (observer, enable_vad, vad_configure)
        joined = " ".join(param_names).lower()
        if "vad" in joined and "mask" not in joined:
            # enable_vad = 0, vad_configure = None
            return self.connection.register_audio_frame_observer(self.audio_observer, 0, None)

        # Fallback (older variants used mask)
        # Usually something like: (observer, mask, ???)
        try:
            return self.connection.register_audio_frame_observer(self.audio_observer, mask_debug, 0)
        except TypeError:
            # last resort: try minimal call
            return self.connection.register_audio_frame_observer(self.audio_observer)

    def start_connection(self, channel_name: str, uid: str, token: str) -> bool:
        logger.info("🔹 [Manager] Connecting: Channel='%s' / UID='%s'", channel_name, uid)
        logger.info(
            "[DEBUG] IRtcConnectionObserver callbacks: %s",
            [m for m in dir(IRtcConnectionObserver) if m.startswith("on_")],
        )

        if not self.agora_service:
            logger.error("❌ [Manager] Service not initialized!")
            return False

        try:
            # 1) Connection config
            con_config = RTCConnConfig()
            con_config.auto_subscribe_audio = 1

            # IMPORTANT: match browser mode="rtc" (Communication profile)
            # 0 = Communication, 1 = Live Broadcasting (in most Agora SDKs)
            con_config.channel_profile = 0

            # Server is just listening -> Audience is usually better
            # (If your SDK expects broadcaster, switch to 1)
            con_config.client_role_type = 2  # Audience

            # 2) Create connection
            pub_config = RtcConnectionPublishConfig()
            self.connection = self.agora_service.create_rtc_connection(con_config, pub_config)
            logger.debug("✅ [Manager] Connection Object Created")
            logger.info("connect signature: %s", inspect.signature(self.connection.connect))

            # 3) Register connection observer
            self.connection_observer = ConnLogger(manager=self)
            try:
                self.connection.register_observer(self.connection_observer)
                logger.info("[DEBUG] register_observer OK")
            except Exception as e:
                logger.warning("⚠️ [Manager] Could not register connection observer: %s", e)

            # 4) Audio observer setup
            self.audio_observer = PcmAudioObserver(save_to_file=False)

            # only used for fallback (older mask-based APIs)
            mask_debug = 15  # playback + record + mixed + before_mixing (debug)

            try:
                ret_obs = self._register_audio_observer(mask_debug=mask_debug)
                logger.info("[DEBUG] register_audio_frame_observer ret=%s", ret_obs)
            except Exception as e:
                logger.error("[DEBUG] register_audio_frame_observer FAILED: %s", e)
                return False

            # 5) Set audio frame parameters
            local_user = self.connection.get_local_user()
            self.local_user = local_user

            # Helpful: log available methods quickly
            try:
                logger.info("[DEBUG] LocalUser has subscribe_audio? %s", hasattr(local_user, "subscribe_audio"))
                if hasattr(local_user, "subscribe_audio"):
                    logger.info("[DEBUG] subscribe_audio signature: %s", inspect.signature(local_user.subscribe_audio))
            except Exception:
                pass

            # These parameters affect callbacks formats (best-effort; depends on SDK)
            try:
                r_before = local_user.set_playback_audio_frame_before_mixing_parameters(1, 16000)
            except Exception as e:
                r_before = f"ERR({e})"

            try:
                r_mixed = local_user.set_mixed_audio_frame_parameters(16000, 1, 160)
            except Exception as e:
                r_mixed = f"ERR({e})"

            try:
                # not always exists; fine if fails
                r_record = local_user.set_record_audio_frame_parameters(16000, 1, 160)
            except Exception as e:
                r_record = f"ERR({e})"

            logger.info(
                "[DEBUG] set_before_mixing=%s, set_mixed=%s, set_record=%s",
                r_before, r_mixed, r_record
            )

            # 6) Subscribe all audio
            try:
                ret_sub = local_user.subscribe_all_audio()
                logger.info("[DEBUG] subscribe_all_audio ret=%s", ret_sub)
            except Exception as e:
                logger.warning("⚠️ subscribe_all_audio failed: %s", e)

            # 7) Connect
            ret = self.connection.connect(token, channel_name, uid)
            if ret < 0:
                logger.error("❌ [Manager] Connect failed with code: %s", ret)
                return False

            logger.info("🚀 [Manager] Connection Initiated (Code: %s)", ret)
            return True

        except Exception as e:
            logger.error("❌ [Manager] Critical Error during connection: %s", e)
            return False

    def subscribe_user_audio(self, remote_uid: str) -> None:
        """Try explicit per-user subscribe (some setups need it)."""
        if not self.local_user:
            logger.warning("⚠️ subscribe_user_audio called but local_user is None")
            return

        rid = _norm_uid(remote_uid)
        try:
            opts = AudioSubscriptionOptions()
            ret = self.local_user.subscribe_audio(rid, opts)
            logger.info("🔊 subscribe_audio(%s) ret=%s", rid, ret)
        except Exception as e:
            logger.warning("⚠️ subscribe_audio(%s) failed: %s", rid, e)

    def stop_connection(self) -> None:
        if self.connection:
            try:
                self.connection.disconnect()
            except Exception:
                pass
            self.connection = None
            self.local_user = None
            logger.info("🛑 [Manager] Disconnected")

    def get_status(self):
        status = {"connected": self.connection is not None, "build_tag": BUILD_TAG}
        if self.connection_observer:
            status["connection"] = self.connection_observer.get_status()
        if self.audio_observer:
            status["audio"] = self.audio_observer.get_status()
        return status


class ConnLogger(IRtcConnectionObserver):
    def __init__(self, manager: AgoraManager):
        super().__init__()
        self.manager = manager
        self.users = set()

    def on_user_joined(self, *args):
        # Many SDK builds pass (connection, uid) or (uid, elapsed) etc.
        uid = None
        if len(args) >= 2:
            uid = args[1]
        elif len(args) == 1:
            uid = args[0]

        uid_str = _norm_uid(uid)
        logger.info("👤 [Conn] User joined: uid=%s args=%s", uid_str, [repr(a) for a in args])
        self.users.add(uid_str)

        # Try explicit subscribe (in addition to subscribe_all_audio)
        self.manager.subscribe_user_audio(uid_str)

    def on_user_left(self, *args):
        uid = None
        if len(args) >= 2:
            uid = args[1]
        elif len(args) == 1:
            uid = args[0]

        uid_str = _norm_uid(uid)
        logger.info("👤 [Conn] User left: uid=%s args=%s", uid_str, [repr(a) for a in args])
        self.users.discard(uid_str)

    # Add a few common callbacks (best-effort; signatures vary)
    def on_connecting(self, *args):
        logger.info("🔌 [Conn] on_connecting args=%s", [repr(a) for a in args])

    def on_connected(self, *args):
        logger.info("✅ [Conn] on_connected args=%s", [repr(a) for a in args])

    def on_disconnected(self, *args):
        logger.info("🧯 [Conn] on_disconnected args=%s", [repr(a) for a in args])

    def on_error(self, *args):
        logger.error("💥 [Conn] on_error args=%s", [repr(a) for a in args])

    def get_status(self):
        return {"users": sorted(list(self.users))}
