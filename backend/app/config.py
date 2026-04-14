"""
配置管理 — MiroFish Lite
使用 Google Gemini 2.0 Flash + Supabase (PostgreSQL + pgvector)
从项目根目录的 .env 加载配置
"""

import os
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
project_root_env = os.path.join(os.path.dirname(__file__), "../../.env")
if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    load_dotenv(override=True)


class Config:
    """Flask 配置类"""

    # Flask
    SECRET_KEY = os.environ.get("SECRET_KEY", "mirofish-lite-secret-key")
    DEBUG = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    JSON_AS_ASCII = False

    # ── LLM: Google Gemini 2.0 Flash ─────────────────────────────────────────
    # We unify this as LLM_API_KEY, falling back to GEMINI_API_KEY for compatibility.
    LLM_API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY")
    GEMINI_API_KEY = LLM_API_KEY  # Alias for backward compatibility
    
    # GROQ
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
    DEFAULT_LLM_PROVIDER = os.environ.get("DEFAULT_LLM_PROVIDER", "groq").lower()

    # ── Supabase (PostgreSQL + pgvector) ──────────────────────────────────────
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

    # ── File upload ───────────────────────────────────────────────────────────
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "../uploads")
    ALLOWED_EXTENSIONS = {"pdf", "md", "txt", "markdown"}

    # ── Text processing ───────────────────────────────────────────────────────
    DEFAULT_CHUNK_SIZE = 500
    DEFAULT_CHUNK_OVERLAP = 50

    # ── Simulation defaults (configurable via .env) ───────────────────────────
    SIMULATION_NUM_AGENTS = int(os.environ.get("SIMULATION_NUM_AGENTS", "20"))
    SIMULATION_NUM_ROUNDS = int(os.environ.get("SIMULATION_NUM_ROUNDS", "3"))
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get("OASIS_DEFAULT_MAX_ROUNDS", "3"))
    OASIS_SIMULATION_DATA_DIR = os.path.join(
        os.path.dirname(__file__), "../uploads/simulations"
    )

    # ── Platform actions ──────────────────────────────────────────────────────
    OASIS_TWITTER_ACTIONS = [
        "CREATE_POST", "LIKE_POST", "REPOST", "FOLLOW", "DO_NOTHING", "QUOTE_POST"
    ]
    OASIS_REDDIT_ACTIONS = [
        "LIKE_POST", "DISLIKE_POST", "CREATE_POST", "CREATE_COMMENT",
        "LIKE_COMMENT", "DISLIKE_COMMENT", "SEARCH_POSTS", "SEARCH_USER",
        "TREND", "REFRESH", "DO_NOTHING", "FOLLOW", "MUTE",
    ]

    # ── Report Agent ──────────────────────────────────────────────────────────
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get("REPORT_AGENT_MAX_TOOL_CALLS", "5"))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(
        os.environ.get("REPORT_AGENT_MAX_REFLECTION_ROUNDS", "2")
    )
    REPORT_AGENT_TEMPERATURE = float(os.environ.get("REPORT_AGENT_TEMPERATURE", "0.5"))

    # ── API cost control ──────────────────────────────────────────────────────
    MAX_API_CALLS_PER_SIMULATION = int(
        os.environ.get("MAX_API_CALLS_PER_SIMULATION", "150")
    )

    @classmethod
    def validate(cls):
        """Validate required configuration."""
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY (or GEMINI_API_KEY) is not configured")
        if cls.DEFAULT_LLM_PROVIDER == "groq" and not cls.GROQ_API_KEY:
            errors.append("GROQ_API_KEY is not configured but DEFAULT_LLM_PROVIDER is groq")
        if not cls.SUPABASE_URL:
            errors.append("SUPABASE_URL is not configured")
        if not cls.SUPABASE_KEY:
            errors.append("SUPABASE_KEY is not configured")
        return errors
