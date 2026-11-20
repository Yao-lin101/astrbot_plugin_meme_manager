# 使用说明

[返回 README](../README.md) · [更新日志](../CHANGELOG.md) · [配置定义](../_conf_schema.json)

本文介绍配置、图库管理、检索规则和外部插件接口。

## 配置与管理入口

在 AstrBot 的插件管理中打开本插件的「表情包管理」页面。页面包含表情管理、标签合并、重复检测、同步管理和配置管理。

配置管理中的对应关系如下。配置项以当前 [_conf_schema.json](../_conf_schema.json) 为准，保存插件配置后会触发插件热重载。

| 页面 | 配置内容 |
| --- | --- |
| 人设管理 | 当前人格的使用偏好和收集偏好，保存在 `persona_settings` |
| 基础设置 | `enable_giftia_mode` |
| 交互设置 | `interaction_config` |
| 偷图与分类 | `auto_steal_config`、`multimodal_config` |
| 检索与去重 | `embedding_config`、`similarity_dedup_config` |
| 压缩设置 | `compression_config` |
| 图床设置 | `image_host`、`image_host_config` |
| 缓存清理 | 清理全部或孤立缩略图 |

### 检索与去重

以下字段分别位于 `embedding_config` 和 `similarity_dedup_config` 中。

| 配置项 | 默认值 | 作用 |
| --- | --- | --- |
| `embedding_provider_id` | 空 | 指定 Embedding 提供商，留空时使用第一个可用提供商 |
| `embedding_similarity_threshold` | `0.6` | 相似度达到该阈值的标签可以被召回 |
| `auto_tag_merge_threshold` | `0` | 收录时将新标签吸附到语义相近的已有标签；`0` 表示关闭 |
| `enable_similarity_dedup` | `true` | 收录或上传时进行图片相似度去重 |
| `similarity_dedup_threshold` | `0.85` | 图片相似度去重阈值 |

插件在本地 LanceDB 中缓存标签向量，并按余弦相似度检索。更换 Embedding 模型后，执行 `/表情管理 重构向量缓存`，等待后台重建完成再使用语义检索。新表按 Provider 实际返回的向量维度创建。重建期间或向量操作出错时，插件记录警告并继续按精确标签匹配。未配置 Embedding 时也支持精确匹配。

新标签自动合并依赖 Embedding 和已有标签向量，合并后直接使用已有标签。图片去重使用 dHash 和颜色直方图，支持对动图抽帧比较，与标签向量检索分别处理。

### 发送样式

以下字段位于 `interaction_config` 中。

| 配置项 | 默认值 | 作用 |
| --- | --- | --- |
| `convert_static_to_gif` | `false` | `send_meme` 发送时将静态图片转换为单帧 GIF |
| `meme_summaries` | `["这是一张表情包"]` | OneBot 表情图片的外显文字候选，发送时随机抽取 |

每张图片还可以设置 `send_mode`：`sticker` 为贴纸，`image` 为普通图片，默认 `sticker`。实际显示由平台适配器和客户端决定。

### 收录与多模态分析

以下字段分别位于 `auto_steal_config` 和 `multimodal_config` 中。

| 配置项 | 默认值 | 作用 |
| --- | --- | --- |
| `auto_steal_enabled` | `false` | 开启群聊被动收录 |
| `auto_steal_probability` | `30` | 被动收录触发概率，单位为百分比 |
| `auto_steal_min_seen` | `2` | 图片出现次数记录达到该值后再进行收录判定 |
| `meme_decision_provider_id` | 空 | 可选的收录判定决策模型，用于判断是否属于表情包、是否符合人格收集偏好；留空沿用原多模态判定 |
| `multimodal_llm_enabled` | `false` | 收录时自动生成标签和画面描述；被动收录需要开启此项 |
| `multimodal_llm_provider_id` | 空 | 指定图片理解模型，留空时使用当前会话模型 |
| `multimodal_tag_prompt` | 内置分析提示词 | 标签和描述生成指引，输出格式由程序附加 |

