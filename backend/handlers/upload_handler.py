import io
import ssl
import time

import aiohttp
from PIL import Image as PILImage

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.core.message.components import Image, Plain

from ..db.models import save_and_register_meme


async def handle_upload_image(sender, event: AstrMessageEvent):
    """处理用户上传的图片"""
    user_key = f"{event.session_id}_{event.get_sender_id()}"
    upload_state = sender.upload_states.get(user_key)

    if not upload_state or time.time() > upload_state["expire_time"]:
        if user_key in sender.upload_states:
            del sender.upload_states[user_key]
        return

    images = [c for c in event.message_obj.message if isinstance(c, Image)]

    if not images:
        yield event.plain_result("请发送图片文件来进行上传哦。")
        return

    categories = upload_state.get("categories") or [upload_state.get("category")]
    categories = [c for c in categories if c]

    try:
        saved_files = []

        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        for idx, img in enumerate(images, 1):
            timestamp = int(time.time())

            try:
                if "multimedia.nt.qq.com.cn" in img.url:
                    insecure_url = img.url.replace("https://", "http://", 1)
                    logger.warning(
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

                try:
                    with PILImage.open(io.BytesIO(content)) as img_obj:
                        file_type = img_obj.format.lower()
                except Exception as e:
                    logger.error(f"图片格式检测失败: {str(e)}")
                    file_type = "unknown"

                ext_mapping = {
                    "jpeg": ".jpg",
                    "png": ".png",
                    "gif": ".gif",
                    "webp": ".webp",
                }
                ext = ext_mapping.get(file_type, ".jpg")
                filename = f"{timestamp}_{idx}{ext}"

                res = save_and_register_meme(
                    image_bytes=content,
                    filename=filename,
                    category=categories,
                    personas="*",
                    config=sender.config,
                )
                saved_files.append(res["filename"])

            except Exception as e:
                logger.error(f"下载图片失败: {str(e)}")
                yield event.plain_result(f"文件 {img.url} 下载失败啦: {str(e)}")
                continue

        if user_key in sender.upload_states:
            del sender.upload_states[user_key]

        tags_display = "、".join(categories)
        result_msg = [
            Plain(
                f"✅ 已经成功收录了 {len(saved_files)} 张新表情到【{tags_display}】标签下！"
            )
        ]

        yield event.chain_result(result_msg)
        await sender.reload_emotions()

    except Exception as e:
        yield event.plain_result(f"保存失败了：{str(e)}")
