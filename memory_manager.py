"""
Memory Manager - Short-term and long-term memory for AI player.

Short-term: Last N turns (events, actions, outcomes)
Long-term: Markdown files with learned tips, strategies, game patterns

The AI can learn from gameplay and persist knowledge across sessions.
"""
import os
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class TurnEvent:
    """Record of a single turn."""
    turn: int
    timestamp: float
    game_time: float
    action: int
    action_description: str
    my_units: int
    my_buildings: int
    enemy_units: int
    resources: Dict[str, int]
    outcome: str = ""  # e.g., "trained worker", "attack failed"
    reward: float = 0.0


@dataclass
class GameStats:
    """Aggregate statistics for a game session."""
    total_turns: int = 0
    total_reward: float = 0.0
    units_trained: int = 0
    buildings_built: int = 0
    attacks_launched: int = 0
    successful_attacks: int = 0
    resources_gathered: Dict[str, int] = field(default_factory=dict)
    peak_units: int = 0
    peak_resources: int = 0


class MemoryManager:
    """
    Manages AI memory across turns and games.
    
    Short-term: In-memory list of recent turns
    Long-term: Markdown files with learned knowledge
    """
    
    def __init__(
        self,
        memory_dir: str = "./memory/",
        short_term_size: int = 20,
    ):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        self.short_term_size = short_term_size
        self.short_term: List[TurnEvent] = []
        self.game_stats = GameStats()
        
        # Current strategic goal
        self.current_strategy = "economy"  # economy, military, defense, expansion
        self.strategic_goals: List[str] = []
        
        # Load long-term memory
        self._load_long_term_memory()
    
    def record_turn(self, event: TurnEvent):
        """Record a turn event to short-term memory."""
        self.short_term.append(event)
        
        # Update stats
        self.game_stats.total_turns += 1
        self.game_stats.total_reward += event.reward
        self.game_stats.peak_units = max(self.game_stats.peak_units, event.my_units)
        
        total_res = sum(event.resources.values())
        self.game_stats.peak_resources = max(self.game_stats.peak_resources, total_res)
        
        # Track action types
        if event.action == 0:
            self.game_stats.units_trained += 1
        elif event.action == 7:
            self.game_stats.buildings_built += 1
        elif event.action in [2, 4]:
            self.game_stats.attacks_launched += 1
        
        # Trim short-term memory
        if len(self.short_term) > self.short_term_size * 2:
            self.short_term = self.short_term[-self.short_term_size:]
    
    def get_recent_turns(self, n: int = 5) -> List[TurnEvent]:
        """Get the last N turns from short-term memory."""
        return self.short_term[-n:]
    
    def get_short_term_summary(self) -> str:
        """Summarize recent events for the AI prompt."""
        if not self.short_term:
            return "No recent history."
        
        recent = self.short_term[-5:]
        lines = ["Recent turns:"]
        
        for event in recent:
            lines.append(f"  Turn {event.turn}: {event.action_description} → {event.outcome or 'ok'}")
        
        return "\n".join(lines)
    
    def set_strategy(self, strategy: str, goals: List[str] = None):
        """Set the current strategic focus."""
        self.current_strategy = strategy.lower()
        self.strategic_goals = goals or []
        logger.info(f"Strategy set to: {strategy}")
    
    def get_strategy_context(self) -> str:
        """Get current strategy for the prompt."""
        context = f"Current Strategy: {self.current_strategy.upper()}"
        if self.strategic_goals:
            context += f"\nGoals: {', '.join(self.strategic_goals)}"
        return context
    
    # Long-term memory methods
    
    def _load_long_term_memory(self):
        """Load knowledge from markdown files."""
        self.knowledge_files = {
            "tips": self.memory_dir / "tips.md",
            "strategies": self.memory_dir / "strategies.md",
            "patterns": self.memory_dir / "patterns.md",
        }
        
        # Create default files if they don't exist
        self._init_knowledge_files()
    
    def _init_knowledge_files(self):
        """Initialize knowledge files with default content."""
        defaults = {
            "tips": """# 0 AD Tips & Tricks

## Economy
- Always keep workers busy gathering resources
- Idle workers = wasted potential
- Balance resource gathering based on what you need

## Military
- Don't attack until you have a decent army
- Mixed unit compositions work better
- Protect your workers from raids

## General
- Build houses before hitting population cap
- Scout to find enemies early
- Defend your economy first
""",
            "strategies": """# Strategies Learned

## Early Game
- Focus on economy first
- Train 10-15 workers before military
- Build houses proactively

## Mid Game
- Build barracks and start military
- Maintain resource income
- Scout enemy positions

## Late Game
- Full army push when ready
- Protect your base while attacking
""",
            "patterns": """# Game Patterns Observed

## Enemy Behavior
- AI enemies often rush with infantry
- Watch for early raids on workers

## Resource Locations
- Food: Usually near starting location
- Wood: Forest around map edges
- Stone/Metal: Scattered, often contested
"""
        }
        
        for key, path in self.knowledge_files.items():
            if not path.exists():
                path.write_text(defaults[key])
                logger.info(f"Created knowledge file: {path}")
    
    def get_long_term_knowledge(self, category: str = None) -> str:
        """Get knowledge from long-term memory files."""
        if category and category in self.knowledge_files:
            path = self.knowledge_files[category]
            if path.exists():
                return path.read_text()
        
        # Return summary of all knowledge
        all_knowledge = []
        for cat, path in self.knowledge_files.items():
            if path.exists():
                content = path.read_text()
                # Get first 20 lines as summary
                lines = content.split("\n")[:20]
                all_knowledge.append(f"## {cat.title()}\n" + "\n".join(lines))
        
        return "\n\n".join(all_knowledge)
    
    def add_learned_tip(self, tip: str, category: str = "tips"):
        """Add a new tip to long-term memory."""
        if category not in self.knowledge_files:
            return
        
        path = self.knowledge_files[category]
        current = path.read_text() if path.exists() else ""
        
        # Add new tip with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d")
        new_content = current + f"\n\n## Learned {timestamp}\n- {tip}"
        
        path.write_text(new_content)
        logger.info(f"Added tip to {category}: {tip[:50]}...")
    
    def analyze_game_and_learn(self):
        """Analyze the game and extract lessons to long-term memory."""
        if not self.short_term:
            return
        
        lessons = []
        
        # Analyze resource patterns
        if self.game_stats.peak_resources < 500:
            lessons.append("Need to focus more on economy early game")
        
        # Analyze military success
        if self.game_stats.attacks_launched > 0:
            success_rate = self.game_stats.successful_attacks / self.game_stats.attacks_launched
            if success_rate < 0.3:
                lessons.append("Attacks failing - build larger army before attacking")
        
        # Analyze unit count
        if self.game_stats.peak_units < 15:
            lessons.append("Not training enough units - need more workers and military")
        
        for lesson in lessons:
            self.add_learned_tip(lesson, "patterns")
    
    def save_game_summary(self, outcome: str = "unknown"):
        """Save a summary of the game to long-term memory."""
        summary_path = self.memory_dir / "game_history.jsonl"
        
        summary = {
            "timestamp": datetime.now().isoformat(),
            "turns": self.game_stats.total_turns,
            "reward": self.game_stats.total_reward,
            "peak_units": self.game_stats.peak_units,
            "outcome": outcome,
            "strategy": self.current_strategy,
        }
        
        with open(summary_path, "a") as f:
            f.write(json.dumps(summary) + "\n")
        
        logger.info(f"Saved game summary: {outcome}")
    
    def reset(self):
        """Reset short-term memory for new game."""
        # Save lessons from current game first
        self.analyze_game_and_learn()
        
        self.short_term = []
        self.game_stats = GameStats()
        self.current_strategy = "economy"
        self.strategic_goals = []
        
        logger.info("Memory reset for new game")
