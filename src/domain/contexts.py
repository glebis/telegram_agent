"""
Bounded context definitions for the Telegram Agent.

Each context groups related services and defines which other contexts
it may import from. This enables automated import-boundary enforcement.
"""

from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Context definitions
#
# Keys: context name
# Values:
#   modules  - list of dotted module paths belonging to this context
#   allowed  - list of context names this context may import from
#              ("shared" is always implicitly allowed)
# ---------------------------------------------------------------------------

BOUNDED_CONTEXTS: Dict[str, Dict] = {
    "shared": {
        "modules": [
            "src.core.config",
            "src.core.database",
            "src.core.i18n",
            "src.core.mode_manager",
            "src.core.services",
            "src.core.vector_db",
            "src.models.chat",
            "src.models.user",
            "src.models.user_settings",
            "src.models.message",
            "src.models.admin_contact",
            "src.utils",
        ],
        "allowed": [],
    },
    "ui": {
        "modules": [
            "src.services.keyboard_service",
            "src.bot.keyboard_utils",
        ],
        "allowed": ["shared"],
    },
    "learning": {
        "modules": [
            "src.services.srs_service",
            "src.services.srs",
        ],
        "allowed": ["shared"],
    },
    "polling": {
        "modules": [
            "src.services.poll_service",
            "src.services.polling_service",
            "src.services.poll_lifecycle",
            "src.services.poll_scheduler",
        ],
        "allowed": ["shared", "ai"],
    },
    "accountability": {
        "modules": [
            "src.services.accountability_service",
            "src.services.accountability_scheduler",
            "src.services.tracker_queries",
            "src.models.tracker",
        ],
        "allowed": ["shared", "voice"],
    },
    "voice": {
        "modules": [
            "src.services.voice_service",
            "src.services.voice_response_service",
            "src.services.voice_synthesis",
            "src.services.tts_service",
            "src.services.stt_service",
            "src.services.transcript_corrector",
        ],
        "allowed": ["shared"],
    },
    "ai": {
        "modules": [
            "src.services.llm_service",
            "src.services.embedding_service",
            "src.services.claude_code_service",
            "src.services.claude_subprocess",
            "src.services.opencode_service",
            "src.services.opencode_subprocess",
            "src.services.design_skills_service",
            "src.services.session_naming",
            "src.services.conversation_archive",
            "src.services.routing_memory",
        ],
        "allowed": ["shared"],
    },
    "media": {
        "modules": [
            "src.services.image_service",
            "src.services.image_classifier",
            "src.services.gallery_service",
            "src.services.collect_service",
            "src.services.similarity_service",
            "src.services.cache_service",
            "src.services.media_validator",
        ],
        "allowed": ["shared", "ai"],
    },
    "messaging": {
        "modules": [
            "src.services.message_buffer",
            "src.services.message_persistence_service",
            "src.services.link_service",
        ],
        "allowed": ["shared", "media"],
    },
    "infra": {
        "modules": [
            "src.services.heartbeat_service",
            "src.services.heartbeat_scheduler",
            "src.services.resource_monitor_service",
            "src.services.database_backup_service",
            "src.services.data_retention_service",
            "src.services.session_cleanup_service",
            "src.services.tunnel_monitor_service",
            "src.services.subprocess_sandbox",
            "src.services.task_ledger_service",
        ],
        "allowed": ["shared"],
    },
    "scheduling": {
        "modules": [
            "src.services.scheduler",
            "src.services.job_queue_service",
            "src.services.life_weeks_scheduler",
            "src.services.life_weeks_image",
            "src.services.life_weeks_reply_handler",
            "src.services.trail_scheduler",
            "src.services.trail_review_service",
        ],
        "allowed": ["shared"],
    },
}


def get_context_for_module(module_path: str) -> Optional[str]:
    """Return the context name a module belongs to, or None if unmapped.

    Checks for exact match first, then prefix match (for sub-packages
    like ``src.services.srs.*``).
    """
    for ctx_name, ctx_def in BOUNDED_CONTEXTS.items():
        for mod in ctx_def["modules"]:
            if module_path == mod or module_path.startswith(mod + "."):
                return ctx_name
    return None


def get_allowed_imports(context_name: str) -> List[str]:
    """Return the list of context names *context_name* may import from.

    Always includes ``"shared"`` unless the context itself is ``"shared"``.
    """
    ctx_def = BOUNDED_CONTEXTS.get(context_name)
    if ctx_def is None:
        return []
    allowed = list(ctx_def.get("allowed", []))
    if context_name != "shared" and "shared" not in allowed:
        allowed.append("shared")
    return allowed
