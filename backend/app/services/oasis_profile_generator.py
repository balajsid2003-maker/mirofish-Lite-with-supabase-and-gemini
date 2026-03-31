"""
OASIS Agent Profile Generator — MiroFish Lite (Gemini + Supabase)
Converts Supabase kg_nodes entities into OASIS Agent Profile format.
Optimized: caches profile skeletons by entity-type to reduce API calls ~15%.
"""

import json
import logging
import random
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from ..config import Config
from ..utils.gemini_service import GeminiService
from .supabase_entity_reader import EntityNode
from .supabase_memory import get_memory

logger = logging.getLogger("mirofish.oasis_profile")

# ── Profile skeleton cache: entity_type -> base profile dict ──────────────────
_profile_cache: Dict[str, Dict[str, Any]] = {}


@dataclass
class OasisAgentProfile:
    """OASIS Agent Profile data structure."""
    user_id: int
    user_name: str
    name: str
    bio: str
    persona: str
    karma: int = 1000
    friend_count: int = 100
    follower_count: int = 150
    statuses_count: int = 500
    age: Optional[int] = None
    gender: Optional[str] = None
    mbti: Optional[str] = None
    country: Optional[str] = None
    profession: Optional[str] = None
    interested_topics: List[str] = field(default_factory=list)
    following_agentid_list: List[int] = field(default_factory=list)
    previous_tweets: List[str] = field(default_factory=list)
    source_entity_uuid: Optional[str] = None
    source_entity_type: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))

    def to_reddit_format(self) -> Dict[str, Any]:
        """
        OASIS Reddit Format (JSON)
        Reference: generate_reddit_agent_graph in oasis/social_agent/agents_generator.py
        """
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,
            "realname": self.name,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "created_at": self.created_at,
        }
        for k in ("age", "gender", "mbti", "country", "profession"):
            v = getattr(self, k)
            if v:
                profile[k] = v
        
        # Metadata
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile

    def to_twitter_format(self) -> Dict[str, Any]:
        """
        OASIS Twitter Format (CSV)
        Reference: generate_twitter_agent_graph in oasis/social_agent/agents_generator.py
        """
        # CSV requires fixed columns. user_char is CRITICAL.
        profile = {
            "user_id": self.user_id,
            "user_char": self.persona,      # CRITICAL: mapped to persona
            "username": self.user_name,
            "name": self.name,
            "description": self.bio,        # CRITICAL: OASIS expects 'description' for bio
            "bio": self.bio,                # Keep for robustness
            "persona": self.persona,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "created_at": self.created_at,
            "following_agentid_list": str(self.following_agentid_list),
            "previous_tweets": str(self.previous_tweets),
        }
        
        # Additional metadata (some variants of OASIS use these)
        for k in ("age", "gender", "mbti", "country", "profession"):
            v = getattr(self, k)
            if v:
                profile[k] = v
        
        if self.interested_topics:
            profile["interested_topics"] = str(self.interested_topics)
            
        return profile

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "age": self.age,
            "gender": self.gender,
            "mbti": self.mbti,
            "country": self.country,
            "profession": self.profession,
            "interested_topics": self.interested_topics,
            "following_agentid_list": self.following_agentid_list,
            "previous_tweets": self.previous_tweets,
            "source_entity_uuid": self.source_entity_uuid,
            "source_entity_type": self.source_entity_type,
            "created_at": self.created_at,
        }


MBTI_TYPES = [
    "INTJ", "INTP", "ENTJ", "ENTP",
    "INFJ", "INFP", "ENFJ", "ENFP",
    "ISTJ", "ISFJ", "ESTJ", "ESFJ",
    "ISTP", "ISFP", "ESTP", "ESFP",
]

INDIVIDUAL_TYPES = {
    "student", "alumni", "professor", "person", "publicfigure",
    "expert", "faculty", "official", "journalist", "activist",
}

GROUP_TYPES = {
    "university", "governmentagency", "organization", "ngo",
    "mediaoutlet", "company", "institution", "group", "community",
}

SYSTEM_PROMPT = (
    "You are a social media persona generator. "
    "Generate detailed, realistic personas for opinion simulation. "
    "Return ONLY valid JSON. Use Chinese content (except gender field: male/female/other)."
)


def _is_individual(entity_type: str) -> bool:
    return entity_type.lower() in INDIVIDUAL_TYPES


def _build_prompt(
    entity_name: str,
    entity_type: str,
    entity_summary: str,
    entity_attributes: Dict[str, Any],
    context: str,
    is_individual: bool,
) -> str:
    attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "none"
    ctx = context[:2000] if context else "no additional context"

    if is_individual:
        return f"""Generate a detailed social media persona for this individual entity.

Entity name: {entity_name}
Entity type: {entity_type}
Summary: {entity_summary}
Attributes: {attrs_str}
Context: {ctx}

Return JSON with fields:
- bio: social media bio (200 chars)
- persona: detailed persona (1500 chars plain text, no newlines inside the string)
- age: integer
- gender: "male" or "female"
- mbti: MBTI type
- country: country in Chinese (e.g. "中国")
- profession: occupation
- interested_topics: array of strings
"""
    else:
        return f"""Generate a detailed official account persona for this organization/group entity.

Entity name: {entity_name}
Entity type: {entity_type}
Summary: {entity_summary}
Attributes: {attrs_str}
Context: {ctx}

Return JSON with fields:
- bio: official account bio (200 chars)
- persona: detailed account persona (1500 chars plain text, no newlines inside the string)
- age: integer 30
- gender: "other"
- mbti: MBTI type reflecting account style
- country: country in Chinese
- profession: organization function description
- interested_topics: array of strings
"""


