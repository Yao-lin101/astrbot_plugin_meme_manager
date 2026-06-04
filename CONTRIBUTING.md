# 协作开发规则

> **本文档是给 AI 编程助手（如 Gemini/DeepSeek/Claude）阅读和遵循的协作开发规则。**
> 把它作为项目上下文 / 系统提示喂给 AI，让 AI 在改动本仓库时严格按以下规则操作。
> 规则以「可执行、不二义」为目标：能照抄的命令就照抄，需要判断的地方给了明确判定条件。

- 仓库：`astrbot_plugin_meme_manager`（AstrBot 插件，从原项目 Fork）
- 维护者：独力维护（`Yao-lin101`）
- 仓库地址：https://github.com/Yao-lin101/astrbot_plugin_meme_manager

---

## 0. 最高优先级规则（违反任何一条都算错误）

1. **任何改动开始前，先同步最新 `main`**：`git checkout main && git pull origin main`。基于旧代码开发是冲突的头号原因。
2. **不使用 `dev` 或任何长期分支。** 不要创建、不要维护、不要往 `dev` 提交。需要分支时，从最新 `main` 临时切出，合并后立即删除。
3. **删除或重命名任何函数 / 接口 / 字段前，必须全局搜索所有调用方并一并修改**：使用 grep 或 IDE 全局搜索。前后端、调用方与定义必须保持一致。
4. **推送前必须本地验证通过**（包含运行 `ruff` 检查和实际功能验证，见 [第 4 节](#4-推送前必须执行的自检)）。
5. **版本一致性**：发版时必须同步修改三处版本号（见 [第 5 节](#5-发版版本号三处必须同步)）。

---

## 1. 工作方式：什么时候直接推 main，什么时候开临时分支

虽然是单人维护的 Fork 仓库，但为了保持提交历史整洁和便于追踪，仍建议采用以下规范。

### 路径 A —— 直接提交到 `main`（仅限「小修复」）

**同时满足以下全部条件**，才算「小修复」，可直接推 `main`：
- 改动集中在 1～2 个文件，且不超过几十行；
- **不**改动公共接口、函数签名、配置 schema（`_conf_schema.json`）、数据库结构；
- 本地已编译 + 验证通过。

操作：
```bash
git checkout main
git pull --rebase origin main        # 先拉最新，避免冲突
# ...改代码...
# ...验证并执行 ruff 检查...
git add <文件> && git commit -m "fix: 简短描述"
git pull --rebase origin main        # 推送前再同步一次
git push origin main
```

### 路径 B —— 开临时分支 + PR/合并（其余所有情况）

**只要不满足「小修复」全部条件，就走这里**：新功能、重构、改接口 / schema / 数据结构、改动较大。

```bash
git checkout main && git pull origin main
git checkout -b feat/简短英文描述         # 见第 2 节命名规范
# ...改代码 + 多次小步提交...
# ...自检并通过 ruff check/format ...
git push -u origin feat/简短英文描述
# 然后在 GitHub 上向 main 发起 PR / 合并，写清改动内容
```

合并后清理临时分支：
```bash
git checkout main && git pull origin main
git branch -d feat/简短英文描述
git push origin --delete feat/简短英文描述
```

---

## 2. 提交信息与分支命名

### Commit 信息：`类型: 简短描述`

```
feat: 新增缓存最近图片 fallback 收录功能
fix: 修复 send_meme 二次调用缺少 query 报错
docs: 补充协作规则文档
refactor: 重构 steal_meme 逻辑并拆分子模块
```

- 常用类型：`feat`/`fix`/`docs`/`refactor`/`style`/`perf`/`chore`。
- ❌ 禁止：`更新`、`改了点东西`、`111` 这类无意义信息。
- ❌ **禁止在 commit 信息开头带 ` ``` ` 反引号**。

### 分支命名：`类型/简短英文描述`

`feat/tag-vectorization`、`fix/llm-tool-query`、`refactor/tag-only-retrieval`、`docs/contributing`。

---

## 3. 同步 main 与解决冲突

功能分支落后于 `main` 需要更新时：
```bash
git fetch origin
git rebase origin/main
# 如有冲突，解决后：
git add <冲突文件> && git rebase --continue
git push --force-with-lease origin <你的分支>    # 仅对自己的临时分支使用
```

---

## 4. 推送前必须执行的自检

每次推送前，逐项确认：

- [ ] **代码格式与风格检查**：必须在插件目录下使用 AstrBot 虚拟环境的 ruff 格式化并检查所有 Python 代码。
  ```bash
  # 格式化
  <AstrBot_Path>/.venv/bin/ruff format .
  # 静态检查与自动修复
  <AstrBot_Path>/.venv/bin/ruff check --fix .
  ```
- [ ] **功能已实际验证**：改了 WebUI（如 `pages/` 下的内容）→ 打开管理面板点一遍对应标签页；改了逻辑/工具 → 在 AstrBot 中实测对应场景，确保能正常发送、收录和匹配。
- [ ] **关联处已同步**：改了函数/接口/字段名，调用方（含前端 JS / 模块间调用）已一并改动。
- [ ] **配置与前端管理页面已同步**：若修改了 `_conf_schema.json` 中的配置项，需确认管理面板前端是否也需要对应的交互和显示适配。
- [ ] **未夹带**无关文件、调试 `print`、临时代码。

---

## 5. 发版：版本号三处必须同步

发布新版本时，以下三处版本号**必须一起修改**，漏一处就会导致版本不一致：

1. **`metadata.yaml`** 的 `version` 属性
2. **`main.py`** 中 `@register(...)` 装饰器的第四个参数
3. **`README.md`** 顶部的目录索引与 `## 📜 更新日志` 尾部新增的本次变更条目

---

## 6. 禁止清单（高频翻车点，直接对照）

| ❌ 禁止 | ✅ 正确做法 |
|---|---|
| 基于旧代码开干 | 开工前先 `git pull origin main` |
| 直接修改/回退别人或上游已合并的改动 | 仔细确认，不擅自改回 |
| 删/改函数却漏改调用方 | 全局搜索找全调用方一起改 |
| 配置项变更漏改 schema/管理页面 | 同步修改 `_conf_schema.json` 及 WebUI 页面 |
| 只改一处版本号 | 三处同步（第 5 节） |
| commit 信息无意义 | 遵循 `类型: 简短描述` 规范 |
| 冲突标记残留就提交 | 提交前搜索确认无 `<<<<<<<` |
