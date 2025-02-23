import unittest
import json
from pathlib import Path
from providers.stardots_provider import StarDotsProvider
from core.sync_manager import SyncManager


class TestImageSync(unittest.TestCase):
    """图床同步测试类"""

    @classmethod
    def setUpClass(cls):
        """测试前的准备工作"""
        # 加载配置
        with open("config.json", "r", encoding="utf-8") as f:
            cls.config = json.load(f)

        # 确保配置完整
        stardots_config = cls.config["stardots"]
        required_fields = {"key", "secret", "space", "local_dir"}
        missing_fields = required_fields - set(stardots_config.keys())
        if missing_fields:
            raise ValueError(f"Missing required config fields: {missing_fields}")

        # 初始化provider
        cls.provider = StarDotsProvider(cls.config["stardots"])

        # 设置测试目录
        cls.test_dir = Path(stardots_config["local_dir"])
        cls.sync_manager = SyncManager(image_host=cls.provider, local_dir=cls.test_dir)

    def test_01_check_status(self):
        """测试检查同步状态"""
        print("\n=== 测试同步状态检查 ===")
        status = self.sync_manager.check_sync_status()

        print(f"\n本地目录: {self.test_dir}")
        print(f"需要上传的文件: {len(status['to_upload'])} 个")
        for file in status["to_upload"]:
            print(f"  - [{file.get('category', '根目录')}] {file['filename']}")

        print(f"\n需要下载的文件: {len(status['to_download'])} 个")
        for file in status["to_download"]:
            print(f"  - [{file.get('category', '根目录')}] {file['filename']}")

        self.assertIsInstance(status, dict)

    def test_02_sync_to_remote(self):
        """测试同步到远程"""
        print("\n=== 测试同步到远程 ===")
        try:
            result = self.sync_manager.sync_to_remote()
            print("同步完成")
            self.assertTrue(result)
        except Exception as e:
            self.fail(f"同步失败: {str(e)}")

    def test_03_sync_from_remote(self):
        """测试从远程同步"""
        print("\n=== 测试从远程同步 ===")
        try:
            result = self.sync_manager.sync_from_remote()
            print("同步完成")
            self.assertTrue(result)
        except Exception as e:
            self.fail(f"同步失败: {str(e)}")

    def test_04_sync_all_from_remote(self):
        """测试从远程同步所有内容到local目录"""
        print("\n=== 测试从远程同步所有内容到local目录 ===")

        local_dir = Path("local")
        if local_dir.exists():
            import shutil

            shutil.rmtree(local_dir)
        local_dir.mkdir(exist_ok=True)

        config = self.config["stardots"]
        config["local_dir"] = str(local_dir)
        image_host = StarDotsProvider(config)
        sync_manager = SyncManager(image_host, local_dir)

        try:
            # 执行同步
            result = sync_manager.sync_from_remote()
            self.assertTrue(result)

            # 验证目录结构
            categories = {p.name for p in local_dir.iterdir() if p.is_dir()}
            self.assertGreater(len(categories), 0, "应该有分类目录")

            # 验证文件
            files = list(local_dir.rglob("*.*"))
            self.assertGreater(len(files), 0, "应该有文件被下载")

            print(
                f"同步完成，共下载 {len(files)} 个文件到 {len(categories)} 个分类目录"
            )

        except Exception as e:
            self.fail(f"同步失败: {str(e)}")


def run_tests():
    """运行测试"""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestImageSync)
    unittest.TextTestRunner(verbosity=2).run(suite)


if __name__ == "__main__":
    run_tests()
