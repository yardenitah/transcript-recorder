import sys
import os
import time
import hmac
import hashlib
import base64
import struct
import zlib
import logging

# Set up logging
logger = logging.getLogger("AgoraRawBuilder")
logging.basicConfig(level=logging.INFO)


class AccessToken:
    # Constants for privileges
    kJoinChannel = 1
    kPublishAudioStream = 2
    kPublishVideoStream = 3
    kPublishDataStream = 4

    def __init__(self, appID, appCertificate, channelName, uid):
        self.appID = appID
        self.appCertificate = appCertificate
        self.channelName = channelName

        # ⚠️ CRITICAL: We mimic C# behavior here.
        # Even if uid is int, we treat it as the raw value passed.
        # The logic in handoff_manager will force it to string to match C# "uid.ToString()"
        self.uid = uid

        self.messages = {}

    def addPrivilege(self, privilege, expireTimestamp):
        self._add_privilege(privilege, expireTimestamp)

    def _add_privilege(self, privilege, expireTimestamp):
        self.messages[privilege] = expireTimestamp

    def build(self):
        self.message = {}
        m = sorted(self.messages.items(), key=lambda item: item[0])
        for (k, v) in m:
            self.message[k] = v

        # Packing logic matching the raw C# implementation
        val = self.pack_string(self.appID) + \
              self.pack_string(self.channelName) + \
              self.pack_string(self.uid) + \
              self.pack_map(self.message)

        signature = hmac.new(self.appCertificate.encode('utf-8'), val, hashlib.sha256).digest()

        crc_channel = zlib.crc32(self.channelName.encode('utf-8')) & 0xffffffff

        # ⚠️ CRITICAL: C# hashes the STRING representation of the UID
        crc_uid = zlib.crc32(str(self.uid).encode('utf-8')) & 0xffffffff

        content = self.pack_string(signature) + \
                  self.pack_uint32(crc_channel) + \
                  self.pack_uint32(crc_uid) + \
                  self.pack_string(val)

        # Protocol 006 Prefix
        return "006" + self.appID + base64.b64encode(content).decode('utf-8')

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
        return struct.pack('<H', len(v)) + v

    @staticmethod
    def pack_map(k_v):
        buffer = bytearray()
        buffer += struct.pack('<H', len(k_v))
        for k, v in k_v.items():
            buffer += AccessToken.pack_uint16(k)
            buffer += AccessToken.pack_uint32(v)
        return bytes(buffer)