import os
import aiofiles  # 使用 aiofiles 进行异步文件操作
from werkzeug.utils import secure_filename
from ..config import MEMES_DIR


async def scan_emoji_folder():
    """扫描表情包文件夹，返回所有类别及其表情包"""
    emoji_data = {}
    if not os.path.exists(MEMES_DIR):
        os.makedirs(MEMES_DIR)
    for category in os.listdir(MEMES_DIR):
        category_path = os.path.join(MEMES_DIR, category)
        if os.path.isdir(category_path):
            emoji_files = [
                f
                for f in os.listdir(category_path)
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif"))
            ]
            emoji_data[category] = emoji_files
        else:
            emoji_data[category] = []
    return emoji_data


def get_emoji_by_category(category):
    """获取指定类别下的所有表情包"""
    category_path = os.path.join(MEMES_DIR, category)
    if not os.path.isdir(category_path):
        return []
    emoji_files = [
        f
        for f in os.listdir(category_path)
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif"))
    ]
    return emoji_files


def add_emoji_to_category(category, image_file):
    """添加表情包到指定类别"""
    category_path = os.path.join(MEMES_DIR, category)

    if not os.path.exists(category_path):
        os.makedirs(category_path)
    filename = secure_filename(image_file.filename)
    target_path = os.path.join(category_path, filename)
    image_file.save(target_path)
    return target_path


def delete_emoji_from_category(category, image_file):
    """删除指定类别下的表情包"""
    category_path = os.path.join(MEMES_DIR, category)

    if not os.path.isdir(category_path):
        return False
    image_path = os.path.join(category_path, image_file)
    if os.path.exists(image_path):
        os.remove(image_path)
        return True
    return False


def update_emoji_in_category(category, old_image_file, new_image_file):
    """更新（替换）表情包文件"""
    category_path = os.path.join(MEMES_DIR, category)

    if not os.path.isdir(category_path):
        return False
    old_image_path = os.path.join(category_path, old_image_file)
    if os.path.exists(old_image_path):
        os.remove(old_image_path)
        filename = secure_filename(new_image_file.filename)
        target_path = os.path.join(category_path, filename)
        new_image_file.save(target_path)
        return True
    return False
