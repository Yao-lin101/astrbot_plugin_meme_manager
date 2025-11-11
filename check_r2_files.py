#!/usr/bin/env python3
"""
检查R2存储桶中的所有文件
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

# R2配置
config = {
    'account_id': '8f9052f99abfe069e1b09732df19cc88',
    'access_key_id': 'cb5d78d1db08e88c57a04b8eb5100847',
    'secret_access_key': 'd47fef6bf20cff81654db815c07b862ff323de2d7da5ed59cb47d4f0c02eaf21',
    'bucket_name': 'piexian',
    'public_url': 'https://r2.pieixan.icu'
}

try:
    from image_host.providers.cloudflare_r2_provider import CloudflareR2Provider
    
    print("=" * 70)
    print("检查 R2 存储桶文件")
    print("=" * 70)
    
    provider = CloudflareR2Provider(config)
    files = provider.get_image_list()
    
    print(f"\n存储桶 '{config['bucket_name']}' 中共有 {len(files)} 个文件:\n")
    
    if files:
        for i, f in enumerate(files, 1):
            print(f"{i}. {'='*60}")
            print(f"   文件名: {f['filename']}")
            print(f"   路径: {f['id']}")
            print(f"   URL: {f['url']}")
            print(f"   分类: {f.get('category', '无')}")
    else:
        print("存储桶为空")
    
    print("\n" + "=" * 70)
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
