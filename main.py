"""
QQ头像获取插件

指令：/头像 @某人 [清晰度]
清晰度：1-6，默认5（高清）
"""

import os

import aiohttp

from astrbot.api.event import filter
from astrbot.api.star import StarTools
from astrbot.api.all import AstrBotConfig, Context, Star, logger, Plain, Image, At
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent


class AvatarPlugin(Star):
    # 清晰度映射
    SIZE_MAP = {
        1: ("s=1", "40x40 最小"),
        2: ("s=2", "40x40 小图"),
        3: ("s=3", "100x100 中等"),
        4: ("s=4", "140x140 标清"),
        5: ("s=5", "640x640 高清"),
        6: ("s=0&type=1", "大头像 最清晰"),
    }
    
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.default_size = config.get("default_size", 5)
        self.cache_dir = os.path.join(str(StarTools.get_data_dir()), "avatar_cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        
        logger.info(f"[QQ头像] 插件已加载，默认清晰度: {self.default_size}")
    
    def _get_avatar_url(self, qq_id: str, size: int = 5) -> str:
        """生成头像URL"""
        size_param, _ = self.SIZE_MAP.get(size, self.SIZE_MAP[5])
        return f"https://q1.qlogo.cn/g?b=qq&nk={qq_id}&{size_param}"
    
    async def _download_avatar(self, qq_id: str, size: int = 5) -> str | None:
        """下载头像并返回本地路径"""
        url = self._get_avatar_url(qq_id, size)
        local_path = os.path.join(self.cache_dir, f"{qq_id}_{size}.jpg")
        
        # 如果已缓存且不超过1小时，直接返回
        if os.path.exists(local_path):
            import time
            if time.time() - os.path.getmtime(local_path) < 3600:
                return local_path
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        with open(local_path, 'wb') as f:
                            f.write(await resp.read())
                        return local_path
        except Exception as e:
            logger.error(f"[QQ头像] 下载失败: {e}")
        
        return None
    
    @staticmethod
    def _extract_at_qq(event: AiocqhttpMessageEvent) -> str | None:
        """从消息中提取@的QQ号"""
        for 组件 in event.get_messages():
            if isinstance(组件, At):
                return str(组件.qq)

        return None

    @filter.command("头像")
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    async def 头像获取(self, event: AiocqhttpMessageEvent):
        """获取QQ头像"""

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    async def 接收消息(self, event: AiocqhttpMessageEvent):
        """监听消息，检测'头像'关键词"""

        # 提取参数
        message_text = event.message_str.strip()
        if not message_text.startswith("头像"):
            return
        event.stop_event()
        parts = message_text.split()

        # 尝试获取@的QQ号
        qq_id = self._extract_at_qq(event)
        
        # 如果没有@，尝试从参数获取QQ号
        if not qq_id and len(parts) > 1:
            for part in parts[1:]:
                if part.isdigit() and len(part) >= 5:
                    qq_id = part
                    break
        
        # 如果还是没有，获取自己的头像
        if not qq_id:
            qq_id = event.get_sender_id()
        
        if not qq_id:
            yield event.plain_result("请@要获取头像的用户，或提供QQ号")
            return
        
        # 解析清晰度参数
        size = self.default_size
        for part in parts:
            if part.isdigit() and 1 <= int(part) <= 6:
                size = int(part)
                break
        
        # 下载头像
        avatar_path = await self._download_avatar(qq_id, size)
        
        if not avatar_path:
            yield event.plain_result("获取头像失败，请稍后再试")
            return

        # 发送头像 - 使用消息链构造
        _, size_desc = self.SIZE_MAP.get(size, self.SIZE_MAP[5])
        chain = [
            Plain(f"QQ: {qq_id}\n清晰度: {size_desc}\n"),
            Image.fromFileSystem(avatar_path)
        ]
        await event.send(event.chain_result(chain))