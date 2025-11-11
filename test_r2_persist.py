#!/usr/bin/env python3
"""
测试 Cloudflare R2 - 上传一个持久文件到存储桶
这个测试会保留上传的文件，方便在R2控制台查看
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

def test_r2_persistent_upload():
    """上传一个持久文件到R2，不删除"""
    print("=" * 70)
    print("Cloudflare R2 持久上传测试")
    print("=" * 70)
    print("\n⚠️  这个测试会保留上传的文件，请手动在R2控制台查看")
    
    # 用户提供的配置
    r2_config = {
        "account_id": "8f9052f99abfe069e1b09732df19cc88",
        "access_key_id": "cb5d78d1db08e88c57a04b8eb5100847",
        "secret_access_key": "d47fef6bf20cff81654db815c07b862ff323de2d7da5ed59cb47d4f0c02eaf21",
        "bucket_name": "piexian",
        "public_url": "https://r2.pieixan.icu"
    }
    
    try:
        # 初始化R2提供商
        print("\n初始化 R2 提供商...")
        from image_host.providers.cloudflare_r2_provider import CloudflareR2Provider
        provider = CloudflareR2Provider(r2_config)
        print("✅ R2 提供商初始化成功")
        
        # 获取当前文件列表
        print("\n获取当前存储桶文件列表...")
        files_before = provider.get_image_list()
        print(f"当前存储桶中有 {len(files_before)} 个文件")
        
        # 创建测试图片
        print("\n创建测试图片...")
        test_dir = Path("/tmp/r2_persistent_test")
        test_dir.mkdir(exist_ok=True)
        test_file = test_dir / "astrbot_r2_test.jpg"
        
        from PIL import Image
        import numpy as np
        
        # 创建一个带文字标识的图片
        img_array = np.zeros((200, 400, 3), dtype=np.uint8)
        img_array[:, :] = [0, 120, 255]  # 蓝色背景
        img_array[50:150, 50:350] = [255, 255, 255]  # 白色中心
        
        test_img = Image.fromarray(img_array)
        test_img.save(test_file)
        
        file_size = test_file.stat().st_size
        print(f"✅ 创建测试图片: {test_file}")
        print(f"   文件大小: {file_size} bytes")
        
        # 上传测试图片
        print("\n上传测试图片到R2...")
        result = provider.upload_image(test_file)
        
        print(f"\n✅ 上传成功!")
        print(f"   文件名: {result['filename']}")
        print(f"   远程路径: {result['id']}")
        print(f"   公共URL: {result['url']}")
        print(f"   分类: {result.get('category', '无')}")
        
        # 验证上传
        print("\n验证上传结果...")
        files_after = provider.get_image_list()
        print(f"上传后存储桶中有 {len(files_after)} 个文件")
        
        if len(files_after) > len(files_before):
            print("✅ 文件已成功上传到R2存储桶")
            
            # 查找新上传的文件
            new_files = [f for f in files_after if f['id'] == result['id']]
            if new_files:
                new_file = new_files[0]
                print(f"\n📁 新上传的文件信息:")
                print(f"   - 文件名: {new_file['filename']}")
                print(f"   - 完整路径: {new_file['id']}")
                print(f"   - 访问URL: {new_file['url']}")
                
                # 测试URL是否可访问
                import urllib.request
                try:
                    print(f"\n测试URL访问性...")
                    urllib.request.urlopen(new_file['url'], timeout=10)
                    print(f"✅ URL可正常访问")
                except Exception as e:
                    print(f"⚠️  URL访问测试失败: {e}")
                    print(f"   请检查R2存储桶的公共访问权限是否开启")
        else:
            print("❌ 文件数量没有变化，上传可能失败")
        
        # 清理本地文件（保留远程文件）
        print(f"\n清理本地测试文件...")
        import shutil
        if test_dir.exists():
            shutil.rmtree(test_dir)
            print("✅ 本地测试文件已清理")
        
        print("\n" + "=" * 70)
        print("测试完成！")
        print("=" * 70)
        print(f"\n📌 重要信息:")
        print(f"   文件已上传到: {r2_config['bucket_name']} 存储桶")
        print(f"   文件名: {result['filename']}")
        print(f"   完整路径: {result['id']}")
        print(f"   公共URL: {result['url']}")
        print(f"\n🔍 请在 Cloudflare R2 控制台查看:")
        print(f"   1. 登录 https://dash.cloudflare.com/")
        print(f"   2. 进入 R2")
        print(f"   3. 打开 '{r2_config['bucket_name']}' 存储桶")
        print(f"   4. 查找文件: {result['id']}")
        print(f"\n⚠️  如果看不到文件，请检查:")
        print(f"   - 存储桶的公共访问权限是否开启")
        print(f"   - 是否需要刷新R2控制台页面")
        print(f"   - 文件名是否包含特殊字符")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_r2_persistent_upload()
    sys.exit(0 if success else 1)
