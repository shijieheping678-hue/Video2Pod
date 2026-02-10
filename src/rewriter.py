"""AI-powered podcast script rewriter module.

Uses DeepSeek LLM to transform raw transcripts into engaging,
conversational podcast scripts with host-guest dialogue format.
"""

import os
from openai import OpenAI
from src.utils import logger


class Rewriter:
    """AI script rewriter that converts transcripts into podcast dialogue.

    Uses the DeepSeek API (OpenAI-compatible) to rewrite raw text into
    a natural, conversational two-person podcast script with designated
    host and guest roles.

    Attributes:
        client (OpenAI): OpenAI-compatible API client configured for DeepSeek.
        model (str): The LLM model name to use for rewriting.
    """

    def __init__(self, api_key=None, base_url="https://api.deepseek.com", model=None):
        """Initialize the Rewriter with DeepSeek API credentials.

        Args:
            api_key (str, optional): DeepSeek API key. Falls back to the
                ``DEEPSEEK_API_KEY`` environment variable if not provided.
            base_url (str): Base URL for the DeepSeek API endpoint.
                Defaults to "https://api.deepseek.com".
            model (str, optional): Model name to use. Falls back to the
                ``DEEPSEEK_MODEL`` environment variable, then to "deepseek-chat".
        """
        # Default to DeepSeek API
        self.client = OpenAI(
            api_key=api_key or os.getenv("DEEPSEEK_API_KEY"),
            base_url=base_url
        )
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    def rewrite_for_podcast(self, text, style="engaging"):
        """Rewrite text into a podcast-style dialogue script.

        Transforms raw transcript text into a two-person conversation
        between a host and a guest, with natural spoken
        language, emotional expressions, and interactive dialogue flow.

        The output format uses the convention:
            主持人：[content]
            嘉宾：[content]

        Args:
            text (str): The raw transcript or source text to rewrite.
            style (str): Writing style hint. Currently only "engaging"
                is supported. Defaults to "engaging".

        Returns:
            str: The rewritten podcast script in dialogue format.

        Raises:
            Exception: If the DeepSeek API call fails.
        """
        logger.info(f"Rewriting text for podcast using model: {self.model}")

        system_prompt = """你是一位专业的播客制作人，擅长制作那种“闲聊中见真知”的深度对谈节目。你的任务是将输入的素材改编成一段**极具生活气息、像真人聊天一样**的播客脚本。

核心要求：
1. **彻底的口语化（关键）**：
   - 坚决摒弃书面语！不要说“因此”、“然而”、“此外”，要说“所以说嘛”、“不过呢”、“还有个事儿”。
   - 大量使用自然填充词：在句子中自然地插入“那个...”、“呃...”、“就是说”、“对对对”、“哎你别说”。
   - 允许句子破碎和重复：真实说话往往是不连贯的，比如“我觉得...其实我觉得这个事儿吧...”。

2. **角色设定**：
   - **主持人**：好奇心强，负责捧哏、追问、引导话题。有时候会故意问点“傻问题”来引出解释。
   - **嘉宾**（xx老师）：行业专家，但说话接地气，喜欢打比方，偶尔会感慨或开玩笑。

3. **语气与情感标记（重要 - 适配 TTS）**：
   - **禁止使用括号备注**！不要写 `(笑)`、`[思考]`、`（惊讶）`，因为语音合成念不出来。
   - **直接把情绪写成语气词**：
     - 想笑？写“哈哈”或“嘿嘿”。
     - 思考？写“嗯……”、“让我想想……”。
     - 惊讶？写“哎呀”、“哇塞”。
     - 停顿？使用逗号或“……”来控制节奏。
   - 错误示例：嘉宾：这个嘛……(思考) 其实是这样的。
   - 正确示例：嘉宾：这个嘛……嗯……其实是这样的。

4. **对话流**：
   - 拒绝“一问一答”的采访式僵硬感。
   - 要有互动：抢话、补充、感叹（“天哪，真的假的？”）。
   - 主持人不要只做总结，要参与讨论，要有自己的（哪怕是外行的）反应。

5. **格式严格**：
   主持人：[内容]
   嘉宾：[内容]

6. **内容处理**：
   - 将干货融化在故事和闲聊里。
   - 保持原素材的核心观点不丢失，但表达方式要完全重构。

请直接输出对话脚本，不要包含任何“好的，这是脚本”之类的开场白。"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请将以下内容改写为播客文案：\n\n{text}"}
                ],
                temperature=0.3,
                stream=False
            )
            content = response.choices[0].message.content
            logger.info("Rewriting successful")
            return content
        except Exception as e:
            logger.error(f"Rewriting failed: {str(e)}")
            raise e