`steal_meme` 工具和群聊被动收录都会读取当前人格的收集偏好。未配置收集偏好时拒绝收录。开启或关闭自动分类，不会取消收集偏好判定。

在「配置管理 → 偷图与分类」中，可选择 `meme_decision_provider_id`，通过 AstrBot 通用的 `context.decision.ask()` 接口，在一次请求中判断「是否属于表情包」和「是否符合人格收集偏好」。两个结果的概率均达到 `0.5` 才允许继续收录；动图沿用最多 8 帧的抽帧流程。决策接口不返回自由文本理由，拒绝提示按未通过的判断生成。

**AstrBot 当前仅 Gemini 决策模型支持多模态适配**，请选择已在 AstrBot 中配置并启用的 Gemini 决策提供商。OpenAI 决策适配器目前仅支持文本和业务 JSON，不能用于此处的图片判定。配置留空时，继续通过 `multimodal_llm_provider_id` 指定的多模态聊天模型判定，未指定时使用当前会话模型。已配置决策模型但调用失败时，本次收录停止，不缓存拒绝结果，后续可以重试。

标签与画面描述的生成仍使用原来的多模态自动分类配置；群聊被动收录仍需开启 `multimodal_llm_enabled`。

### 压缩

以下字段位于 `compression_config` 中，作用于图片上传和收录。

| 配置项 | 默认值 | 作用 |
| --- | --- | --- |
| `enable_compression` | `true` | 开启自动压缩 |
| `compression_max_size_kb` | `1024` | 图片大小阈值，单位为 KB |
| `compression_max_width` | `1024` | 图片宽度限制，单位为像素 |
| `compression_quality` | `80` | 静态图片编码质量 |
| `compress_gif` | `false` | 开启动图压缩 |
| `compression_format` | `original` | 保存为原格式，或选择 `webp`、`avif` |

## 图库与人格偏好

表情包包含标签、画面描述、适用人格和发送样式。表情管理页面可上传、编辑、批量导入、删除或修改适用人格，并支持单张及批量 AI 分析标签和描述。

- **适用人格**：一张图可以绑定一个或多个人格；`*` 表示全局可用。检索只返回当前人格和全局可用的图片。
- **使用偏好**：在「配置管理 → 人设管理」维护标签列表。首个标签在候选评分时提供小幅加分；偏好标签也会加入该人格的可匹配标签集合。
- **收集偏好**：用自然语言描述希望收录的内容，供 `steal_meme` 和被动收录进行偏好判断。

使用偏好和收集偏好都由插件直接读取，不注入人格提示词。手动上传时可以自行指定标签和适用人格。

「标签合并」用于整理语义相近的标签，执行后同步更新图片标签、人格使用偏好和向量缓存。「重复检测」用于扫描相似图片并选择保留项。「缓存清理」处理缩略图文件。

## 检索与评分规则

工具、标签检索接口和指定人格的候选接口共用以下匹配逻辑。

1. 按人格过滤可用标签和图片，并排除本地文件已不存在的记录。
2. 按逗号、中文逗号或空白拆分查询，保留标签顺序。
3. 对每个标签执行忽略大小写的精确匹配；有可用 Embedding 时，同时召回达到阈值的相似标签。
4. 精确命中排在首位，每个查询标签另召回最多 5 个相似标签。
5. 根据有效查询标签的顺序、候选排名和人格使用偏好计算分数，按总分降序返回候选。

有效查询标签的权重依次为 **1000、400、200、100、50……**，最低为 1。对同一查询标签，一张图只计入其最佳匹配候选的分数；候选排名每后移一位，保留的分值减少 5%，最低保留 80%，计分时取整数。

人格使用偏好的首个标签仅提供额外加分，上限为 10，并低于末位有效查询标签的权重。标签语义匹配使用标签向量，画面描述用于向模型展示候选及分组，不作为独立的文本检索通道。

## 工具调用

### send_meme

模型使用两步调用来选择并发送图片：

