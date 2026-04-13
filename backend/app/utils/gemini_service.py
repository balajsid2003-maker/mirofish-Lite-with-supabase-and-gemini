"""
Centralized Gemini 2.0 Flash LLM Service (google-genai SDK)
- Prompt caching (SHA-256 keyed, TTL 10 min)
- Rate-limit fallback to gemini-1.5-flash-8b with exponential backoff
- Per-simulation API call budget enforcement (≤150 calls)
- Batching helper for sequential calls
- Embedding via text-embedding-004
"""

import hashlib
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types as genai_types
from google.genai import errors as genai_errors

from ..config import Config

logger = logging.getLogger("mirofish.gemini_service")

# ─── Cache ────────────────────────────────────────────────────────────────────
_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL = 600  # 10 minutes

# ─── Global call counter ──────────────────────────────────────────────────────
_global_call_count: int = 0
_simulation_call_counts: Dict[str, int] = {}

SIMULATION_BUDGET = 150


class BudgetExceeded(Exception):
    pass


def _cache_key(prompt: str, system_prompt: str, model: str) -> str:
    content = f"{model}||{system_prompt}||{prompt}"
    return hashlib.sha256(content.encode()).hexdigest()


def _cache_get(key: str) -> Optional[str]:
    entry = _CACHE.get(key)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL:
        return entry["response"]
    if entry:
        del _CACHE[key]
    return None


def _cache_set(key: str, response: str) -> None:
    _CACHE[key] = {"response": response, "ts": time.time()}


def _strip_think_tags(text: str) -> str:
    return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()


