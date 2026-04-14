"""
Groq LLM Service — Cost-efficient alternative to Gemini.
Provides a similar interface to GeminiService for seamless switching.
"""

import json
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional

from groq import Groq
from ..config import Config

logger = logging.getLogger("mirofish.groq_service")

# Re-use the same budget tracking from GeminiService for consistency
# or define a separate one? User said "run this project with the minimal cost".
# We'll use a shared or similar budget tracker.
_global_call_count: int = 0
_simulation_call_counts: Dict[str, int] = {}
SIMULATION_BUDGET = 500  # Groq is cheaper, maybe higher budget? 
# For now, let's keep it consistent or follow Config.

class GroqService:
    """
    Handler for Groq LLM.
    Uses Llama 3 or Mixtral models.
    """

    PRIMARY_MODEL = "llama-3.3-70b-versatile"
    # ALTERNATIVE: "llama-3.1-8b-instant" for even lower cost/latency
    
    _instance: Optional["GroqService"] = None
    _lock = threading.Lock()

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.GROQ_API_KEY
        if not self.api_key:
            # Fallback to LLM_API_KEY if Groq key not set, though unlikely to work if it's a Gemini key
            self.api_key = Config.LLM_API_KEY 
        
        self._client = Groq(api_key=self.api_key)

    @classmethod
    def get_instance(cls) -> "GroqService":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        json_mode: bool = False,
        temperature: float = 0.7,
        max_retries: int = 3,
        simulation_id: Optional[str] = None,
        use_cache: bool = True, # Cache not fully implemented here for simplicity
    ) -> str:
        """Generate a response using Groq."""
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        last_error = None
        for attempt in range(max_retries):
            try:
                response = self._client.chat.completions.create(
                    model=self.PRIMARY_MODEL,
                    messages=messages,
                    temperature=temperature,
                    response_format={"type": "json_object"} if json_mode else None,
                )
                text = response.choices[0].message.content
                logger.debug("Groq call (sim=%s): %d chars", simulation_id, len(text))
                return text
            except Exception as e:
                last_error = e
                logger.warning(f"Groq error (attempt {attempt+1}): {e}")
                time.sleep(1 * (attempt + 1))
        
        raise last_error or RuntimeError("Groq generate failed")

    def generate_json(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.4,
        simulation_id: Optional[str] = None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """Generate and parse a JSON response from Groq."""
        text = self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            json_mode=True,
            temperature=temperature,
            simulation_id=simulation_id,
            use_cache=use_cache,
        )
        return self._parse_json(text)

    def _parse_json(self, text: str) -> Dict[str, Any]:
        """Robuts JSON parsing."""
        cleaned = text.strip()
        # Remove markdown code blocks if present
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Fallback: try to find the first '{' and last '}'
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
            raise ValueError(f"Could not parse JSON from Groq: {cleaned[:200]}")
