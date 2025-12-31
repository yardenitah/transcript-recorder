import sys
import os
import time
from random import randint
import hmac
import hashlib
import base64
import struct


class AccessToken(object):
    def __init__(self, appID, appCertificate, channelName, uid):
        self.appID = appID
        self.appCertificate = appCertificate
        self.channelName = channelName
        self.uid = uid
        self.ts = 0
        self.salt = 0
        self.messages = {}
        self.salt = randint(1, 99999999)
        self.ts = int(time.time()) + 24 * 3600

    def addPrivilege(self, privilege, expireTimestamp):
        self.messages[privilege] = expireTimestamp

    def build(self):
        m = sorted(self.messages.items(), key=lambda x: int(x[0]))
        self.messages = {}
        for k, v in m:
            self.messages[k] = v
        return self._build()

    def _build(self):
        m = ""
        for k, v in self.messages.items():
            m += str(k) + str(v)
        val = self.appID + self.channelName + self.uid + m + str(self.salt) + str(self.ts)
        signature = hmac.new(self.appCertificate.encode("utf-8"), val.encode("utf-8"), hashlib.sha256).digest()
        crc_channel_name = (self.appCertificate + self.channelName).encode("utf-8")
        crc = 0xFFFFFFFF & (0 ^ int(hashlib.crc32(crc_channel_name)))
        crc_uid = (self.appCertificate + self.uid).encode("utf-8")
        crc = 0xFFFFFFFF & (crc ^ int(hashlib.crc32(crc_uid)))

        content = struct.pack(
            "I" + str(len(self.channelName)) + "s" + "II" + "I" + "I" + "H" + str(len(signature)) + "s" + str(
                len(m)) + "s",
            len(self.channelName), self.channelName.encode("utf-8"), int(self.uid), crc, self.salt, self.ts,
            len(self.messages), signature, len(m), m.encode("utf-8")
            )
        version = "006".encode("utf-8")
        ret = version + self.appID.encode("utf-8") + base64.b64encode(content)
        return ret.decode("utf-8")


class RtcTokenBuilder:
    Role_Subscriber = 2

    @staticmethod
    def buildTokenWithUid(appId, appCertificate, channelName, uid, role, privilegeExpiredTs):
        token = AccessToken(appId, appCertificate, channelName, str(uid))
        token.addPrivilege(1, privilegeExpiredTs)
        token.addPrivilege(2, privilegeExpiredTs)
        return token.build()