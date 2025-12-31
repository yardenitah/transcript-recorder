import sys
import os
import time
import hmac
import hashlib
import base64
import zlib
import struct

# Constants for the Agora protocol
VERSION_LENGTH = 3
APP_ID_LENGTH = 32


class AccessToken:
    """
    Class to build the Agora Dynamic Key (Token).
    It handles packing the data and signing it with the App Certificate.
    """
    def __init__(self, app_id, app_certificate, channel_name, uid):
        self.app_id = app_id
        self.app_certificate = app_certificate
        self.channel_name = channel_name
        self.uid = uid
        self.messages = {}

    def add_privilege(self, privilege, expire_timestamp):
        """
        Adds a privilege (e.g., JoinChannel, PublishAudio) with an expiration time.
        """
        self.messages[privilege] = expire_timestamp

    def build(self):
        """
        Constructs the final token string.
        """
        # 1. Sort messages (privileges) by key to ensure consistent signing order
        m = sorted(self.messages.items(), key=lambda x: x[0])
        self.message = {}
        for (k, v) in m:
            self.message[k] = v

        # 2. Validate required configuration
        if not self.app_id or not self.app_certificate or not self.channel_name:
            raise ValueError("AppId, AppCertificate, and ChannelName are required.")

        # 3. Serialize (Pack) the raw message data
        # Structure: AppID + ChannelName + UID + Privileges
        val = self.pack_string(self.app_id) + \
              self.pack_string(self.channel_name) + \
              self.pack_string(self.uid) + \
              self.pack_map(self.message)

        # 4. Generate the Signature
        # Sign the packed data using HMAC-SHA256 with the App Certificate
        signature = hmac.new(self.app_certificate.encode('utf-8'), val, hashlib.sha256).digest()

        # 5. Calculate CRC32 Checksums (Using zlib)
        # The '& 0xffffffff' ensures it stays within 32-bit unsigned integer limits
        crc_channel_name = zlib.crc32(self.channel_name.encode('utf-8')) & 0xffffffff
        crc_uid = zlib.crc32(self.uid.encode('utf-8')) & 0xffffffff if self.uid else 0

        # 6. Pack the final content
        # Structure: Signature + CRC(Channel) + CRC(UID) + RawMessage
        content = self.pack_string(signature) + \
                  self.pack_uint32(crc_channel_name) + \
                  self.pack_uint32(crc_uid) + \
                  self.pack_string(val)

        # 7. Return the final token string (Version + AppID + Base64EncodedContent)
        return (getattr(self, 'version', "006") + self.app_id + base64.b64encode(content).decode('utf-8'))

    # --- Helper methods for binary packing (Little Endian) ---

    @staticmethod
    def pack_uint16(v):
        return struct.pack('<H', int(v))

    @staticmethod
    def pack_uint32(v):
        return struct.pack('<I', int(v))

    @staticmethod
    def pack_string(v):
        if isinstance(v, str):
            v = v.encode('utf-8')
        # Format: Length (uint16) + String Data
        return struct.pack('<H', len(v)) + v

    @staticmethod
    def pack_map(k_v):
        buffer = bytearray()
        buffer += struct.pack('<H', len(k_v))
        for k, v in k_v.items():
            buffer += AccessToken.pack_uint16(k)  # Key (Privilege ID)
            buffer += AccessToken.pack_uint32(v)  # Value (Expiration Timestamp)
        return bytes(buffer)


def build_token_with_uid(app_id, app_certificate, channel_name, uid, role, privilege_expired_ts):
    """
    Main entry point to build the Agora Access Token (RTC).
    Args:
        role: 1 for Host/Publisher, 2 for Subscriber (Not directly used in token gen but good for context)
        privilege_expired_ts: Timestamp when the token expires (seconds since epoch)
    """
    token = AccessToken(app_id, app_certificate, channel_name, uid)

    # Grant Privilege 1: Join Channel
    token.add_privilege(1, privilege_expired_ts)

    # Grant Privilege 2: Publish Audio Stream
    # Note: Both privileges usually share the same expiration time.
    token.add_privilege(2, privilege_expired_ts)

    return token.build()