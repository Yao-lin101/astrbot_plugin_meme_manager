import json
from img_sync import ImageSync


def test_image_sync():
    """测试 ImageSync 类的所有接口"""
    try:
        # 加载配置
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)["stardots"]

        # 初始化同步客户端
        sync = ImageSync(
            config={
                "key": config["key"],
                "secret": config["secret"],
                "space": config["space"],
            },
            local_dir="memes",
        )

        # 1. 测试配置加载
        print("\n=== 测试配置加载 ===")
        assert sync.provider.key == config["key"], "密钥配置错误"
        assert sync.provider.space == config["space"], "空间配置错误"
        print("配置加载正确")

        # 2. 测试同步状态
        print("\n=== 测试检查同步状态 ===")
        status = sync.check_status()
        assert isinstance(status, dict), "状态返回格式错误"
        assert "to_upload" in status, "缺少上传列表"
        assert "to_download" in status, "缺少下载列表"
        print(f"需要上传: {len(status['to_upload'])} 个文件")
        print(f"需要下载: {len(status['to_download'])} 个文件")

        # 3. 测试远程文件列表
        print("\n=== 测试获取远程文件列表 ===")
        remote_files = sync.get_remote_files()
        assert isinstance(remote_files, list), "远程文件列表格式错误"
        if remote_files:
            assert all(isinstance(f, dict) for f in remote_files), "文件信息格式错误"
            assert all(
                {"url", "id", "filename", "category"}.issubset(f.keys())
                for f in remote_files
            ), "文件信息字段不完整"
        print(f"远程文件数量: {len(remote_files)}")
        if remote_files:
            print("示例文件:")
            for file in remote_files[:3]:
                print(f"- [{file['category']}] {file['filename']}")

        # 4. 测试同步操作
        print("\n=== 测试完整同步 ===")
        sync_result = sync.sync_all()
        assert isinstance(sync_result, bool), "同步结果格式错误"
        print("同步" + ("成功" if sync_result else "失败"))

        print("\n所有测试通过!")
        return True

    except AssertionError as e:
        print(f"\n测试失败: {str(e)}")
        return False
    except Exception as e:
        print(f"\n测试出错: {str(e)}")
        return False


def test_push_to_remote():
    """测试将本地文件推送到云端"""
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)["stardots"]

        sync = ImageSync(
            config={
                "key": config["key"],
                "secret": config["secret"],
                "space": config["space"],
            },
            local_dir="memes",
        )

        print("\n=== 检查同步状态 ===")
        status = sync.check_status()

        if not status["to_upload"] and not status["to_download"]:
            print("本地和云端已经同步，无需操作")
            return True

        print("\n=== 开始推送到云端 ===")
        if sync.upload_to_remote():
            print("推送成功！云端现在与本地一致")
            return True
        else:
            print("推送失败")
            return False

    except Exception as e:
        print(f"测试出错: {str(e)}")
        return False


def test_pull_from_remote():
    """测试从云端拉取文件到本地"""
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)["stardots"]

        sync = ImageSync(
            config={
                "key": config["key"],
                "secret": config["secret"],
                "space": config["space"],
            },
            local_dir="memes",
        )

        print("\n=== 检查同步状态 ===")
        status = sync.check_status()

        if not status["to_upload"] and not status["to_download"]:
            print("本地和云端已经同步，无需操作")
            return True

        print("\n=== 开始从云端拉取 ===")
        if sync.download_to_local():
            print("拉取成功！本地现在与云端一致")
            return True
        else:
            print("拉取失败")
            return False

    except Exception as e:
        print(f"测试出错: {str(e)}")
        return False


def test_check_status():
    """测试检查同步状态"""
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)["stardots"]

        sync = ImageSync(
            config={
                "key": config["key"],
                "secret": config["secret"],
                "space": config["space"],
            },
            local_dir="memes",
        )

        print("\n=== 检查同步状态 ===")
        status = sync.check_status()
        return True

    except Exception as e:
        print(f"测试出错: {str(e)}")
        return False


def main():
    """主测试函数"""
    while True:
        print("\n=== 图片同步测试 ===")
        print("1. 检查同步状态")
        print("2. 推送本地到云端")
        print("3. 从云端拉取到本地")
        print("0. 退出")

        choice = input("\n请选择测试项 (0-3): ").strip()

        if choice == "0":
            print("测试结束")
            break
        elif choice == "1":
            test_check_status()
        elif choice == "2":
            test_push_to_remote()
        elif choice == "3":
            test_pull_from_remote()
        else:
            print("无效的选项，请重新选择")

        input("\n按回车键继续...")


if __name__ == "__main__":
    main()
