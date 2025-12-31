import sys
import os
import time
import hmac
import hashlib
import base64
import struct
import zlib


# Role Constants
class Role:
    Rtc_Publisher = 1
    Rtc_Subscriber = 2
    Rtc_Admin = 101


class RtcTokenBuilder:
    @staticmethod
    def buildTokenWithUid(appId, appCertificate, channelName, uid, role, privilegeExpiredTs):
        return RtcTokenBuilder.buildTokenWithAccount(appId, appCertificate, channelName, uid, role, privilegeExpiredTs)

    @staticmethod
    def buildTokenWithAccount(appId, appCertificate, channelName, account, role, privilegeExpiredTs):
        token = AccessToken(appId, appCertificate, channelName, account)
        token.addPrivilege(AccessToken.kJoinChannel, privilegeExpiredTs)
        if (role == Role.Rtc_Publisher) or (role == Role.Rtc_Subscriber) or (role == Role.Rtc_Admin):
            token.addPrivilege(AccessToken.kPublishAudioStream, privilegeExpiredTs)
            token.addPrivilege(AccessToken.kPublishVideoStream, privilegeExpiredTs)
            token.addPrivilege(AccessToken.kPublishDataStream, privilegeExpiredTs)
        return token.build()


class AccessToken:
    kJoinChannel = 1
    kPublishAudioStream = 2
    kPublishVideoStream = 3
    kPublishDataStream = 4

    def __init__(self, appID, appCertificate, channelName, uid):
        self.appID = appID
        self.appCertificate = appCertificate
        self.channelName = channelName
        self.uid = uid
        self.messages = {}

    def addPrivilege(self, privilege, expireTimestamp):
        self.messages[privilege] = expireTimestamp

    def build(self):
        self.message = {}
        m = sorted(self.messages.items(), key=lambda item: item[0])
        for (k, v) in m:
            self.message[k] = v

        val = self.pack_string(self.appID) + \
              self.pack_string(self.channelName) + \
              self.pack_string(self.uid) + \
              self.pack_map(self.message)

        signature = hmac.new(self.appCertificate.encode('utf-8'), val, hashlib.sha256).digest()

        # Ensure UID is treated as string for CRC calculation just like in C#
        crc_channel = zlib.crc32(self.channelName.encode('utf-8')) & 0xffffffff
        crc_uid = zlib.crc32(str(self.uid).encode('utf-8')) & 0xffffffff

        content = self.pack_string(signature) + \
                  self.pack_uint32(crc_channel) + \
                  self.pack_uint32(crc_uid) + \
                  self.pack_string(val)

        return "006" + self.appID + base64.b64encode(content).decode('utf-8')

    @staticmethod
    def pack_uint16(v):
        return struct.pack('<H', int(v))

    @staticmethod
    def pack_uint32(v):
        return struct.pack('<I', int(v))

    @staticmethod
    def pack_string(v):
        # ✅ FIX: Handle integers gracefully by converting to string first
        if isinstance(v, int):
            v = str(v)

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