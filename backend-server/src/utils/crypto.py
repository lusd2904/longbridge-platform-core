"""
加密工具模块
用于API密钥等敏感信息的加密存储和解密
"""

import base64
import logging
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

# 从环境变量获取加密密钥，如果没有则使用默认密钥（生产环境必须使用环境变量）
MASTER_KEY = os.environ.get("API_ENCRYPTION_KEY", "LongbridgeTrade-Secret-Key-2025")
SALT = os.environ.get("API_ENCRYPTION_SALT", "LongbridgeTrade-Salt").encode()


def _get_fernet() -> Fernet:
    """获取Fernet加密实例"""
    # 使用PBKDF2从主密钥派生加密密钥
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(MASTER_KEY.encode()))
    return Fernet(key)


def encrypt(text: str) -> str:
    """
    加密文本

    Args:
        text: 要加密的明文

    Returns:
        加密后的密文（base64编码）
    """
    if not text:
        return text

    try:
        f = _get_fernet()
        encrypted = f.encrypt(text.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    except Exception as e:
        logger.error(f"加密失败: {e}")
        raise


def decrypt(encrypted_text: str) -> str:
    """
    解密文本

    Args:
        encrypted_text: 要解密的密文（base64编码）

    Returns:
        解密后的明文
    """
    if not encrypted_text:
        return encrypted_text

    try:
        f = _get_fernet()
        # 先解码base64
        encrypted = base64.urlsafe_b64decode(encrypted_text.encode())
        decrypted = f.decrypt(encrypted)
        return decrypted.decode()
    except Exception as e:
        logger.error(f"解密失败: {e}")
        # 如果解密失败，可能是明文存储的旧数据，直接返回
        return encrypted_text


def encrypt_dict(data: dict, fields: list) -> dict:
    """
    加密字典中的指定字段

    Args:
        data: 原始数据字典
        fields: 需要加密的字段列表

    Returns:
        加密后的数据字典
    """
    result = data.copy()
    for field in fields:
        if field in result and result[field]:
            result[field] = encrypt(result[field])
    return result


def decrypt_dict(data: dict, fields: list) -> dict:
    """
    解密字典中的指定字段

    Args:
        data: 加密后的数据字典
        fields: 需要解密的字段列表

    Returns:
        解密后的数据字典
    """
    result = data.copy()
    for field in fields:
        if field in result and result[field]:
            result[field] = decrypt(result[field])
    return result


# 老虎证券需要加密的字段
TIGER_ENCRYPT_FIELDS = ["tiger_id", "tiger_account", "tiger_license", "tiger_private_key_pk1", "tiger_private_key_pk8"]

# 所有需要加密的字段
ALL_ENCRYPT_FIELDS = TIGER_ENCRYPT_FIELDS
