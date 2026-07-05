from ...utils import get_config_value


class MemeConfigMixin:
    @property
    def fault_tolerant_symbols(self) -> list[str]:
        return get_config_value(self.config, "fault_tolerant_symbols", ["⬡"])

    @property
    def auto_steal_enabled(self) -> bool:
        return get_config_value(self.config, "auto_steal_enabled", False)

    @property
    def auto_steal_probability(self) -> int:
        return get_config_value(self.config, "auto_steal_probability", 30)

    @property
    def meme_prompt(self) -> str:
        default_prompt = (
            "【表情包发送行为指引】：你在每次回复中都应该自然地根据当前的聊天内容和情绪选择表情标签。"
            "\n规则："
            "\n1. 标签越丰富、越明确，越能精准匹配到图库中的表情。建议根据当前的聊天内容和情绪提炼并输出多个简短标签（用英文逗号 `,` 分隔），可从以下几个社交维度去发想："
            "\n   - 意图与功能（如：敷衍、赞同、摸头、贴贴、递茶、抱抱）"
            "\n   - 情绪与心理（如：得意、害羞、尴尬、开摆、委屈、暴躁、吃惊）"
            "\n   - 画面主体与行为（如：猫猫、睡觉、吃瓜、熊猫头）"
            "\n   - 风格与态度（如：阴阳怪气、沙雕、二次元、职场发疯、治愈）"
            "\n   （若当前回复不需要表情包，则不输出表情标签）"
            "\n\n【关于搜索与发图工具的限制】："
            "\n除非用户十分明确要求你使用网络搜索，否则对于普通的聊天回复 and 表情包发送需求，严禁使用任何外部搜索工具（如 web_search、tavily 等）去网络搜索图片，也严禁调用任何第三方发图或消息发送工具。你只需输出表情标签，系统会自动在后台拦截并从本地匹配发送表情包。"
        )
        return get_config_value(self.config, "meme_prompt", default_prompt)

    @property
    def multimodal_tag_prompt(self) -> str:
        default_tag_prompt = (
            "你是一个专业的表情包内容分析师，需要全面分析表情包的各个维度，重点识别角色来源、作品归属和物品特征，为用户提供详细、准确、实用的信息。\n"
            "标签策略（重点优化）：\n"
            "- 标签数量：4-6个精选标签，避免冗余\n"
            "- 标签优先级（从高到低）：\n"
            '  * 角色/作品标签（最高优先级）：如果能识别角色或作品，必须包含。如"派蒙"、"原神"、"海绵宝宝"、"柴犬"\n'
            '  * 物品/主体标签（高优先级）：描述表情包的主体是什么。如"猫"、"狗"、"食物"、"机器人"\n'
            '  * 情感/表情标签（中优先级）：描述表情包表达的情感。如"开心"、"无语"、"生气"、"摆烂"、"震惊"\n'
            '  * 动作/状态标签（中优先级）：描述角色或物品的动作。如"奔跑"、"吃东西"、"睡觉"、"跳舞"\n'
            '  * 风格/形式标签（低优先级）：如"二次元"、"像素风"、"真人"、"手绘"\n'
            "- 标签质量：\n"
            "  * 使用通俗易懂的词汇\n"
            "  * 考虑用户搜索习惯与词汇偏好\n"
            "  * 平衡具体性和通用性\n"
            "  * 避免过于专业或生僻的术语\n\n"
            "描述：\n"
            "根据画面和标签结果进行简洁描述。"
        )
        return get_config_value(
            self.config, "multimodal_tag_prompt", default_tag_prompt
        )

    @property
    def max_emotions_per_message(self) -> int:
        return get_config_value(self.config, "max_emotions_per_message", 2)

    @property
    def emotions_probability(self) -> int:
        return get_config_value(self.config, "emotions_probability", 50)

    @property
    def multimodal_llm_enabled(self) -> bool:
        return get_config_value(self.config, "multimodal_llm_enabled", False)

    @property
    def multimodal_llm_provider_id(self) -> str:
        return get_config_value(self.config, "multimodal_llm_provider_id", "")

    @property
    def enable_mixed_message(self) -> bool:
        return get_config_value(self.config, "enable_mixed_message", True)

    @property
    def mixed_message_probability(self) -> int:
        return get_config_value(self.config, "mixed_message_probability", 80)

    @property
    def convert_static_to_gif(self) -> bool:
        return get_config_value(self.config, "convert_static_to_gif", False)

    @property
    def streaming_compatibility(self) -> bool:
        return get_config_value(self.config, "streaming_compatibility", False)

    @property
    def meme_summaries(self) -> list[str]:
        return get_config_value(self.config, "meme_summaries", ["这是一张表情包"])

    @property
    def enable_similarity_dedup(self) -> bool:
        return get_config_value(self.config, "enable_similarity_dedup", True)

    @property
    def similarity_dedup_threshold(self) -> float:
        return get_config_value(self.config, "similarity_dedup_threshold", 0.85)

    @property
    def enable_llm_tool(self) -> str:
        val = get_config_value(self.config, "enable_llm_tool", "tag")
        if val is True:
            return "tool"
        elif val is False:
            return "tag"
        return val

    @property
    def enable_emotion_llm(self) -> bool:
        return get_config_value(self.config, "enable_emotion_llm", False)

    @property
    def emotion_llm_provider_id(self) -> str:
        return get_config_value(self.config, "emotion_llm_provider_id", "")

    @property
    def emotion_llm_prompt(self) -> str:
        default_prompt = "根据以下对话背景，分析助手回复的语气和情感，自由输出符合回复语气、画面主体或情感的表情包标签。"
        return get_config_value(self.config, "emotion_llm_prompt", default_prompt)