```text
send_meme(query="猫猫, 开心")
send_meme(index=1)
```

第一次调用返回最多 8 张匹配图片形成的候选列表：有描述时按相同描述分组，没有描述时按相同标签集合分组。第二次调用中的 `index` 从 1 开始，指向候选组，工具随机发送该组中的一张图片。

候选按当前会话缓存。传入新的 `query` 会刷新该会话的候选；发送成功后清除缓存。找不到候选时工具返回提示，不随机发送其他图片。工具自行完成图片构造、可选的 GIF 转换和发送。

### steal_meme

`steal_meme` 用于下载并收录指定图片：

| 参数 | 说明 |
| --- | --- |
| `image_url` | 图片的 HTTP/HTTPS URL 或本地文件路径；Giftia 模式可使用图片哈希 |
| `categories` | 用户明确指定的标签列表；未指定标签时需开启多模态自动分类 |
| `category` | 单个标签参数，与 `categories` 二选一即可 |
| `description` | 用户明确指定的画面描述，可省略 |

收录时依次执行相似度去重、收集偏好判定、标签解析和入库；符合条件的图片绑定到当前人格。显式标签优先于自动分类。

## 外部插件接口

`sender` 指已加载的表情包管理器插件实例，可从 AstrBot 已加载插件的元数据 `star_cls` 获取。传入检索函数的是该实例，而非调用插件自身的实例。

### 按当前会话标签检索

模块路径：`backend.core.emotion_handler`。

```python
async def get_direct_trigger_memes(sender, event, raw_tags: list[str]) -> list[dict]:
    ...
```

该模块级函数通过 `event` 解析当前人格，按 `raw_tags` 的顺序查询，返回最多 8 张匹配图片的候选。空标签或无匹配时返回 `[]`，不会从无关图库中兜底取图，也不会发送消息。

候选中的字段如下：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | 整数 | 表情包数据库 ID |
| `filename` | 字符串 | 图库内文件名 |
| `emotions` | 字符串列表 | 图片标签 |
| `description` | 字符串 | 画面描述 |
| `send_mode` | 字符串 | `sticker` 或 `image` |
| `score` | 数值 | 检索匹配分数 |

异步调用示例。通过插件实例的模块路径导入检索模块：

```python
import importlib


async def send_tagged_meme(sender, event, tags: list[str]):
    package = type(sender).__module__.rsplit(".", 1)[0]
    handler = importlib.import_module(f"{package}.backend.core.emotion_handler")
    candidates = await handler.get_direct_trigger_memes(sender, event, tags)
    if not candidates:
        return

    image = sender.build_meme_component(candidates[0])
    if image is not None:
        await event.send(event.chain_result([image]))
```

### 指定人格和候选数量

插件实例提供以下异步方法，供 Giftia 等外部插件调用：

```python
async def get_candidate_memes(
    persona_id: str = "default",
    query: str = "",
    count: int = 5,
    event=None,
) -> list[dict]:
    ...
```

该方法使用显式传入的 `persona_id` 过滤图库，`event` 不替代该参数。当查询有匹配时返回评分最高的前 `count` 张候选；查询为空或没有匹配时，从该人格可用的图库中随机返回最多 `count` 张，兜底候选的 `score` 为 `0`。`count <= 0` 时返回空列表。候选字段与上表一致，方法内不发送消息。

### 按 ID 查询和构造组件

- `sender.get_meme_by_id(meme_id)`：返回单条数据库记录，ID 无效或不存在时返回 `None`。该接口返回的 `emotions` 和 `personas` 是原始的逗号分隔字符串，不是候选接口中的标签列表。
- `sender.build_meme_component(meme_id_or_dict)`：接受 ID 或候选字典，返回带发送样式和画面说明的 `Image` 组件；记录无效或本地文件不存在时返回 `None`。构造组件后仍需由调用方发送。

按 ID 查询和组件构造不承担人格筛选，调用方应使用已经筛选的候选或自行校验适用人格。`build_meme_component()` 不执行静态图转 GIF；外部插件如需转换，可调用 `backend.core.helpers.convert_to_gif(image_path, sender)`，发送完成后自行清理生成的临时 GIF。

