"""
Utility functions for the Claude 0 AD Player.

Includes:
- Logging setup
- Configuration loading
- Episode saving
- Display helpers
"""
import os
import json
import yaml
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


def setup_logging(config: Dict[str, Any] = None) -> logging.Logger:
    """
    Configure logging based on config.
    
    Args:
        config: Logging configuration dict
        
    Returns:
        Configured logger
    """
    if config is None:
        config = {}
    
    level_str = config.get("level", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)
    
    log_format = "%(asctime)s | %(levelname)-8s | %(message)s"
    date_format = "%H:%M:%S"
    
    # Configure root logger
    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt=date_format,
    )
    
    # File handler if specified
    log_file = config.get("log_file")
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(log_format, date_format))
        logging.getLogger().addHandler(file_handler)
    
    return logging.getLogger(__name__)


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """
    Load YAML config with environment variable substitution.
    
    Args:
        config_path: Path to config file
        
    Returns:
        Configuration dict
    """
    default_config = {
        "anthropic": {
            "api_key": os.getenv("ANTHROPIC_API_KEY", ""),
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 100,
            "temperature": 0.3,
        },
        "gemini": {
            "api_key": os.getenv("GEMINI_API_KEY", ""),
            "model": "gemini-2.0-flash",
        },
        "game": {
            "environment": "zero_ad_rl/CavalryVsInfantry-v0",
            "render": False,
            "max_steps_per_episode": 500,
        },
        "policy": {
            "provider": "gemini",
            "conversation_history_length": 20,
        },
        "logging": {
            "level": "INFO",
            "log_file": None,
            "save_episodes": True,
            "episode_dir": "./episodes/",
        }
    }
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                content = f.read()
                
            # Substitute environment variables
            for key, value in os.environ.items():
                content = content.replace(f"${{{key}}}", value)
                content = content.replace(f"${key}", value)
            
            file_config = yaml.safe_load(content)
            
            # Deep merge with defaults
            if file_config:
                _deep_merge(default_config, file_config)
                
        except Exception as e:
            logging.warning(f"Could not load config from {config_path}: {e}")
    
    return default_config


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """Deep merge override into base dict."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def save_episode(
    episode_num: int,
    observations: List[Dict],
    actions: List[int],
    rewards: List[float],
    save_dir: str = "./episodes/",
    metadata: Dict = None,
) -> str:
    """
    Save episode data for later analysis.
    
    Args:
        episode_num: Episode number
        observations: List of observations
        actions: List of actions taken
        rewards: List of rewards received
        save_dir: Directory to save episodes
        metadata: Additional metadata to save
        
    Returns:
        Path to saved file
    """
    # Create directory
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    
    # Create episode data
    episode_data = {
        "episode": episode_num,
        "timestamp": datetime.now().isoformat(),
        "total_steps": len(actions),
        "total_reward": sum(rewards),
        "actions": actions,
        "rewards": rewards,
        "metadata": metadata or {},
    }
    
    # Don't save full observations (too large), just summaries
    if observations:
        episode_data["final_observation_summary"] = {
            "units_remaining": len(observations[-1].get("units", [])) if isinstance(observations[-1], dict) else 0,
        }
    
    # Save to file
    filename = f"episode_{episode_num:04d}.json"
    filepath = os.path.join(save_dir, filename)
    
    with open(filepath, 'w') as f:
        json.dump(episode_data, f, indent=2, default=str)
    
    return filepath


def print_episode_summary(
    episode_num: int,
    total_reward: float,
    total_steps: int,
    win: bool = None,
    duration_seconds: float = None,
):
    """
    Pretty print episode results.
    
    Args:
        episode_num: Episode number
        total_reward: Total reward accumulated
        total_steps: Number of steps taken
        win: Whether the episode was won (if known)
        duration_seconds: Episode duration in seconds
    """
    print("\n" + "=" * 50)
    print(f"📊 EPISODE {episode_num} COMPLETE")
    print("=" * 50)
    
    print(f"  Steps:        {total_steps}")
    print(f"  Total Reward: {total_reward:.2f}")
    
    if win is not None:
        result = "🏆 VICTORY!" if win else "💀 DEFEAT"
        print(f"  Result:       {result}")
    
    if duration_seconds is not None:
        mins = int(duration_seconds // 60)
        secs = int(duration_seconds % 60)
        print(f"  Duration:     {mins}m {secs}s")
    
    print("=" * 50 + "\n")


def print_turn_info(
    turn: int,
    action: int,
    reward: float = None,
    action_description: str = None,
    verbose: bool = True,
):
    """Print info for a single turn."""
    if not verbose:
        return
    
    desc = action_description or f"Action {action}"
    reward_str = f" → Reward: {reward:.1f}" if reward is not None else ""
    
    print(f"Turn {turn:4d}: {desc}{reward_str}")


def format_time(seconds: float) -> str:
    """Format seconds as MM:SS."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"
