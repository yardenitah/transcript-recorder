import hmac
import hashlib
import base64
import struct
import json
import zlib
import time
import logging

# Set up logging for this module
logger = logging.getLogger("AgoraBuilder")
logging.basicConfig(level=logging.INFO)


class ServiceRtc:
    kPrivilegeJoinChannel = 1
    kPrivilegePublishAudioStream = 2
    kPrivilegePublishVideoStream = 3
    kPrivilegePublishDataStream = 4

    def __init__(self, channel_name, uid):
        self._channel_name = channel_name
        self._uid = uid
        self._privileges = {}

    def add_privilege(self, privilege, expire):
        self._privileges[privilege] = expire

    def pack(self):
        return struct.pack('<H', self.kPrivilegeJoinChannel) + struct.pack('<I', self._privileges.get(
            self.kPrivilegeJoinChannel, 0)) + \
            struct.pack('<H', self.kPrivilegePublishAudioStream) + struct.pack('<I', self._privileges.get(
                self.kPrivilegePublishAudioStream, 0)) + \
            struct.pack('<H', self.kPrivilegePublishVideoStream) + struct.pack('<I', self._privileges.get(
                self.kPrivilegePublishVideoStream, 0)) + \
            struct.pack('<H', self.kPrivilegePublishDataStream) + struct.pack('<I', self._privileges.get(
                self.kPrivilegePublishDataStream, 0))


class AccessToken2:
    def __init__(self, app_id, app_certificate, issue_ts, expire):
        self._app_id = app_id
        self._app_certificate = app_certificate
        self._issue_ts = issue_ts
        self._expire = expire
        self._salt = 1
        self._services = {}

    def add_service(self, service):
        self._services[service.__class__.__name__] = service

    def build(self):
        try:
            logger.info(f"🛠️ [TokenBuilder] Starting build process...")
            logger.info(f"   - App ID Length: {len(self._app_id)}")
            logger.info(f"   - Cert Length: {len(self._app_certificate)}")

            signing_content = struct.pack('<H', self._salt) + \
                              struct.pack('<I', self._issue_ts) + \
                              struct.pack('<H', len(self._services))

            for service_name in self._services:
                service = self._services[service_name]
                signing_content += struct.pack('<H', 1)
                signing_content += struct.pack('<H', len(service.pack()))
                signing_content += service.pack()

            logger.info("🛠️ [TokenBuilder] Signing content prepared. Calculating HMAC...")

            signature = hmac.new(self._app_certificate.encode('utf-8'), self._app_id.encode('utf-8') + signing_content,
                                 hashlib.sha256).digest()

            content = struct.pack('<H', 1) + \
                      self._app_id.encode('utf-8') + \
                      struct.pack('<I', self._issue_ts) + \
                      struct.pack('<I', self._salt) + \
                      struct.pack('<H', len(self._services))

            for service_name in self._services:
                service = self._services[service_name]
                content += struct.pack('<H', 1)
                content += struct.pack('<H', len(service.pack()))
                content += service.pack()

            content += struct.pack('<H', len(signature)) + signature

            final_token = "007" + base64.b64encode(zlib.compress(content)).decode('utf-8')
            logger.info(f"✅ [TokenBuilder] Token 007 built successfully. Length: {len(final_token)}")
            return final_token

        except Exception as e:
            logger.error(f"❌ [TokenBuilder] CRASH during build: {str(e)}")
            raise e


class RtcTokenBuilder2:
    @staticmethod
    def build_token_with_uid(app_id, app_certificate, channel_name, uid, role, token_expire):
        logger.info(f"🚀 [TokenBuilder] Request received:")
        logger.info(f"   - Channel: {channel_name} (Type: {type(channel_name)})")
        logger.info(f"   - UID: {uid} (Type: {type(uid)})")

        # Validation checks
        if not isinstance(uid, int):
            logger.warning(f"⚠️ [TokenBuilder] UID is NOT an int! It is {type(uid)}. Attempting conversion...")
            try:
                uid = int(uid)
            except:
                logger.error("❌ [TokenBuilder] Failed to convert UID to int!")
                raise ValueError("UID must be an integer for Protocol 007")

        token = AccessToken2(app_id, app_certificate, int(time.time()), token_expire)
        service_rtc = ServiceRtc(channel_name, uid)

        service_rtc.add_privilege(ServiceRtc.kPrivilegeJoinChannel, token_expire)
        if role == 1:
            service_rtc.add_privilege(ServiceRtc.kPrivilegePublishAudioStream, token_expire)
            service_rtc.add_privilege(ServiceRtc.kPrivilegePublishVideoStream, token_expire)
            service_rtc.add_privilege(ServiceRtc.kPrivilegePublishDataStream, token_expire)

        token.add_service(service_rtc)
        return token.build()