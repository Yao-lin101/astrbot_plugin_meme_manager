import re
import os
import io
import random
import logging
import json
import time
import aiohttp
import ssl
import imghdr
import copy
from PIL import Image
import asyncio
from multiprocessing import Process
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.provider import LLMResponse
from astrbot.api.message_components import *
from astrbot.api.event.filter import EventMessageType
from astrbot.api.event import ResultContentType
from astrbot.core.message.components import Plain
from astrbot.api.all import *
from astrbot.core.message.message_event_result import MessageChain
from astrbot.api.provider import Personality
from .webui import run_server, ServerState
from .utils import get_public_ip, generate_secret_key, dict_to_string, load_json
from .image_host.img_sync import ImageSync
from .config import MEMES_DIR, MEMES_DATA_PATH, DEFAULT_CATEGORY_DESCRIPTIONS
from .backend.category_manager import CategoryManager
from .init import init_plugin


@register(
    "meme_manager_test", "anka", "anka - 表情包管理器 - 支持表情包发送及表情包上传", "2.0"
)
class MemeSender(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}
        
        # 初始化插件
        if not init_plugin():
            raise RuntimeError("插件初始化失败")
        
        # 初始化类别管理器
        self.category_manager = CategoryManager()
        
        # 初始化图床同步客户端
        self.img_sync = None
        if self.config.get("image_host") == "stardots":
            stardots_config = self.config.get("image_host_config", {}).get("stardots", {})
            if stardots_config.get("key") and stardots_config.get("secret"):
                self.img_sync = ImageSync(
                    config={
                        "key": stardots_config["key"],
                        "secret": stardots_config["secret"],
                        "space": stardots_config.get("space", "memes")
                    },
                    local_dir=MEMES_DIR
                )

        # 用于管理服务器
        self.webui_process = None

        self.server_key = None
        self.server_port = self.config.get("webui_port", 5000)


        # 初始化表情状态
        self.found_emotions = []  # 存储找到的表情
        self.upload_states = {}   # 存储上传状态：{user_session: {"category": str, "expire_time": float}}
        self.pending_images = {}  # 存储待发送的图片

        # 初始化 logger
        self.logger = logging.getLogger(__name__)
        
        # 处理人格
        self.prompt_head = self.config.get("prompt").get("prompt_head")
        self.prompt_tail_1 = self.config.get("prompt").get("prompt_tail_1")
        self.prompt_tail_2 = self.config.get("prompt").get("prompt_tail_2")
        self.max_emotions_per_message = self.config.get("max_emotions_per_message")
        self.emotions_probability = self.config.get("emotions_probability")
        self.strict_max_emotions_per_message = self.config.get("strict_max_emotions_per_message")
        
        # 更新人格
        personas = self.context.provider_manager.personas
        self.persona_backup = copy.deepcopy(personas)
        self._reload_personas()

    @filter.command_group("表情管理")
    def meme_manager(self):
        """表情包管理命令组:
        开启管理后台
        关闭管理后台
        查看图库
        添加表情
        同步状态
        同步到云端
        从云端同步
        """
        pass


    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("开启管理后台")
    async def start_webui(self, event: AstrMessageEvent):
        """启动表情包管理服务器"""
        yield event.plain_result("🚀 正在启动管理后台，请稍等片刻～")

        try:
            state = ServerState()
            state.ready.clear()

            # 生成秘钥
            self.server_key = generate_secret_key(8)
            self.server_port = self.config.get("webui_port", 5000)

            # 检查端口占用情况
            if await self._check_port_active():
                yield event.plain_result("🔧 检测到端口占用，正在尝试自动释放...")
                await self._shutdown()
                await asyncio.sleep(1)  # 等待系统释放端口

            config_for_server = {
                "img_sync": self.img_sync,
                "category_manager": self.category_manager,
                "webui_port": self.server_port,
                "server_key": self.server_key
            }
            self.webui_process = Process(target=run_server, args=(config_for_server,))
            self.webui_process.start()

            # 等待服务器就绪（轮询检测端口激活）
            for i in range(10):
                if await self._check_port_active():
                    break
                await asyncio.sleep(1)
            else:
                raise RuntimeError("⌛ 启动超时，请检查防火墙设置")

            # 获取公网IP并返回结果
            public_ip = await get_public_ip()
            yield event.plain_result(
                f"✨ 管理后台已就绪！\n"
                f"━━━━━━━━━━━━━━\n"
                f"表情包管理服务器已启动！\n"
                f"🔗 访问地址：http://{public_ip}:{self.server_port}\n"
                f"🔑 临时密钥：{self.server_key} （本次有效）\n"
                f"⚠️ 请勿分享给未授权用户"
            )

        except Exception as e:
            self.logger.error(f"启动失败: {str(e)}")
            yield event.plain_result(f"⚠️ 后台启动失败，请稍后重试\n（错误代码：{str(e)}）")
            await self._cleanup_resources()


    async def _check_port_active(self):
        """验证端口是否实际已激活"""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection('127.0.0.1', self.server_port),
                timeout=1
            )
            writer.close()
            return True
        except:
            return False


    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("关闭管理后台")
    async def stop_server(self, event: AstrMessageEvent):
        """关闭表情包管理服务器的指令"""
        yield event.plain_result("🚪 管理后台正在关闭，稍后见~ ✨")
        
        try:
            await self._shutdown()
            yield event.plain_result("✅ 服务器已关闭")
        except Exception as e:
            yield event.plain_result(f"❌ 安全关闭失败: {str(e)}")
        finally:
            await self._cleanup_resources()
        
    async def _shutdown(self):
        if self.webui_process:
            self.webui_process.terminate()
            self.webui_process.join()

    async def _cleanup_resources(self):
        if self.img_sync:
            self.img_sync.stop_sync()
        self.server_key = None
        self.server_port = None
        if self.webui_process:
            if self.webui_process.is_alive():
                self.webui_process.terminate()
                self.webui_process.join()
        self.webui_process = None
        self.logger.info("资源清理完成")

    def _reload_personas(self):
        """重新注入人格"""
        self.category_mapping = load_json(MEMES_DATA_PATH, DEFAULT_CATEGORY_DESCRIPTIONS)
        self.category_mapping_string = dict_to_string(self.category_mapping)
        self.sys_prompt_add = self.prompt_head + self.category_mapping_string + self.prompt_tail_1 + str(self.max_emotions_per_message) + self.prompt_tail_2
        personas = self.context.provider_manager.personas
        for persona, persona_backup in zip(personas, self.persona_backup):
            persona["prompt"] =  persona_backup["prompt"] + self.sys_prompt_add

    @meme_manager.command("查看图库")
    async def list_emotions(self, event: AstrMessageEvent):
        """查看所有可用表情包类别"""
        descriptions = self.category_mapping
        categories = "\n".join([
            f"- {tag}: {desc}" 
            for tag, desc in descriptions.items()
        ])
        yield event.plain_result(f"🖼️ 当前图库：\n{categories}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("添加表情")
    async def upload_meme(self, event: AstrMessageEvent, category: str = None):
        """上传表情包到指定类别"""
        if not category:
            yield event.plain_result(
                "📌 若要添加表情，请按照此格式操作：\n/表情管理 添加表情 [类别名称]\n（输入/查看图库 可获取类别列表）"
            )
            return

        if category not in self.category_manager.get_descriptions():
            yield event.plain_result(
                f"您输入的表情包类别「{category}」是无效的哦。\n可以使用/查看表情包来查看可用的类别。"
            )
            return

        user_key = f"{event.session_id}_{event.get_sender_id()}"
        self.upload_states[user_key] = {
            "category": category,
            "expire_time": time.time() + 30,
        }
        yield event.plain_result(
            f"请在30秒内发送要添加到【{category}】类别的图片（可发送多张图片）。"
        )

    @filter.event_message_type(EventMessageType.ALL)
    async def handle_upload_image(self, event: AstrMessageEvent):
        """处理用户上传的图片"""
        user_key = f"{event.session_id}_{event.get_sender_id()}"
        upload_state = self.upload_states.get(user_key)

        if not upload_state or time.time() > upload_state["expire_time"]:
            if user_key in self.upload_states:
                del self.upload_states[user_key]
            return

        images = [c for c in event.message_obj.message if isinstance(c, Image)]

        if not images:
            yield event.plain_result("请发送图片文件来进行上传哦。")
            return

        category = upload_state["category"]
        save_dir = os.path.join(MEMES_DIR, category)

        try:
            os.makedirs(save_dir, exist_ok=True)
            saved_files = []

            # 创建忽略 SSL 验证的上下文
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            for idx, img in enumerate(images, 1):
                timestamp = int(time.time())

                try:
                    # 特殊处理腾讯多媒体域名
                    if "multimedia.nt.qq.com.cn" in img.url:
                        insecure_url = img.url.replace("https://", "http://", 1)
                        self.logger.warning(
                            f"检测到腾讯多媒体域名，使用 HTTP 协议下载: {insecure_url}"
                        )
                        async with aiohttp.ClientSession() as session:
                            async with session.get(insecure_url) as resp:
                                content = await resp.read()
                    else:
                        async with aiohttp.ClientSession(
                            connector=aiohttp.TCPConnector(ssl=ssl_context)
                        ) as session:
                            async with session.get(img.url) as resp:
                                content = await resp.read()

                    file_type = imghdr.what(None, h=content)
                    if not file_type:
                        try:
                            with Image.open(io.BytesIO(content)) as temp_img:
                                temp_img.verify()  # 验证文件完整性
                                file_type = temp_img.format.lower()
                        except Exception as e:
                            self.logger.error(f"图片格式检测失败: {str(e)}")
                            file_type = "unknown"

                    ext_mapping = {
                        "jpeg": ".jpg",
                        "png": ".png",
                        "gif": ".gif",
                        "webp": ".webp",
                    }
                    ext = ext_mapping.get(file_type, ".bin")
                    filename = f"{timestamp}_{idx}{ext}"
                    save_path = os.path.join(save_dir, filename)

                    with open(save_path, "wb") as f:
                        f.write(content)
                    saved_files.append(filename)

                except Exception as e:
                    self.logger.error(f"下载图片失败: {str(e)}")
                    yield event.plain_result(f"文件 {img.url} 下载失败啦: {str(e)}")
                    continue

            del self.upload_states[user_key]
            result_msg = [
                Plain(f"✅ 已经成功收录了 {len(saved_files)} 张新表情到「{category}」图库！")
            ]
            yield event.chain_result(result_msg)
            await self.reload_emotions()

        except Exception as e:
            yield event.plain_result(f"保存失败了：{str(e)}")

    async def reload_emotions(self):
        """动态加载表情配置"""
        config_path = os.path.join(MEMES_DATA_PATH)
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                self.category_manager.update_descriptions(json.load(f))

    def _check_meme_directories(self):
        """检查表情包目录是否存在并且包含图片"""
        self.logger.info(f"开始检查表情包根目录: {MEMES_DIR}")
        if not os.path.exists(MEMES_DIR):
            self.logger.error(f"表情包根目录不存在，请检查: {MEMES_DIR}")
            return

        for emotion in self.category_manager.get_descriptions().values():
            emotion_path = os.path.join(MEMES_DIR, emotion)
            if not os.path.exists(emotion_path):
                self.logger.error(f"表情分类 {emotion} 对应的目录不存在，请查看: {emotion_path}")
                continue

            memes = [
                f
                for f in os.listdir(emotion_path)
                if f.endswith((".jpg", ".png", ".gif"))
            ]
            if not memes:
                self.logger.error(f"表情分类 {emotion} 对应的目录为空: {emotion_path}")
            else:
                self.logger.info(f"表情分类 {emotion} 对应的目录 {emotion_path} 包含 {len(memes)} 个图片")

    @filter.on_llm_response(priority=99999)
    async def resp(self, event: AstrMessageEvent, response: LLMResponse):
        """处理 LLM 响应，识别表情, 注入人格"""
        
        if not response or not response.completion_text:
            return

        text = response.completion_text
        self.found_emotions = []  # 重置表情列表

        # 严格匹配六边形符号包裹的表情
        hex_pattern = r"⬡([^⬡]+)⬡"
        matches = re.finditer(hex_pattern, text)
        
        clean_text = text
        valid_emoticons = set(self.category_mapping.keys())  # 预加载合法表情集合

        # 两阶段处理保证准确性
        temp_replacements = []
        for match in matches:
            original = match.group(0)
            emotion = match.group(1).strip()
            
            # 合法性验证
            if emotion in valid_emoticons:
                temp_replacements.append( (original, emotion) )
            else:
                temp_replacements.append( (original, "") )  # 非法表情静默移除

        # 保持原始顺序替换
        for original, emotion in temp_replacements:
            clean_text = clean_text.replace(original, "", 1)  # 每次替换第一个匹配项
            if emotion:
                self.found_emotions.append(emotion)

        # 去重并应用数量限制
        seen = set()
        filtered_emotions = []
        for emo in self.found_emotions:
            if emo not in seen:
                seen.add(emo)
                filtered_emotions.append(emo)
            if len(filtered_emotions) >= self.max_emotions_per_message:
                break
                
        self.found_emotions = filtered_emotions

        # 防御性清理残留符号
        clean_text = re.sub(r'⬡+', '', clean_text)  # 清除未成对的六边形符号
        response.completion_text = clean_text.strip()

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        """在消息发送前处理文本部分"""
        if not self.found_emotions:
            return

        result = event.get_result()
        if not result:
            return

        try:
            chains = []
            original_chain = result.chain

            if original_chain:
                if isinstance(original_chain, str):
                    chains.append(Plain(original_chain))
                elif isinstance(original_chain, MessageChain):
                    chains.extend([c for c in original_chain if isinstance(c, Plain)])
                elif isinstance(original_chain, list):
                    chains.extend([c for c in original_chain if isinstance(c, Plain)])

            text_result = event.make_result().set_result_content_type(
                ResultContentType.LLM_RESULT
            )
            for component in chains:
                if isinstance(component, Plain):
                    text_result = text_result.message(component.text)

            event.set_result(text_result)

        except Exception as e:
            self.logger.error(f"处理文本失败: {str(e)}")
            import traceback

            self.logger.error(traceback.format_exc())

    @filter.after_message_sent()
    async def after_message_sent(self, event: AstrMessageEvent):
        """消息发送后处理图片部分"""
        if not self.found_emotions:
            return

        try:
            for emotion in self.found_emotions:
                if not emotion:
                    continue

                emotion_path = os.path.join(MEMES_DIR, emotion)
                if not os.path.exists(emotion_path):
                    continue

                memes = [
                    f
                    for f in os.listdir(emotion_path)
                    if f.endswith((".jpg", ".png", ".gif"))
                ]
                if not memes:
                    continue

                meme = random.choice(memes)
                meme_file = os.path.join(emotion_path, meme)
                
                if random.randint(0, 100) <= self.emotions_probability:
                    await self.context.send_message(
                            event.unified_msg_origin,
                            MessageChain([Image.fromFileSystem(meme_file)]),
                        )
            self.found_emotions = []

        except Exception as e:
            self.logger.error(f"发送表情图片失败: {str(e)}")
            import traceback

            self.logger.error(traceback.format_exc())
        finally:
            self.found_emotions = []

    @meme_manager.command("同步状态")
    async def check_sync_status(self, event: AstrMessageEvent):
        """检查表情包与图床的同步状态"""
        if not self.img_sync:
            yield event.plain_result("图床服务尚未配置，请先在插件页面的配置中完成图床配置哦。")
            return
        
        try:
            status = self.img_sync.check_status()
            to_upload = status.get("to_upload", [])
            to_download = status.get("to_download", [])
            
            result = ["同步状态检查结果："]
            if to_upload:
                result.append(f"\n需要上传的文件({len(to_upload)}个)：")
                for file in to_upload[:5]:
                    result.append(f"\n- {file['category']}/{file['filename']}")
                if len(to_upload) > 5:
                    result.append("\n...（还有更多文件）")
                
            if to_download:
                result.append(f"\n需要下载的文件({len(to_download)}个):")
                for file in to_download[:5]:
                    result.append(f"\n- {file['category']}/{file['filename']}")
                if len(to_download) > 5:
                    result.append("\n...（还有更多文件）")
                
            if not to_upload and not to_download:
                result.append("🌩️ 云端与本地图库已经完全同步啦！")
            
            yield event.plain_result("".join(result))
        except Exception as e:
            self.logger.error(f"检查同步状态失败: {str(e)}")
            yield event.plain_result(f"检查同步状态失败: {str(e)}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("同步到云端")
    async def sync_to_remote(self, event: AstrMessageEvent):
        """将本地表情包同步到云端"""
        if not self.img_sync:
            yield event.plain_result("图床服务尚未配置，请先在配置文件中完成图床配置哦。")
            return
        
        try:
            yield event.plain_result("⚡ 正在开启云端同步任务...")
            success = await self.img_sync.start_sync('upload')
            if success:
                yield event.plain_result("云端同步已完成！")
            else:
                yield event.plain_result("云端同步失败，请查看日志哦。")
        except Exception as e:
            self.logger.error(f"同步到云端失败: {str(e)}")
            yield event.plain_result(f"同步到云端失败: {str(e)}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @meme_manager.command("从云端同步")
    async def sync_from_remote(self, event: AstrMessageEvent):
        """从云端同步表情包到本地"""
        if not self.img_sync:
            yield event.plain_result("图床服务尚未配置，请先在配置文件中完成图床配置哦。")
            return
        
        try:
            yield event.plain_result("开始从云端进行同步...")
            success = await self.img_sync.start_sync('download')
            if success:
                yield event.plain_result("从云端同步已完成！")
                # 重新加载表情配置
                await self.reload_emotions()
            else:
                yield event.plain_result("从云端同步失败，请查看日志哦。")
        except Exception as e:
            self.logger.error(f"从云端同步失败: {str(e)}")
            yield event.plain_result(f"从云端同步失败: {str(e)}")

    def __del__(self):
        """清理资源"""
        if self.img_sync:
            self.img_sync.stop_sync()
        self._cleanup_resources()

