# LLM 大语言模型

## 文件位置

```
src/line_c/llm/
├── base.py              # LLM 接口定义
├── mock_llm.py          # Mock LLM（测试用）
├── cloud_llm.py         # DeepSeek API
└── cloud_llm_mimo.py    # MiMo API
```

---

## 1. LLM 接口定义 (`base.py`)

```python
@dataclass
class LLMResponse:
    """LLM 的一次回复结果"""
    text: str                         # 回复文本
    latency_ms: float = 0.0           # 响应耗时（毫秒）
    tokens_used: int = 0              # 使用的 token 数


class BaseLLM(ABC):
    """LLM 抽象基类——所有大模型后端的统一接口"""

    @abstractmethod
    def chat(self, system_prompt: str, messages: List[dict]) -> LLMResponse:
        """发送对话请求

        参数：
        - system_prompt: 系统提示词
        - messages: 对话历史 [{"role": "user", "content": "..."}]

        返回：
        - LLMResponse: 包含回复文本和元信息
        """
        ...
```

**作用**：定义 LLM 的统一接口。

---

## 2. DeepSeek API (`cloud_llm.py`)

### 2.1 初始化

```python
class CloudLLM(BaseLLM):
    """通过 HTTP 调用云端大模型 API"""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        model: str = "deepseek-chat",
        max_tokens: int = 150,
        temperature: float = 0.7,
    ):
        """
        参数说明：
        - api_url:      API 地址
        - api_key:      API 密钥（从服务商获取）
        - model:        模型名称
        - max_tokens:   每次回复最多输出多少个 token（约 150 token ≈ 100 英文词）
        - temperature:  随机性参数 0.0-1.0，越高回复越"有创意"但也更容易跑偏
        """
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
```

---

### 2.2 调用 API

```python
    def chat(self, system_prompt: str, messages: List[dict]) -> LLMResponse:
        """发送请求到云端 API

        OpenAI 兼容 API 的消息格式：
        [
            {"role": "system", "content": "你是..."},
            {"role": "user", "content": "用户说的话"},
            {"role": "assistant", "content": "AI上一次的回复"},
            {"role": "user", "content": "用户最新说的话"},
        ]
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
        }

        start = time.time()
        response = requests.post(
            self.api_url,
            headers=headers,
            json=body,
            timeout=30,   # 30 秒超时，避免无限等待
        )
        elapsed_ms = (time.time() - start) * 1000

        data = response.json()
        reply_text = data["choices"][0]["message"]["content"]
        tokens = data.get("usage", {}).get("total_tokens", 0)

        return LLMResponse(
            text=reply_text,
            latency_ms=elapsed_ms,
            tokens_used=tokens,
        )
```

**作用**：调用 DeepSeek 云端 API 获取 LLM 回复。

---

## 3. MiMo API (`cloud_llm_mimo.py`)

### 3.1 初始化

```python
class CloudLLMMimo(BaseLLM):
    """通过 HTTP 调用小米 MiMo API"""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        model: str = "mimo-v2.5",
        max_tokens: int = 500,
        temperature: float = 0.7,
    ):
        """
        参数说明：
        - api_url:      MiMo API 地址
        - api_key:      MiMo API 密钥
        - model:        MiMo 模型名称（默认 mimo-v2.5）
        - max_tokens:   每次回复最多输出多少个 token（默认 500，给思考留空间）
        - temperature:  随机性参数 0.0-1.0
        """
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
```

---

### 3.2 调用 API（支持思考模式）

```python
    def chat(self, system_prompt: str, messages: List[dict]) -> LLMResponse:
        """发送请求到 MiMo API

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
        }

        start = time.time()
        response = requests.post(
            self.api_url,
            headers=headers,
            json=body,
            timeout=30,
        )
        elapsed_ms = (time.time() - start) * 1000

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
```

**作用**：调用小米 MiMo API，支持思考模式。

---

## 📊 API 对比

| API | 模型 | 特点 |
|-----|------|------|
| DeepSeek | deepseek-chat | 标准 OpenAI 格式 |
| MiMo | mimo-v2.5 | 支持思考模式（reasoning_content） |

---

## 🔄 调用流程

```
用户消息
    ↓
构建 messages 数组
    ↓
添加 system_prompt
    ↓
发送 HTTP POST 请求
    ↓
解析响应 JSON
    ↓
返回 LLMResponse
```
