"""CloudLLM MiMo：通过 HTTP 调用小米 MiMo API。

支持 MiMo 的思考模式（reasoning_content）。
配置在 main_mimo.py 中硬编码。
"""

import json
import time
from typing import List, Optional

import requests

from .base import BaseLLM, LLMResponse


class CloudLLMMimo(BaseLLM):
    """通过 HTTP 调用小米 MiMo API。

    用法：
        llm = CloudLLMMimo(
            api_url="https://token-plan-cn.xiaomimimo.com/v1/chat/completions",
            api_key="tp-xxxx",
            model="mimo-v2.5",
        )
        response = llm.chat(system_prompt, messages)
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        model: str = "mimo-v2.5",
        max_tokens: int = 500,
        temperature: float = 0.7,
        top_p: float = 0.9,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
    ):
        """
        参数说明：
        - api_url:      MiMo API 地址
        - api_key:      MiMo API 密钥
        - model:        MiMo 模型名称（默认 mimo-v2.5）
        - max_tokens:   每次回复最多输出多少个 token（默认 500，给思考留空间）
        - temperature:  随机性参数 0.0-1.0
        - top_p:        核采样参数 0.0-1.0
        - frequency_penalty: 频率惩罚 0.0-2.0
        - presence_penalty:  存在惩罚 0.0-2.0
        """
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.frequency_penalty = frequency_penalty
        self.presence_penalty = presence_penalty

    def chat(
        self,
        system_prompt: str,
        messages: List[dict],
    ) -> LLMResponse:
        """发送请求到 MiMo API。

        MiMo 使用思考模式，回复在 content 中，思考在 reasoning_content 中。
        """
        full_messages = [{"role": "system", "content": system_prompt}]
        full_messages.extend(messages)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": full_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
        }

        start = time.time()
        response = requests.post(
            self.api_url,
            headers=headers,
            json=body,
            timeout=30,   # 30 秒超时
        )
        elapsed_ms = (time.time() - start) * 1000

        if response.status_code != 200:
            # API 返回错误时，不崩溃，返回错误信息作为文本
            error_msg = response.text[:200]
            return LLMResponse(
                text=f"[API Error {response.status_code}]: {error_msg}",
                latency_ms=elapsed_ms,
            )

        data = response.json()
        message = data["choices"][0]["message"]

        # MiMo 思考模式：优先使用 content，如果为空则使用 reasoning_content
        reply_text = message.get("content", "")
        if not reply_text:
            reply_text = message.get("reasoning_content", "")

        tokens = data.get("usage", {}).get("total_tokens", 0)

        return LLMResponse(
            text=reply_text,
            latency_ms=elapsed_ms,
            tokens_used=tokens,
        )

    def is_available(self) -> bool:
        """检查 MiMo API 是否可用。"""
        try:
            response = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
                timeout=10,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False