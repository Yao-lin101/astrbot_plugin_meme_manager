from pathlib import Path
from typing import Dict, List
from tqdm import tqdm
from ..interfaces.image_host import ImageHostInterface
from .file_handler import FileHandler


class SyncManager:
    """同步管理器"""

    def __init__(self, image_host: ImageHostInterface, local_dir: Path):
        self.image_host = image_host
        self.file_handler = FileHandler(local_dir)

    def check_sync_status(self) -> Dict[str, List[Dict]]:
        """检查同步状态"""
        print("正在扫描本地文件...")
        local_images = self.file_handler.scan_local_images()
        print("\n=== 本地文件标识 ===")
        for img in local_images[:5]:  # 只显示前5个
            print(
                f"ID: {img['id']}, 文件名: {img['filename']}, 分类: {img['category']}"
            )
        if len(local_images) > 5:
            print(f"... 等 {len(local_images)-5} 个文件")

        print("\n正在获取远程文件列表...")
        remote_images = self.image_host.get_image_list()
        print("\n=== 远程文件标识 ===")
        for img in remote_images[:5]:  # 只显示前5个
            print(
                f"ID: {img['id']}, 文件名: {img['filename']}, 分类: {img['category']}"
            )
        if len(remote_images) > 5:
            print(f"... 等 {len(remote_images)-5} 个文件")

        local_files = {img["id"].replace("\\", "/"): img for img in local_images}
        remote_files = {img["id"].replace("\\", "/"): img for img in remote_images}

        # 找出差异
        to_upload = [img for img in local_images if img["id"] not in remote_files]
        to_download = [img for img in remote_images if img["id"] not in local_files]

        if to_upload:
            print(f"\n需要上传 {len(to_upload)} 个文件:")
            for img in to_upload[:5]:
                print(f"- [{img.get('category', '根目录')}] {img['filename']}")
            if len(to_upload) > 5:
                print(f"... 等 {len(to_upload)-5} 个文件")

        if to_download:
            print(f"\n需要下载 {len(to_download)} 个文件:")
            for img in to_download[:5]:
                print(f"- [{img.get('category', '根目录')}] {img['filename']}")
            if len(to_download) > 5:
                print(f"... 等 {len(to_download)-5} 个文件")

        if not to_upload and not to_download:
            print("\n本地文件和远程文件已完全同步，无需更新。")

        return {
            "to_upload": to_upload,
            "to_download": to_download,
            "to_delete_local": [],
            "to_delete_remote": [],
            "is_synced": not (to_upload or to_download),
        }

    def sync_to_remote(self) -> bool:
        """同步本地文件到远程"""
        status = self.check_sync_status()

        if status.get("is_synced", False):
            return True

        # 上传新文件
        to_upload = status["to_upload"]
        if to_upload:
            print(f"\n开始上传 {len(to_upload)} 个文件...")
            with tqdm(total=len(to_upload), desc="上传进度") as pbar:
                for image in to_upload:
                    file_path = Path(image["path"])
                    try:
                        self.image_host.upload_image(file_path)
                        pbar.update(1)
                    except Exception as e:
                        print(f"\n上传失败: {file_path.name} - {str(e)}")

        # 删除远程文件
        to_delete = status["to_delete_remote"]
        if to_delete:
            print(f"\n开始删除远程文件 {len(to_delete)} 个...")
            with tqdm(total=len(to_delete), desc="删除进度") as pbar:
                for image in to_delete:
                    try:
                        self.image_host.delete_image(image["id"])
                        pbar.update(1)
                    except Exception as e:
                        print(f"\n删除失败: {image['id']} - {str(e)}")

        return True

    def sync_from_remote(self) -> bool:
        """从远程同步文件到本地"""
        status = self.check_sync_status()

        if status.get("is_synced", False):
            return True

        # 下载新文件
        to_download = status["to_download"]
        if to_download:
            print(f"\n开始下载 {len(to_download)} 个文件...")
            with tqdm(total=len(to_download), desc="下载进度") as pbar:
                for image in to_download:
                    try:
                        # 使用图片信息中的分类
                        category = image.get("category", "default")
                        filename = image["filename"]

                        # 获取保存路径
                        save_path = self.file_handler.get_file_path(category, filename)

                        if self.image_host.download_image(image, save_path):
                            pbar.update(1)
                        else:
                            print(f"\n下载失败: {filename}")
                    except Exception as e:
                        print(f"\n下载失败: {filename} - {str(e)}")

        # 删除本地文件
        to_delete = status["to_delete_local"]
        if to_delete:
            print(f"\n开始删除本地文件 {len(to_delete)} 个...")
            with tqdm(total=len(to_delete), desc="删除进度") as pbar:
                for image in to_delete:
                    try:
                        file_path = Path(image["path"])
                        file_path.unlink()
                        pbar.update(1)
                    except Exception as e:
                        print(f"\n删除失败: {file_path.name} - {str(e)}")

        return True
