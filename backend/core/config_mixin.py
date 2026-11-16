from ...utils import get_config_value


class MemeConfigMixin:
    @property
    def auto_steal_enabled(self) -> bool:
        return get_config_value(self.config, "auto_steal_enabled", False)

    @property
    def auto_steal_probability(self) -> int:
        return get_config_value(self.config, "auto_steal_probability", 30)

    @property
    def meme_decision_provider_id(self) -> str:
        """Return the optional decision provider used for collection checks.

        Returns:
            The configured provider ID, or an empty string for the chat flow.
        """
        return get_config_value(self.config, "meme_decision_provider_id", "")

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
    def multimodal_llm_enabled(self) -> bool:
        return get_config_value(self.config, "multimodal_llm_enabled", False)

    @property
    def multimodal_llm_provider_id(self) -> str:
        return get_config_value(self.config, "multimodal_llm_provider_id", "")

    @property
    def convert_static_to_gif(self) -> bool:
        return get_config_value(self.config, "convert_static_to_gif", False)

    @property
    def meme_summaries(self) -> list[str]:
        return get_config_value(self.config, "meme_summaries", ["这是一张表情包"])

    @property
    def enable_similarity_dedup(self) -> bool:
        return get_config_value(self.config, "enable_similarity_dedup", True)

    @property
    def similarity_dedup_threshold(self) -> float:
        return get_config_value(self.config, "similarity_dedup_threshold", 0.85)
