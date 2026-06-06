from .helpers import get_persona_setting


def reload_personas(sender):
    """Reload meme settings and inject prompt instructions into registered personas."""
    personas = sender.context.provider_manager.personas

    if not hasattr(sender, "persona_prompts_backup"):
        sender.persona_prompts_backup = {}

    for persona in personas:
        name = persona.get("name") or ""
        if name not in sender.persona_prompts_backup:
            raw_prompt = persona.get("prompt") or ""
            import re

            cleaned_prompt = re.sub(
                r"\n*<(meme_formatting_instructions|meme_tool_instructions|meme_hybrid_instructions|meme_behavior_instructions|meme_preference|meme_use_preference)>.*?</\1>",
                "",
                raw_prompt,
                flags=re.DOTALL | re.IGNORECASE,
            )
            sender.persona_prompts_backup[name] = cleaned_prompt.strip()

    format_instruction = (
        "\n\n<meme_formatting_instructions>\n"
        "【输出格式要求（极其重要）】:\n"
        "你必须在回复的【最末尾】且【单独一行】输出一个固定格式的表情标记块：<emotions>标签1, 标签2, ...</emotions>（例如 <emotions>得意, 摸头, 猫猫</emotions>，用英文逗号 `,` 分隔）。不要分在正文多处。若当前回复不需要表情包，则不要输出此标签块。\n"
        "</meme_formatting_instructions>"
    )

    tool_instruction = (
        "\n\n<meme_tool_instructions>\n"
        "【表情包工具发送指引（极其重要）】:\n"
        "你拥有发送本地表情包的专属工具 `send_meme`。在对话过程中，为了活跃气氛或展现你的个性，你应该根据当前的聊天内容、你的人格设定以及表情包使用偏好（供参考），积极、自然地使用此工具发送表情包。\n"
        "注意：在单次回复中，你可以多次调用本工具进行检索或发送。\n"
        "【防复述规则】：成功使用工具发送表情包后，若你在调用工具前已生成了回复文本（或者该表情包已完全表达你的意图，无需额外话语），请在此直接结束本次回复（停止生成），绝对不要复述或重复前面已输出的任何内容。\n"
        "除非用户要求，否则严禁使用其他任何外部网络搜索或画图工具发图。\n"
        "</meme_tool_instructions>"
    )

    hybrid_instruction = (
        "\n\n<meme_hybrid_instructions>\n"
        "【表情包发送指引（极其重要）】:\n"
        "**你必须使用以下两种方式之一来发送表情包**：\n"
        "1. 【情绪标签（日常推荐）】: 你可以直接在回复的【最末尾】且【单独一行】输出固定格式的表情标记块：<emotions>标签1, 标签2, ...</emotions>（例如 <emotions>得意, 摸头, 猫猫</emotions>，用英文逗号 `,` 分隔）。系统在后台会自动匹配并发送对应的表情包。适合日常闲聊表达语气和简单情绪。\n"
        "2. 【专属工具（精准检索）】: 你拥有专属工具 `send_meme`。当遇到特殊场景（如用户明确要求发送某张表情包，或你需要更精准地查找/挑选表情包）时，请使用此工具。工具调用遵循以下两步工作流：\n"
        "【注意事项】:\n"
        "- **你需要十分积极地发送表情包。**\n"
        "- 如果在单次回复中调用了 `send_meme` 发送了表情包，就【不要】再在回复末尾输出 `<emotions>` 情绪标签块，避免重复发送表情包。\n"
        "- **【防复述规则】：成功使用工具发送表情包后，如果你在调用工具前已生成了回复文本（或者该表情包已经能完全表达你的意思，无需额外话语），你应当直接结束本次回复（停止生成），绝对不要复述或重复你刚才说过的任何话。**\n"
        "- 除非用户要求，否则严禁使用其他任何外部网络搜索或画图工具发图。\n"
        "</meme_hybrid_instructions>"
    )

    for persona in personas:
        name = persona.get("name") or ""
        persona_id = persona.get("id") or ""
        blacklist = sender.config.get("persona_blacklist", [])
        if name in blacklist or persona_id in blacklist:
            if name in sender.persona_prompts_backup:
                persona["prompt"] = sender.persona_prompts_backup[name]
            continue

        original_prompt = sender.persona_prompts_backup.get(name, "")

        # Get persona preference from configuration settings
        pref = get_persona_setting(
            sender.config, persona_id, "meme_preference"
        ) or get_persona_setting(sender.config, name, "meme_preference")
        use_pref = get_persona_setting(
            sender.config, persona_id, "meme_use_preference"
        ) or get_persona_setting(sender.config, name, "meme_use_preference")

        pref_prompt = ""
        if pref:
            pref_prompt += f"<meme_preference>{pref}</meme_preference>"
        if use_pref:
            if pref_prompt:
                pref_prompt += "\n"
            pref_prompt += f"<meme_use_preference>{use_pref}</meme_use_preference>"

        injected_prompt = original_prompt
        if pref_prompt:
            injected_prompt += "\n\n" + pref_prompt

        is_emotion_llm = getattr(sender, "enable_emotion_llm", False)

        if is_emotion_llm:
            if sender.enable_llm_tool in ("tool", "hybrid"):
                persona["prompt"] = injected_prompt + tool_instruction
            else:
                persona["prompt"] = injected_prompt
        else:
            if sender.enable_llm_tool == "tool":
                persona["prompt"] = injected_prompt + tool_instruction
            elif sender.enable_llm_tool == "hybrid":
                persona["prompt"] = injected_prompt + hybrid_instruction
            else:
                behavior_prompt = f"\n\n<meme_behavior_instructions>\n{sender.meme_prompt}\n</meme_behavior_instructions>"
                persona["prompt"] = (
                    injected_prompt + behavior_prompt + format_instruction
                )
