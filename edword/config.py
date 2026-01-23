"""Configuration loading and validation."""

from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

import yaml


@dataclass
class LLMConfig:
    """LLM configuration."""
    provider: str = "claude"
    model: str = "opus"
    recursive_provider: str = ""  # Empty = same as provider
    recursive_model: str = "sonnet"
    max_iterations: int = 25
    timeout: int = 300


@dataclass
class PathsConfig:
    """Path configuration."""
    manuscripts: str = "manuscripts/"
    codex: str = "codex/"
    reports: str = ".edword/reports/"


@dataclass
class PassConfig:
    """Configuration for a single pass."""
    enabled: bool = True
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EdwordConfig:
    """Full edword configuration."""
    project_name: str = "Untitled Project"
    paths: PathsConfig = field(default_factory=PathsConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    passes: Dict[str, PassConfig] = field(default_factory=dict)

    # Runtime info (not from config file)
    config_path: Optional[Path] = None
    project_root: Optional[Path] = None


def find_config(start_path: Optional[Path] = None) -> Optional[Path]:
    """
    Find edword config file by walking up directory tree.

    Looks for: edword.yaml, .edword.yaml, edword.yml, .edword.yml

    Args:
        start_path: Starting directory (defaults to cwd)

    Returns:
        Path to config file or None if not found
    """
    if start_path is None:
        start_path = Path.cwd()

    start_path = Path(start_path).resolve()

    config_names = ["edword.yaml", ".edword.yaml", "edword.yml", ".edword.yml"]

    current = start_path
    while current != current.parent:
        for name in config_names:
            config_path = current / name
            if config_path.exists():
                return config_path
        current = current.parent

    return None


def load_config(config_path: Optional[Path] = None) -> EdwordConfig:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to config file (auto-discovered if None)

    Returns:
        EdwordConfig with loaded values
    """
    if config_path is None:
        config_path = find_config()

    config = EdwordConfig()

    if config_path is None:
        # No config file - use all defaults
        config.project_root = Path.cwd()
        return config

    config_path = Path(config_path)
    config.config_path = config_path
    config.project_root = config_path.parent

    with open(config_path) as f:
        data = yaml.safe_load(f) or {}

    # Project name
    if "project" in data:
        config.project_name = data["project"].get("name", config.project_name)

    # Paths
    if "paths" in data:
        paths = data["paths"]
        config.paths = PathsConfig(
            manuscripts=paths.get("manuscripts", config.paths.manuscripts),
            codex=paths.get("codex", config.paths.codex),
            reports=paths.get("reports", config.paths.reports),
        )

    # LLM settings
    if "llm" in data:
        llm = data["llm"]
        config.llm = LLMConfig(
            provider=llm.get("provider", config.llm.provider),
            model=llm.get("model", config.llm.model),
            recursive_provider=llm.get("recursive_provider", config.llm.recursive_provider),
            recursive_model=llm.get("recursive_model", config.llm.recursive_model),
            max_iterations=llm.get("max_iterations", config.llm.max_iterations),
            timeout=llm.get("timeout", config.llm.timeout),
        )

    # Pass configurations
    if "passes" in data:
        for pass_name, pass_data in data["passes"].items():
            if isinstance(pass_data, bool):
                config.passes[pass_name] = PassConfig(enabled=pass_data)
            elif isinstance(pass_data, dict):
                config.passes[pass_name] = PassConfig(
                    enabled=pass_data.get("enabled", True),
                    options={k: v for k, v in pass_data.items() if k != "enabled"}
                )

    return config


def get_pass_config(config: EdwordConfig, pass_name: str) -> PassConfig:
    """
    Get configuration for a specific pass.

    Args:
        config: Full edword configuration
        pass_name: Name of the pass

    Returns:
        PassConfig (default if not specified)
    """
    return config.passes.get(pass_name, PassConfig())
