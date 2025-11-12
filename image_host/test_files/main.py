import argparse
import json
import time
from pathlib import Path
from providers.stardots_provider import StarDotsProvider
from providers.cloudflare_r2_provider import CloudflareR2Provider
from core.sync_manager import SyncManager
from typing import Dict

class ImageSyncCLI:
    """图床同步工具命令行接口"""
    
    def __init__(self, config_path: str = 'config.json'):
        self.config = self._load_config(config_path)
        self.provider = self._init_provider()
        self.sync_manager = SyncManager(
            image_host=self.provider,
            local_dir=Path(self.config['local_dir'])
        )
    
    def _init_provider(self):
        """根据配置初始化图床提供者"""
        provider_type = self.config.get('provider', 'stardots')
        
        if provider_type == 'stardots':
            return StarDotsProvider(self.config['stardots'])
        elif provider_type == 'cloudflare_r2':
            return CloudflareR2Provider(self.config['cloudflare_r2'])
        else:
            raise ValueError(f"不支持的图床提供者: {provider_type}")
    
    def _load_config(self, config_path: str) -> Dict:
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
                # 验证必要的配置项
                if 'provider' not in config:
                    config['provider'] = 'stardots'  # 默认使用stardots
                
                if 'local_dir' not in config:
                    raise ValueError(f"配置文件缺少必要的配置项: local_dir")
                
                # 根据提供者验证配置
                provider_type = config.get('provider', 'stardots')
                
                if provider_type == 'stardots':
                    if 'stardots' not in config:
                        raise ValueError("配置了stardots提供者但缺少stardots配置")
                    stardots_required = ['key', 'secret', 'space']
                    for key in stardots_required:
                        if key not in config['stardots']:
                            raise ValueError(f"StarDots配置缺少必要的配置项: {key}")
                
                elif provider_type == 'cloudflare_r2':
                    if 'cloudflare_r2' not in config:
                        raise ValueError("配置了cloudflare_r2提供者但缺少cloudflare_r2配置")
                    r2_required = ['account_id', 'access_key_id', 'secret_access_key', 'bucket_name']
                    for key in r2_required:
                        if key not in config['cloudflare_r2']:
                            raise ValueError(f"Cloudflare R2配置缺少必要的配置项: {key}")
                
                else:
                    raise ValueError(f"不支持的图床提供者: {provider_type}")
                        
                return config
        except FileNotFoundError:
            raise FileNotFoundError(f"配置文件 {config_path} 不存在")
    
    def check_status(self) -> None:
        """检查同步状态"""
        print("正在检查同步状态...")
        status = self.sync_manager.check_sync_status()
        
        print("\n=== 同步状态 ===")
        print(f"需要上传的文件: {len(status['to_upload'])} 个")
        for file in status['to_upload']:
            print(f"  - {file['filename']}")
            
        print(f"\n需要下载的文件: {len(status['to_download'])} 个")
        for file in status['to_download']:
            print(f"  - {file['filename']}")
            
        print(f"\n需要删除的本地文件: {len(status['to_delete_local'])} 个")
        for file in status['to_delete_local']:
            print(f"  - {file['filename']}")
            
        print(f"\n需要删除的远程文件: {len(status['to_delete_remote'])} 个")
        for file in status['to_delete_remote']:
            print(f"  - {file['filename']}")
    
    def sync_to_remote(self) -> None:
        """同步到远程"""
        print("正在同步到远程...")
        try:
            self.sync_manager.sync_to_remote()
            print("同步完成！")
        except Exception as e:
            print(f"同步失败: {str(e)}")
    
    def sync_from_remote(self) -> None:
        """从远程同步"""
        print("正在从远程同步...")
        try:
            self.sync_manager.sync_from_remote()
            print("同步完成！")
        except Exception as e:
            print(f"同步失败: {str(e)}")
    
    def auto_sync(self, interval: int = 300) -> None:
        """自动同步
        
        Args:
            interval: 同步间隔（秒），默认5分钟
        """
        print(f"启动自动同步，间隔 {interval} 秒")
        try:
            while True:
                print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] 开始同步...")
                self.sync_to_remote()
                self.sync_from_remote()
                print(f"等待 {interval} 秒后进行下一次同步...")
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n自动同步已停止")

def main():
    parser = argparse.ArgumentParser(description='图床同步工具')
    parser.add_argument('--config', default='config.json', help='配置文件路径')
    parser.add_argument('action', choices=['check', 'upload', 'download', 'auto'],
                      help='执行的操作：check-检查状态，upload-上传到远程，download-从远程下载，auto-自动同步')
    parser.add_argument('--interval', type=int, default=300,
                      help='自动同步的间隔时间（秒），默认300秒')
    
    args = parser.parse_args()
    
    try:
        cli = ImageSyncCLI(args.config)
        
        if args.action == 'check':
            cli.check_status()
        elif args.action == 'upload':
            cli.sync_to_remote()
        elif args.action == 'download':
            cli.sync_from_remote()
        elif args.action == 'auto':
            cli.auto_sync(args.interval)
            
    except Exception as e:
        print(f"错误: {str(e)}")
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main()) 