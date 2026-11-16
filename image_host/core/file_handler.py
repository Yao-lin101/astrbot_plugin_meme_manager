from pathlib import Path


class FileHandler:
    """文件处理类"""

    SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def scan_local_images(self) -> list[dict[str, str]]:
        """扫描本地图片"""
        images = []
        for file_path in self.base_dir.iterdir():
            if (
                file_path.is_file()
                and file_path.suffix.lower() in self.SUPPORTED_FORMATS
            ):
                images.append(
                    {
                        "path": str(file_path),
                        "id": file_path.name,
                        "filename": file_path.name,
                        "category": "",
                    }
                )
        return images

    def get_file_path(self, category: str, filename: str) -> Path:
        """Return a path in the flat meme directory.

        Args:
            category: Empty category field supplied by the image host protocol.
            filename: Filename without a directory component.

        Returns:
            Destination path for the image.

        Raises:
            ValueError: A category or nested filename was supplied.
        """
        if (
            category
            or filename in {"", ".", ".."}
            or Path(filename).name != filename
            or "\\" in filename
        ):
            raise ValueError("Only flat meme filenames are supported.")
        return self.base_dir / filename