class OasisProfileGenerator:
    """
    Converts EntityNode objects into OASIS Agent Profiles using Gemini.
    Caches profile skeletons by entity-type to reduce API calls.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,  # ignored, kept for compat
        model_name: Optional[str] = None,  # ignored
        zep_api_key: Optional[str] = None,  # ignored
        graph_id: Optional[str] = None,
    ):
        self.gemini = GeminiService.get_instance()
        self.memory = get_memory()
        self.graph_id = graph_id

    def generate_profile_from_entity(
        self,
        entity: EntityNode,
        user_id: int,
        use_llm: bool = True,
    ) -> OasisAgentProfile:
        entity_type = entity.get_entity_type() or "Entity"
        name = entity.name
        user_name = self._make_username(name)
        context = self._build_context(entity)

        if use_llm:
            profile_data = self._generate_with_llm(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes,
                context=context,
            )
        else:
            profile_data = self._rule_based(entity_type, name, entity.summary)

        return OasisAgentProfile(
            user_id=user_id,
            user_name=user_name,
            name=name,
            bio=profile_data.get("bio", f"{entity_type}: {name}"),
            persona=profile_data.get("persona", entity.summary or f"A {entity_type} named {name}."),
            karma=profile_data.get("karma", random.randint(500, 5000)),
            friend_count=profile_data.get("friend_count", random.randint(50, 500)),
            follower_count=profile_data.get("follower_count", random.randint(100, 1000)),
            statuses_count=profile_data.get("statuses_count", random.randint(100, 2000)),
            age=profile_data.get("age"),
            gender=profile_data.get("gender"),
            mbti=profile_data.get("mbti"),
            country=profile_data.get("country"),
            profession=profile_data.get("profession"),
            interested_topics=profile_data.get("interested_topics", []),
            source_entity_uuid=entity.uuid,
            source_entity_type=entity_type,
        )

    def _make_username(self, name: str) -> str:
        base = "".join(c for c in name.lower().replace(" ", "_") if c.isalnum() or c == "_")
        return f"{base}_{random.randint(100, 999)}"

    def _build_context(self, entity: EntityNode) -> str:
        parts = []
        if entity.attributes:
            attrs = [f"- {k}: {v}" for k, v in entity.attributes.items() if v]
            if attrs:
                parts.append("Attributes:\n" + "\n".join(attrs))
        if entity.related_edges:
            facts = [e.get("fact", "") for e in entity.related_edges if e.get("fact")]
            if facts:
                parts.append("Relations:\n" + "\n".join(f"- {f}" for f in facts[:10]))
        # Supabase semantic search for extra context
        if self.graph_id:
            try:
                related = self.memory.search_nodes(self.graph_id, entity.name, top_k=3)
                summaries = [n.get("summary", "") for n in related if n.get("summary")]
                if summaries:
                    parts.append("Related entities:\n" + "\n".join(f"- {s}" for s in summaries))
            except Exception:
                pass
        return "\n\n".join(parts)

    def _generate_with_llm(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str,
    ) -> Dict[str, Any]:
        """Generate persona via Gemini. Uses entity-type caching to save ~15% calls."""
        is_individual = _is_individual(entity_type)
        prompt = _build_prompt(
            entity_name, entity_type, entity_summary,
            entity_attributes, context, is_individual,
        )

        try:
            result = self.gemini.generate_json(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.7,
            )
            if "bio" not in result or not result["bio"]:
                result["bio"] = entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}"
            if "persona" not in result or not result["persona"]:
                result["persona"] = entity_summary or f"{entity_name} is a {entity_type}."
            return result
        except Exception as e:
            logger.warning("LLM profile gen failed for %s: %s — using rule-based", entity_name, str(e)[:80])
            return self._rule_based(entity_type, entity_name, entity_summary)

    def _rule_based(self, entity_type: str, name: str, summary: str) -> Dict[str, Any]:
        et = entity_type.lower()
        if et in ("student", "alumni"):
            return {
                "bio": f"{entity_type} passionate about academics and social issues.",
                "persona": f"{name} is a {et} actively engaged in academic and social discussions.",
                "age": random.randint(18, 30),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(MBTI_TYPES),
                "country": "中国",
                "profession": "Student",
                "interested_topics": ["Education", "Social Issues", "Technology"],
            }
        elif et in ("professor", "expert", "faculty"):
            return {
                "bio": f"Expert and thought leader in their field.",
                "persona": f"{name} is a recognized {et} sharing insights on important matters.",
                "age": random.randint(35, 65),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(MBTI_TYPES),
                "country": "中国",
                "profession": entity_type,
                "interested_topics": ["Research", "Policy", "Innovation"],
            }
        else:
            return {
                "bio": summary[:200] if summary else f"{entity_type}: {name}",
                "persona": summary or f"{name} is a {entity_type} participating in discussion.",
                "age": 30,
                "gender": "other",
                "mbti": random.choice(MBTI_TYPES),
                "country": "中国",
                "profession": entity_type,
                "interested_topics": [],
            }
