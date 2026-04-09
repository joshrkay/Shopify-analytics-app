"""
OpenRouter API response models.

Dataclasses for structured response handling.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class ChatMessage:
    """A message in a chat completion."""
    role: str  # 'system', 'user', 'assistant', 'tool'
    content: str
    # Used when role == 'tool' (tool result back to model)
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatMessage":
        return cls(
            role=data.get("role", ""),
            content=data.get("content", "") or "",
            tool_call_id=data.get("tool_call_id"),
            name=data.get("name"),
        )

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            d["name"] = self.name
        return d


@dataclass
class ToolCall:
    """A tool call requested by the model."""
    id: str
    name: str        # function name
    arguments: str   # JSON-encoded argument dict — parse at call site


@dataclass
class ToolDefinition:
    """Definition of a callable tool (function) exposed to the model."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema object

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ChatChoice:
    """A single choice in a chat completion response."""
    index: int
    message: ChatMessage
    finish_reason: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatChoice":
        raw_tool_calls = data.get("message", {}).get("tool_calls") or []
        tool_calls = [
            ToolCall(
                id=tc.get("id", ""),
                name=tc.get("function", {}).get("name", ""),
                arguments=tc.get("function", {}).get("arguments", "{}"),
            )
            for tc in raw_tool_calls
        ]
        return cls(
            index=data.get("index", 0),
            message=ChatMessage.from_dict(data.get("message", {})),
            finish_reason=data.get("finish_reason"),
            tool_calls=tool_calls,
        )


@dataclass
class TokenUsage:
    """Token usage information from a completion."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenUsage":
        return cls(
            prompt_tokens=data.get("prompt_tokens", 0),
            completion_tokens=data.get("completion_tokens", 0),
            total_tokens=data.get("total_tokens", 0),
        )


@dataclass
class ChatCompletionResponse:
    """Response from chat completion endpoint."""
    id: str
    model: str
    choices: List[ChatChoice]
    usage: TokenUsage
    created: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatCompletionResponse":
        return cls(
            id=data.get("id", ""),
            model=data.get("model", ""),
            choices=[
                ChatChoice.from_dict(c)
                for c in data.get("choices", [])
            ],
            usage=TokenUsage.from_dict(data.get("usage", {})),
            created=data.get("created", 0),
        )

    @property
    def content(self) -> str:
        """Get the content of the first choice, or empty string."""
        if self.choices:
            return self.choices[0].message.content
        return ""

    @property
    def finish_reason(self) -> Optional[str]:
        """Finish reason of the first choice."""
        if self.choices:
            return self.choices[0].finish_reason
        return None

    @property
    def tool_calls(self) -> List[ToolCall]:
        """Tool calls from the first choice (empty list if none)."""
        if self.choices:
            return self.choices[0].tool_calls
        return []

    @property
    def input_tokens(self) -> int:
        """Alias for prompt_tokens."""
        return self.usage.prompt_tokens

    @property
    def output_tokens(self) -> int:
        """Alias for completion_tokens."""
        return self.usage.completion_tokens


@dataclass
class ModelInfo:
    """Information about an available model."""
    id: str
    name: str
    context_length: int = 4096
    pricing: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelInfo":
        pricing = data.get("pricing", {})
        return cls(
            id=data.get("id", ""),
            name=data.get("name", data.get("id", "")),
            context_length=data.get("context_length", 4096),
            pricing={
                "prompt": float(pricing.get("prompt", 0)),
                "completion": float(pricing.get("completion", 0)),
            },
        )
