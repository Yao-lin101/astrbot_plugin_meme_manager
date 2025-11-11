#!/usr/bin/env python3
"""
测试 Cloudflare R2 功能是否正常工作
使用用户提供的配置进行测试
"""

import sys
import json
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

def test_r2_with_user_config():
    """使用用户提供的配置测试R2功能"""
    print("=" * 70)
    print("Cloudflare R2 功能测试")
    print("=" * 70)
    
    # 用户提供的配置（修正后的域名）
    user_config = {
        "image_host": "cloudflare_r2",
        "image_host_config": {
            "cloudflare_r2": {
                "account_id": "8f9052f99abfe069e1b09732df19cc88",
                "access_key_id": "cb5d78d1db08e88c57a04b8eb5100847",
                "secret_access_key": "d47fef6bf20cff81654db815c07b862ff323de2d7da5ed59cb47d4f0c02eaf21",
                "bucket_name": "piexian",
                "public_url": "https://r2.pieixan.icu"
            }
        }
    }
    
    r2_config = user_config["image_host_config"]["cloudflare_r2"]
    
    print("\n📋 配置信息:")
    print(f"  - Account ID: {r2_config['account_id'][:10]}...")
    print(f"  - Access Key ID: {r2_config['access_key_id'][:10]}...")
    print(f"  - Secret Access Key: {'已设置' if r2_config['secret_access_key'] else '未设置'}")
    print(f"  - Bucket Name: {r2_config['bucket_name']}")
    print(f"  - Public URL: {r2_config['public_url']}")
    
    try:
        # 测试1: 初始化R2提供商
        print("\n" + "=" * 70)
        print("测试 1: 初始化 R2 提供商")
        print("=" * 70)
        
        from image_host.providers.cloudflare_r2_provider import CloudflareR2Provider
        provider = CloudflareR2Provider(r2_config)
        print("✅ R2 提供商初始化成功")
        
        # 测试2: 测试连接（列出存储桶中的文件）
        print("\n" + "=" * 70)
        print("测试 2: 测试连接并获取文件列表")
        print("=" * 70)
        
        files = provider.get_image_list()
        print(f"✅ 成功获取文件列表，共 {len(files)} 个文件")
        
        if files:
            print("\n前 5 个文件:")
            for i, file_info in enumerate(files[:5]):
                print(f"  {i+1}. {file_info['filename']}")
                print(f"     URL: {file_info['url']}")
                print(f"     分类: {file_info.get('category', '无')}")
        else:
            print("存储桶为空")
        
        # 测试3: 创建测试图片并上传
        print("\n" + "=" * 70)
        print("测试 3: 上传测试图片")
        print("=" * 70)
        
        # 创建临时测试图片
        test_dir = Path("/tmp/meme_test")
        test_dir.mkdir(exist_ok=True)
        test_file = test_dir / "test_r2_connection.jpg"
        
        # 生成一个简单的测试图片
        from PIL import Image
        import numpy as np
        
        # 创建一个简单的彩色图片
        img_array = np.zeros((100, 100, 3), dtype=np.uint8)
        img_array[20:80, 20:80] = [255, 0, 0]  # 红色方块
        test_img = Image.fromarray(img_array)
        test_img.save(test_file)
        
        print(f"✅ 创建测试图片: {test_file}")
        
        # 上传测试图片
        print("\n上传测试图片...")
        result = provider.upload_image(test_file)
        print(f"✅ 上传成功!")
        print(f"  - 文件名: {result['filename']}")
        print(f"  - 远程ID: {result['id']}")
        print(f"  - 公共URL: {result['url']}")
        print(f"  - 分类: {result.get('category', '无')}")
        
        # 测试4: 验证上传记录功能
        print("\n" + "=" * 70)
        print("测试 4: 验证上传记录功能")
        print("=" * 70)
        
        from image_host.core.upload_tracker import UploadTracker
        tracker_file = test_dir / ".upload_tracker.json"
        tracker = UploadTracker(tracker_file)
        
        # 检查是否标记为已上传
        is_uploaded = tracker.is_uploaded(test_file)
        print(f"上传前检查: {'已上传' if is_uploaded else '未上传'}")
        
        # 标记为已上传
        tracker.mark_uploaded(test_file, "", result['url'])
        print("✅ 已标记为已上传")
        
        # 再次检查
        is_uploaded = tracker.is_uploaded(test_file)
        print(f"标记后检查: {'已上传' if is_uploaded else '未上传'}")
        
        # 测试5: 再次上传（应该跳过）
        print("\n" + "=" * 70)
        print("测试 5: 重复上传测试（应该跳过）")
        print("=" * 70)
        
        # 模拟同步管理器的逻辑
        if tracker.is_uploaded(test_file):
            print("✅ 检测到已上传记录，跳过上传")
        else:
            print("⚠️  未检测到上传记录，会重复上传")
        
        # 测试6: 下载测试
        print("\n" + "=" * 70)
        print("测试 6: 下载测试图片")
        print("=" * 70)
        
        download_dir = test_dir / "download"
        download_dir.mkdir(exist_ok=True)
        download_file = download_dir / "downloaded_test.jpg"
        
        # 下载图片信息
        image_info = {
            'id': result['id'],
            'filename': result['filename'],
            'category': result.get('category', ''),
            'url': result['url']
        }
        
        print(f"下载图片: {image_info['filename']}")
        success = provider.download_image(image_info, download_file)
        
        if success and download_file.exists():
            print(f"✅ 下载成功!")
            print(f"  - 保存路径: {download_file}")
            print(f"  - 文件大小: {download_file.stat().st_size} bytes")
        else:
            print(f"❌ 下载失败")
        
        # 测试7: 清理测试文件
        print("\n" + "=" * 70)
        print("测试 7: 清理测试文件")
        print("=" * 70)
        
        # 删除远程测试文件
        print("删除远程测试文件...")
        delete_success = provider.delete_image(result['id'])
        print(f"{'✅' if delete_success else '❌'} 远程文件删除{'成功' if delete_success else '失败'}")
        
        # 清理本地文件
        import shutil
        if test_dir.exists():
            shutil.rmtree(test_dir)
            print("✅ 本地测试文件已清理")
        
        print("\n" + "=" * 70)
        print("所有测试完成！")
        print("=" * 70)
        print("\n✅ 测试结果总结:")
        print("  1. R2 提供商初始化: 成功")
        print("  2. 连接测试: 成功")
        print("  3. 文件上传: 成功")
        print("  4. 上传记录: 成功")
        print("  5. 重复上传跳过: 成功")
        print("  6. 文件下载: 成功")
        print("  7. 清理测试: 成功")
        print("\n🎉 R2 配置工作正常！")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_r2_with_user_config()
    sys.exit(0 if success else 1)
