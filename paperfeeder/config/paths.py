from __future__ import annotations

from dataclasses import dataclass


DEFAULT_CONFIG_PATH = "config.yaml"
DEFAULT_USER_SETTINGS_PATH = "user/settings.yaml"
DEFAULT_RESEARCH_PROFILE_PATH = "user/research_interests.txt"
DEFAULT_PROMPT_ADDON_PATH = "user/prompt_addon.txt"
DEFAULT_SEMANTIC_SEEDS_PATH = "state/semantic/seeds.json"
DEFAULT_SEMANTIC_MEMORY_PATH = "state/semantic/memory.json"
DEFAULT_ARTIFACTS_DIR = "artifacts"
DEFAULT_REPORT_PREVIEW_PATH = "report_preview.html"
DEFAULT_FILTER_DEBUG_DIR = "llm_filter_debug"


@dataclass(frozen=True)
class ProjectPaths:
    config: str = DEFAULT_CONFIG_PATH
    user_settings: str = DEFAULT_USER_SETTINGS_PATH
    research_profile: str = DEFAULT_RESEARCH_PROFILE_PATH
    prompt_addon: str = DEFAULT_PROMPT_ADDON_PATH
    semantic_seeds: str = DEFAULT_SEMANTIC_SEEDS_PATH
    semantic_memory: str = DEFAULT_SEMANTIC_MEMORY_PATH
    artifacts_dir: str = DEFAULT_ARTIFACTS_DIR
    report_preview: str = DEFAULT_REPORT_PREVIEW_PATH
    filter_debug_dir: str = DEFAULT_FILTER_DEBUG_DIR
