# 分支管理规范

## 主要分支

### `main` 分支（主分支）
- **用途**: 生产环境代码，稳定版本
- **保护**: 受保护分支，直接推送需要权限
- **更新**: 只能通过 PR/Merge 从功能分支合并

### `cloudflare-r2` 分支（功能开发分支）
- **用途**: Cloudflare R2 图床相关功能的开发和测试
- **创建**: 2025-11-12，从 main 分支创建
- **用途说明**: 所有与 Cloudflare R2 相关的修改、测试、优化都在此分支进行

## 工作流程

### 1. 开发新功能或修改

```bash
# 切换到 cloudflare-r2 分支
git checkout cloudflare-r2

# 创建特性分支（可选，用于更大功能的开发）
git checkout -b feature/your-feature-name

# 进行修改和测试
# ... 你的修改 ...

# 提交修改
git add .
git commit -m "feat: 描述你的修改"
```

### 2. 测试验证

在 `cloudflare-r2` 分支上进行充分测试：
- 运行测试脚本：`uv run test_r2_function.py`
- 验证功能是否正常工作
- 检查日志输出是否正确

### 3. 合并到主分支

当测试通过后，合并到 main 分支：

```bash
# 切换到 main 分支
git checkout main

# 拉取最新代码
git pull origin main

# 合并 cloudflare-r2 分支
git merge cloudflare-r2

# 解决冲突（如果有）
# ... 解决冲突 ...

# 推送到远程
git push origin main
```

### 4. 同步主分支到功能分支

main 分支更新后，同步到 cloudflare-r2 分支：

```bash
# 切换到 cloudflare-r2 分支
git checkout cloudflare-r2

# 合并 main 分支的最新更改
git merge main

# 推送到远程
git push origin cloudflare-r2
```

## 提交规范

### Commit 类型
- `feat`: 新功能
- `fix`: 修复bug
- `docs`: 文档更新
- `style`: 代码格式调整
- `refactor`: 代码重构
- `test`: 测试相关
- `chore`: 构建过程或辅助工具的变动

### 格式示例
```bash
git commit -m "feat: 添加 R2 上传记录功能

- 新增 upload_tracker.py 记录已上传文件
- 避免重复上传相同文件
- 支持重置上传记录"
```

## 注意事项

1. **不要在 main 分支直接开发**：所有开发工作都在 cloudflare-r2 分支进行

2. **充分测试后再合并**：确保 cloudflare-r2 分支的代码稳定后再合并到 main

3. **保持分支同步**：定期将 main 分支的更新合并到 cloudflare-r2，避免分支差异过大

4. **代码审查**：重要功能合并前建议进行代码审查

5. **版本号管理**：在合并到 main 分支时更新版本号

6. **清理测试脚本**：合并到 main 分支前，必须清理测试脚本！
   
   测试脚本（test_r2_*.py, check_r2_files.py 等）只应在 cloudflare-r2 分支保留，不应该提交到 main 分支。
   
   **清理步骤**:
   ```bash
   # 在 main 分支执行
   git checkout main
   rm test_r2_*.py check_r2_files.py UPLOAD_TRACKER_README.md
   
   # 确保 .gitignore 已包含测试脚本规则
   # 已添加: test_r2_*.py, check_r2_files.py, UPLOAD_TRACKER_README.md
   ```
   
   这些测试文件仅在 cloudflare-r2 分支用于开发和测试，main 分支应保持干净，只包含生产代码。

## 当前分支状态

- **主分支**: `main` (v3.17)
- **功能分支**: `cloudflare-r2` (用于 R2 相关功能开发)
- **最新更新**: 2025-11-12

## 相关文件

- `.gitignore` - 确保测试文件不被提交
- `test_r2_*.py` - R2 功能测试脚本
- `UPLOAD_TRACKER_README.md` - 上传记录功能说明
