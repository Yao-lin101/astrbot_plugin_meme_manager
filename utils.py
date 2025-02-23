import os
import json
import logging
import aiohttp
import random
import string
from typing import Dict, Any
import shutil
from .config import MEMES_DIR, CURRENT_DIR

logger = logging.getLogger(__name__)

def ensure_dir_exists(path: str) -> None:
    """确保目录存在，不存在则创建"""
    if not os.path.exists(path):
        os.makedirs(path)

def copy_memes_if_not_exists():
    """如果 MEMES_DIR 不存在，则复制 CURRENT_DIR 下的 memes 文件夹"""
    if not os.path.exists(MEMES_DIR):
        shutil.copytree(os.path.join(CURRENT_DIR, "memes"), MEMES_DIR)


def save_json(data: Dict[str, Any], filepath: str) -> bool:
    """保存 JSON 数据到文件"""
    try:
        ensure_dir_exists(os.path.dirname(filepath))
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存 JSON 文件失败 {filepath}: {e}")
        return False

def load_json(filepath: str, default: Dict = None) -> Dict:
    """从文件加载 JSON 数据"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载 JSON 文件失败 {filepath}: {e}")
        return default if default is not None else {}

def dict_to_string(dictionary):
    lines = [f"{key} - {value}\n" for key, value in dictionary.items()]
    return "\n".join(lines)

def generate_secret_key(length=8):
    """生成随机秘钥"""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

async def get_public_ip():
    """异步获取公网IP"""
    ip_apis = [
        'http://api.ipify.org',
        'http://ip.42.pl/raw',
        'http://ifconfig.me/ip',
        'http://ipecho.net/plain'
    ]
    
    async with aiohttp.ClientSession() as session:
        for api in ip_apis:
            try:
                async with session.get(api, timeout=5) as response:
                    if response.status == 200:
                        return await response.text()
            except:
                continue
    
    return "127.0.0.1"
