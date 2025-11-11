#!/usr/bin/env python3
"""
测试 Cloudflare R2 配置是否正确
"""

import sys
import json
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

def test_r2_config():
    """测试R2配置"""
    print("=" * 60)
    print("Cloudflare R2 配置测试工具")
    print("=" * 60)
    
    # 尝试从配置文件中读取
    config_file = Path("/root/astrbot/config.json")
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            print(f"\n✅ 找到配置文件: {config_file}")
            
            # 检查R2配置
            if "image_host_config" in config and "cloudflare_r2" in config["image_host_config"]:
                r2_config = config["image_host_config"]["cloudflare_r2"]
                print("\n📋 R2 配置信息:")
                print(f"  - Account ID: {r2_config.get('account_id', '未设置')[:10]}...")
                print(f"  - Access Key ID: {r2_config.get('access_key_id', '未设置')[:10]}...")
                print(f"  - Secret Access Key: {'已设置' if r2_config.get('secret_access_key') else '未设置'}")
                print(f"  - Bucket Name: {r2_config.get('bucket_name', '未设置')}")
                print(f"  - Public URL: {r2_config.get('public_url', '未设置')}")
                
                # 测试连接
                print("\n🔌 测试R2连接...")
                try:
                    from image_host.providers.cloudflare_r2_provider import CloudflareR2Provider
                    provider = CloudflareR2Provider(r2_config)
                    print("✅ R2 连接成功！")
                    
                    # 测试获取文件列表
                    print("\n📂 测试获取文件列表...")
                    files = provider.get_image_list()
                    print(f"✅ 获取到 {len(files)} 个文件")
                    if files:
                        print(f"  示例: {files[0]}")
                    
                    return True
                    
                except Exception as e:
                    print(f"❌ 连接失败: {e}")
                    return False
            else:
                print("\n❌ 配置文件中未找到 cloudflare_r2 配置")
                return False
                
        except Exception as e:
            print(f"❌ 读取配置文件失败: {e}")
            return False
    else:
        print(f"❌ 配置文件不存在: {config_file}")
        return False

if __name__ == "__main__":
    success = test_r2_config()
    sys.exit(0 if success else 1)