### Giftia 配置

开启顶层配置 `enable_giftia_mode` 后，工具和会话标签检索优先按 Giftia 的机器人映射解析人格，`steal_meme` 的 `image_url` 参数描述改为图片哈希。候选检索、按 ID 查询和组件构造接口继续供接入插件使用，由接入插件决定发送时机。

## 图床同步

在「配置管理 → 图床设置」选择 `image_host`，再填写对应的 `image_host_config`。图床用于同步图片文件，本地管理和发送可以独立使用。

| 提供商 | `image_host` 值 | 配置路径和字段 |
| --- | --- | --- |
| Stardots | `stardots` | `image_host_config.stardots`：`key`、`secret`、`space` |
| Cloudflare R2 | `cloudflare_r2` | `image_host_config.cloudflare_r2`：`account_id`、`access_key_id`、`secret_access_key`、`bucket_name`，可选 `public_url` |

「同步管理」显示 LanceDB 缓存的向量维度、已向量化标签数量和重建状态。图床卡片提供云端状态、上传和下载入口，覆盖操作可通过下表中的管理指令执行。

同步仅处理扁平图库中的图片文件，忽略分类子目录；R2 的 `memes/` 是远端存储前缀。图片标签、描述、人格绑定等 SQLite 元数据不会随图床图片同步，完整备份需同时保存插件数据目录。

## 管理指令

| 指令 | 作用 |
| --- | --- |
| `/表情管理 查看图库` | 列出可用标签 |
| `/表情管理 图库统计` | 查看图片数量和标签统计 |
| `/表情管理 添加表情 标签1,标签2` | 在接下来的 30 秒内接收上传图片并设置标签 |
| `/表情管理 删除标签 标签名` | 删除标签归属，无剩余标签的图片会被删除 |
| `/表情管理 清空全部` | 清空图片、标签和向量缓存 |
| `/表情管理 重构向量缓存` | 清空旧向量缓存，按当前模型的实际维度重建 |
| `/表情管理 压缩现有表情` | 按压缩配置处理现有图片 |
| `/表情管理 同步状态` | 查看图床同步状态与本地标签统计 |
| `/表情管理 同步到云端` | 上传本地图片 |
| `/表情管理 从云端同步` | 下载远端图片 |
| `/表情管理 覆盖到云端` | 以本地图片为准同步，删除云端多出的图片 |
| `/表情管理 从云端覆盖` | 以云端图片为准同步，删除本地多出的图片 |

添加、删除、压缩、重构向量和同步写入操作需要管理员权限。删除标签及覆盖操作需要会话内确认，清空全部需要两次确认。

## 数据与升级范围

默认数据目录位于 AstrBot 数据目录下的 `plugin_data/meme_manager/`：

```text
meme_manager/
├── memes.db          # 图片记录、标签、人格绑定和图片查重缓存
├── lancedb/          # 标签向量及模型信息
├── memes_data.json   # 标签列表
├── memes/            # 扁平存储的图片文件
├── thumbnails/       # 缩略图缓存
├── temp/             # 临时文件
└── ui_settings.json  # 管理页面设置
```

支持 v4 起使用的 SQLite 与扁平图库，保留 4.x 内部的数据库字段和人格偏好升级。v4 之前的 `data/memes_data`、分类子目录及默认表情复制流程不再导入或迁移，旧目录保持原样。

升级后首次建 LanceDB 缓存时，插件会用当前 Embedding Provider 为图库中的标签后台补算向量。旧 SQLite 向量没有模型标识，因此重建以当前 Provider 的输出为准。

主 agent 的人格提示词、普通回复文本和发送后流程不会被本插件注入或改写。旧版人格黑名单、表情包系统提示词、最大表情数、发送概率、回复带图、流式兼容、情感模型和发送模式配置已移除；收录与管理过程中仍可按配置调用多模态模型。
