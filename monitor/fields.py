"""加密欄位：憑證類資料以 Fernet 對稱加密落盤。

金鑰來源（依優先序）：
1. 環境變數 NODEGUARD_ENCRYPT_KEY（urlsafe base64 的 32-byte 金鑰）
2. 由 Django SECRET_KEY 以 SHA-256 派生

注意：若採用派生模式，更換 SECRET_KEY 會導致既有密文無法解密。
要輪換 SECRET_KEY 前，請先設定 NODEGUARD_ENCRYPT_KEY 為原本的派生金鑰。
"""
import base64
import hashlib
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.db import models


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    key = os.environ.get("NODEGUARD_ENCRYPT_KEY", "")
    if not key:
        from django.conf import settings
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode())


class EncryptedCharField(models.CharField):
    """落盤前以 Fernet 加密，讀取時解密。

    舊版明文資料（加密功能上線前寫入）解密失敗時原樣回傳，
    待下次儲存時自動轉為密文。
    """

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        return _get_fernet().encrypt(value.encode()).decode()

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        try:
            return _get_fernet().decrypt(value.encode()).decode()
        except (InvalidToken, ValueError):
            return value