class GeminiService:
    """
    Centralized Gemini LLM handler.
    Singleton via GeminiService.get_instance().
    """

    PRIMARY_MODEL = "gemini-2.0-flash"
    FALLBACK_MODEL = "gemini-2.0-flash-lite"  # free-tier fallback on rate-limit
    EMBEDDING_MODEL = "gemini-embedding-001"  # supports output_dimensionality; we use 768 for pgvector compat
    EMBEDDING_DIM = 768  # Matryoshka truncation — stays within ivfflat 2K limit

    _instance: Optional["GeminiService"] = None

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.LLM_API_KEY
        if not self.api_key:
            raise ValueError("LLM_API_KEY (or GEMINI_API_KEY) is not configured in .env")
        self._client = genai.Client(api_key=self.api_key)

    @classmethod
    def get_instance(cls) -> "GeminiService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ─── Budget tracking ──────────────────────────────────────────────────────
    @staticmethod
    def check_budget(simulation_id: Optional[str] = None) -> None:
        if simulation_id:
            count = _simulation_call_counts.get(simulation_id, 0)
            if count >= SIMULATION_BUDGET:
                raise BudgetExceeded(
                    f"Simulation {simulation_id} exceeded {SIMULATION_BUDGET} API calls"
                )

    @staticmethod
    def increment_count(simulation_id: Optional[str] = None) -> None:
        global _global_call_count
        _global_call_count += 1
        if simulation_id:
            _simulation_call_counts[simulation_id] = (
                _simulation_call_counts.get(simulation_id, 0) + 1
            )

    @staticmethod
    def get_call_count(simulation_id: Optional[str] = None) -> int:
        if simulation_id:
            return _simulation_call_counts.get(simulation_id, 0)
        return _global_call_count

    @staticmethod
    def reset_simulation_count(simulation_id: str) -> None:
        _simulation_call_counts.pop(simulation_id, None)

    # ─── Core generate ────────────────────────────────────────────────────────
    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        json_mode: bool = False,
        temperature: float = 0.7,
        max_retries: int = 1,
        simulation_id: Optional[str] = None,
        use_cache: bool = True,
    ) -> str:
        """Generate a response. Returns text string."""
        model_name = self.PRIMARY_MODEL
        cache_key = _cache_key(prompt, system_prompt, model_name)

        if use_cache:
            cached = _cache_get(cache_key)
            if cached is not None:
                logger.debug("Cache hit (sha=%s)", cache_key[:8])
                return cached

        self.check_budget(simulation_id)

        # Build config
        gen_config_kwargs: Dict[str, Any] = {"temperature": temperature}
        if json_mode:
            gen_config_kwargs["response_mime_type"] = "application/json"

        config = genai_types.GenerateContentConfig(
            system_instruction=system_prompt if system_prompt else None,
            **gen_config_kwargs,
        )

        last_error = None
        delay = 2.0

        for attempt in range(max_retries):
            use_model = self.PRIMARY_MODEL if attempt < 2 else self.FALLBACK_MODEL
            if attempt == 2:
                logger.warning("Falling back to %s", self.FALLBACK_MODEL)

            try:
                response = self._client.models.generate_content(
                    model=use_model,
                    contents=prompt,
                    config=config,
                )
                text = _strip_think_tags(response.text)
                self.increment_count(simulation_id)
                if use_cache:
                    _cache_set(cache_key, text)
                logger.debug(
                    "Gemini call #%d (sim=%s): %d chars",
                    self.get_call_count(simulation_id),
                    simulation_id,
                    len(text),
                )
                return text

            except genai_errors.ClientError as e:
                status_code = getattr(e, 'status_code', 0) or 0
                is_rate_limit = status_code == 429 or '429' in str(e) or 'RESOURCE_EXHAUSTED' in str(e)
                is_not_found = status_code == 404 or '404' in str(e)
                
                if is_not_found:
                    # Model not found even as fallback — raise immediately
                    raise
                elif is_rate_limit:
                    last_error = e
                    logger.warning("Rate limit hit (attempt %d/%d), waiting %.1fs", attempt + 1, max_retries, delay)
                    time.sleep(delay)
                    delay *= 2
                else:
                    last_error = e
                    logger.error("Gemini error (attempt %d): %s", attempt + 1, str(e)[:120])
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                        delay *= 2

            except Exception as e:
                last_error = e
                logger.error("Gemini error (attempt %d): %s", attempt + 1, str(e)[:120])
                if attempt < max_retries - 1:
                    time.sleep(delay)
                    delay *= 2

        raise last_error or RuntimeError("Gemini generate failed after retries")

    # ─── JSON helper ─────────────────────────────────────────────────────────
    def generate_json(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.4,
        simulation_id: Optional[str] = None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """Generate and parse a JSON response."""
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
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
            raise ValueError(f"Could not parse JSON: {cleaned[:200]}")

    # ─── Batch helper ─────────────────────────────────────────────────────────
    def generate_batch(
        self,
        prompts: List[Dict[str, str]],
        inter_call_delay: float = 1.0,
        simulation_id: Optional[str] = None,
    ) -> List[str]:
        results = []
        for item in prompts:
            result = self.generate(
                prompt=item.get("prompt", ""),
                system_prompt=item.get("system_prompt", ""),
                json_mode=item.get("json_mode", False),
                temperature=item.get("temperature", 0.7),
                simulation_id=simulation_id,
            )
            results.append(result)
            time.sleep(inter_call_delay)
        return results

    # ─── Embedding ───────────────────────────────────────────────────────────
    def embed(self, text: str, task_type: str = "retrieval_document") -> List[float]:
        """
        Generate a 768-dim text embedding using gemini-embedding-001.
        Uses output_dimensionality=768 (Matryoshka truncation) for pgvector ivfflat compatibility.
        """
        try:
            result = self._client.models.embed_content(
                model=self.EMBEDDING_MODEL,
                contents=text,
                config=genai_types.EmbedContentConfig(
                    output_dimensionality=self.EMBEDDING_DIM,
                ),
            )
            return result.embeddings[0].values
        except Exception as e:
            logger.warning("Embedding failed: %s — returning zeros", str(e)[:80])
            return [0.0] * self.EMBEDDING_DIM
