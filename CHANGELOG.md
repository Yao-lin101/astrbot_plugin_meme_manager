# 更新日志

## v3.19 - 2025-11-15

### 新增功能
- **混合消息发送功能**
  - 新增混合消息模式，文本和表情图片可以在同一条消息中发送
  - 添加 `enable_mixed_message` 配置项控制是否启用混合消息
  - 添加 `mixed_message_probability` 配置项控制混合消息发送概率（0-100）
  - 提升消息表达的丰富性和连贯性

### Bug 修复
- **R2 图床同步状态检查修复**
  - 修复同步状态检查时错误显示需要下载文件的问题
  - 解决本地文件与云端文件ID格式不匹配的问题（`memes/` 前缀处理）
  - 修复 R2 图床文件识别错误

### 功能优化
- **通用同步状态检查机制**
  - 新增 `_normalize_remote_id()` 方法支持不同图床提供商
  - 根据配置自动识别图床类型并应用相应的ID处理规则
  - 为未来新增图床提供商预留扩展接口
  - 在配置中添加 `provider` 字段用于标识图床类型

- **代码质量改进**
  - 修复 `logger` 未定义的问题
  - 修复 bare except 语句
  - 优化 f-string 使用，移除不必要的格式化前缀

### 技术改进
- 增强同步状态检查的兼容性和准确性
- 改进错误处理和日志记录
- 提升代码可维护性

## v3.18 - 2025-11-14

### Bug 修复
- **修复关键启动错误**
  - 修复 `AttributeError: 'MemeSender' object has no attribute 'logger'`
  - 修复同步进程配置传递错误 (`KeyError: 'key'`)
  - 添加缺失的 `__init__.py` 文件

- **表情包标签清理机制优化**
  - 修复 `&&emotion&&` 标签未被正确过滤的问题
  - 改进表情标签清理逻辑
  - 添加内容清理规则配置项

### 功能优化
- **R2 文件管理优化**
  - 所有文件上传到 `memes/` 文件夹，避免污染存储桶根目录
  - 只检查和同步 `memes/` 文件夹内的文件，提高安全性
  - 改进 S3 键名解析，正确处理 `memes/` 前缀

- **配置简化**
  - 简化 R2 配置 YAML，只保留核心配置项
  - 添加内容清理规则配置选项

## v3.17 - 2025-11-12

### 新增功能
- **智能上传记录机制**
  - 新增上传记录追踪器 (`upload_tracker.py`)
  - 自动记录已上传文件，避免重复上传
  - 上传记录文件: `.upload_tracker.json`
  - 支持重置上传记录（删除记录文件即可）

### 功能优化
- **R2 图床功能增强**
  - 修复 `public_url` 处理逻辑，支持自定义CDN域名
  - 移除不支持的 ACL 参数，适配 Cloudflare R2 API
  - 增强日志输出，便于故障排查
  - 添加 R2 连接测试和存储桶访问验证
  - 优化分类路径处理，保持本地目录结构
  - 支持 R2.dev 默认域名和自定义域名

- **同步逻辑优化**
  - 上传时跳过已上传文件，只上传新文件
  - 下载时跳过已存在文件，只下载缺失文件
  - 显示上传/下载进度和跳过数量
  - 简化同步状态检查，更直观的输出

### 新增文件
- `image_host/core/upload_tracker.py` - 上传记录追踪器
- `UPLOAD_TRACKER_README.md` - 上传记录功能说明
- `test_r2_function.py` - R2功能完整测试脚本
- `test_r2_persist.py` - R2持久上传测试脚本
- `check_r2_files.py` - 检查R2存储桶文件
- `test_r2_config.py` - R2配置测试工具

### 修改文件
- `image_host/providers/cloudflare_r2_provider.py` - 修复R2提供商
- `image_host/img_sync.py` - 集成上传记录功能
- `image_host/core/sync_manager.py` - 优化同步逻辑
- `main.py` - 改进R2配置处理

### 测试验证
- ✅ R2 提供商初始化成功
- ✅ 文件上传/下载功能正常
- ✅ 上传记录功能正常，重复上传自动跳过
- ✅ 公共URL生成正确，可通过CDN访问
- ✅ 与现有 Stardots 图床兼容

## v3.16 - 2025-11-11

### 新增功能
- **Cloudflare R2 图床支持**
  - 新增 Cloudflare R2 作为可选图床后端
  - 在配置中可以选择使用 Stardots 或 Cloudflare R2
  - 支持完整的 R2 图床功能：上传、删除、同步、状态检查

### 技术改进
- 重构图床提供者架构，支持多后端
- 添加图床提供者接口规范 (`image_host/interfaces/image_host.py`)
- 实现 Cloudflare R2 提供者 (`image_host/providers/cloudflare_r2_provider.py`)
- 更新配置架构 (`_conf_schema.json`) 支持 R2 配置项

### 配置说明
在插件配置中添加以下选项：
```yaml
image_host: "cloudflare_r2"  # 选择图床类型
image_host_config:
  cloudflare_r2:
    account_id: "your_account_id"           # Cloudflare Account ID
    access_key_id: "your_access_key_id"     # R2 API Access Key ID
    secret_access_key: "your_secret_access_key"  # R2 API Secret Access Key
    bucket_name: "your_bucket_name"         # R2 Bucket 名称
    public_url: "https://your-domain.com"   # 可选: CDN 域名
```

## v3.15 - 2025-11-11

### 功能
- 表情包管理器初始版本
- 支持 AI 自动发送表情包
- WebUI 管理界面
- Stardots 图床支持