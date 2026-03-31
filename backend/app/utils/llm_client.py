"""
LLM Client — Thin wrapper over GeminiService.
Keeps the same public interface (chat, chat_json) so all existing callers
work without modification.
"""

import json
import re
from typing import Any, Dict, List, Optional

from ..config import Config
from .gemini_service import GeminiService


def _messages_to_prompt(messages: List[Dict[str, str]]) -> tuple[str, str]:
    """Convert OpenAI-style message list to (system_prompt, user_prompt)."""
    system_parts = []
    user_parts = []

    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            system_parts.append(content)
        elif role == "assistant":
            user_parts.append(f"[Assistant]: {content}")
        else:
            user_parts.append(content)

    system_prompt = "\n\n".join(system_parts)
    user_prompt = "\n\n".join(user_parts)
    return system_prompt, user_prompt


class LLMClient:
    """
    LLM客户端 — delegates to GeminiService.
    Public interface unchanged: chat() and chat_json().
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,  # kept for signature compat, unused
        model: Optional[str] = None,     # kept for signature compat, unused
    ):
        self._gemini = GeminiService.get_instance()

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,          # kept for signature compat, unused
        response_format: Optional[Dict] = None,
        simulation_id: Optional[str] = None,
    ) -> str:
        """Send a chat request and return the response text."""
        system_prompt, user_prompt = _messages_to_prompt(messages)
        json_mode = (
            response_format is not None
            and response_format.get("type") == "json_object"
        )
        return self._gemini.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            json_mode=json_mode,
            temperature=temperature,
            simulation_id=simulation_id,
        )

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,          # kept for signature compat, unused
        simulation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a chat request and return parsed JSON."""
        system_prompt, user_prompt = _messages_to_prompt(messages)
        return self._gemini.generate_json(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            simulation_id=simulation_id,
        )

