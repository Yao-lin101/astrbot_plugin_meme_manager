from pathlib import Path

from ..interfaces.image_host import ImageHostInterface


class ProviderTemplate(ImageHostInterface):
    """图床提供者模板类"""

    def __init__(self, config: dict):
        self.config = config

    def upload_image(self, file_path: Path) -> dict[str, str]:
        # 实现图床的上传逻辑
        raise NotImplementedError

    def delete_image(self, image_hash: str) -> bool:
        # 实现图床的删除逻辑
        raise NotImplementedError

    def get_image_list(self) -> list[dict[str, str]]:
        # 实现图床的图片列表获取逻辑
        raise NotImplementedError

    def download_image(self, image_info: dict[str, str], save_path: Path) -> bool:
        # 实现图床的下载逻辑
        raise NotImplementedError
