"""
Observation Formatter - Converts gym observations into Claude-friendly prompts.

This module handles:
- Simplifying raw observations from the zero_ad_rl environment
- Creating structured prompts for the AI
- Parsing AI responses into valid actions
"""
import re
from typing import Dict, Any, List, Optional, Tuple


def simplify_observation(obs: Dict[str, Any], env=None) -> Dict[str, Any]:
    """
    Reduce observation to essential information.
    
    Args:
        obs: Raw observation from gym environment
        env: The gym environment (for metadata)
    
    Returns:
        Simplified dict with key information
    """
    simplified = {
        "turn": obs.get("time", 0),
        "my_units": [],
        "enemy_units": [],
        "resources": {},
        "buildings": [],
    }
    
    # Extract units
    units = obs.get("units", [])
    for unit in units:
        if isinstance(unit, dict):
            unit_info = {
                "id": unit.get("id"),
                "type": _get_unit_type(unit.get("template", "")),
                "health": unit.get("health", 100),
                "position": _simplify_position(unit.get("position", {})),
            }
            
            owner = unit.get("owner", 0)
            if owner == 1:  # Our units
                simplified["my_units"].append(unit_info)
            elif owner > 1:  # Enemy units
                simplified["enemy_units"].append(unit_info)
    
    # Extract resources
    if "players" in obs and len(obs["players"]) > 1:
        player = obs["players"][1]
        simplified["resources"] = {
            "food": player.get("food", 0),
            "wood": player.get("wood", 0),
            "stone": player.get("stone", 0),
            "metal": player.get("metal", 0),
        }
    
    return simplified


def _get_unit_type(template: str) -> str:
    """Extract readable unit type from template string."""
    if not template:
        return "unknown"
    
    # Extract last part of template path
    parts = template.split("/")
    if parts:
        name = parts[-1]
        # Remove rank suffixes
        for suffix in ["_a", "_b", "_c", "_e"]:
            if name.endswith(suffix):
                name = name[:-2]
        return name.replace("_", " ")
    return template


def _simplify_position(pos: Dict) -> Tuple[int, int]:
    """Convert position dict to simple tuple."""
    if isinstance(pos, dict):
        return (int(pos.get("x", 0)), int(pos.get("z", 0)))
    return (0, 0)


def create_claude_prompt(
    simplified_obs: Dict[str, Any],
    action_space,
    action_descriptions: List[str] = None,
    history: List[Dict] = None
) -> str:
    """
    Create the full prompt to send to Claude/AI.
    
    Args:
        simplified_obs: Simplified observation dict
        action_space: Gym action space (for valid actions)
        action_descriptions: Human-readable action descriptions
        history: Recent turn history
    
    Returns:
        Formatted prompt string
    """
    lines = []
    
    # Game state header
    turn = simplified_obs.get("turn", 0)
    lines.append(f"=== TURN {turn} ===")
    
    # Resources
    res = simplified_obs.get("resources", {})
    lines.append(f"\nResources: Food={res.get('food', 0)}, Wood={res.get('wood', 0)}, Stone={res.get('stone', 0)}, Metal={res.get('metal', 0)}")
    
    # My forces
    my_units = simplified_obs.get("my_units", [])
    if my_units:
        unit_counts = {}
        for u in my_units:
            t = u.get("type", "unit")
            unit_counts[t] = unit_counts.get(t, 0) + 1
        unit_summary = ", ".join(f"{v} {k}" for k, v in unit_counts.items())
        lines.append(f"\nYour Forces ({len(my_units)} units): {unit_summary}")
    else:
        lines.append("\nYour Forces: None visible")
    
    # Enemy forces
    enemy_units = simplified_obs.get("enemy_units", [])
    if enemy_units:
        enemy_counts = {}
        for u in enemy_units:
            t = u.get("type", "unit")
            enemy_counts[t] = enemy_counts.get(t, 0) + 1
        enemy_summary = ", ".join(f"{v} {k}" for k, v in enemy_counts.items())
        lines.append(f"Enemy Forces ({len(enemy_units)} units): {enemy_summary}")
    else:
        lines.append("Enemy Forces: None visible")
    
    # Available actions
    lines.append("\n--- AVAILABLE ACTIONS ---")
    
    if action_descriptions:
        for i, desc in enumerate(action_descriptions):
            lines.append(f"{i}: {desc}")
    elif hasattr(action_space, 'n'):
        # Discrete action space
        for i in range(min(action_space.n, 10)):
            lines.append(f"{i}: Action {i}")
    
    # Recent history (if provided)
    if history and len(history) > 0:
        lines.append("\n--- RECENT HISTORY ---")
        for h in history[-3:]:
            lines.append(f"Turn {h.get('turn')}: Action {h.get('action')} → Reward {h.get('reward', 0)}")
    
    # Instruction
    lines.append("\n--- INSTRUCTION ---")
    lines.append("Choose ONE action number. Reply with ONLY the number, nothing else.")
    lines.append("Example: 2")
    
    return "\n".join(lines)


def extract_action_from_response(response: str, action_space=None) -> Optional[int]:
    """
    Parse AI response to extract action number.
    
    Handles various response formats:
    - "3"
    - "Action 3"
    - "I choose action 2 because..."
    - "Let's do 5"
    
    Args:
        response: Raw AI response text
        action_space: Gym action space (for validation)
    
    Returns:
        Action number, or None if can't parse
    """
    if not response:
        return None
    
    response = response.strip()
    
    # Try direct number
    if response.isdigit():
        action = int(response)
        if _is_valid_action(action, action_space):
            return action
    
    # Try to find number in response
    patterns = [
        r'^(\d+)$',                    # Just a number
        r'action[:\s]+(\d+)',          # "action: 3" or "action 3"
        r'choose[:\s]+(\d+)',          # "choose 3"
        r'^(\d+)[:\.\s]',              # "3: because..." or "3. attack"
        r'(\d+)',                       # Any number (last resort)
    ]
    
    for pattern in patterns:
        match = re.search(pattern, response.lower())
        if match:
            action = int(match.group(1))
            if _is_valid_action(action, action_space):
                return action
    
    return None


def _is_valid_action(action: int, action_space) -> bool:
    """Check if action is valid for the action space."""
    if action_space is None:
        return action >= 0
    
    if hasattr(action_space, 'n'):
        return 0 <= action < action_space.n
    
    if hasattr(action_space, 'contains'):
        return action_space.contains(action)
    
    return action >= 0


def get_default_action_descriptions(env_name: str) -> List[str]:
    """Get default action descriptions for known environments."""
    
    # Default descriptions for CavalryVsInfantry
    if "cavalry" in env_name.lower():
        return [
            "Move units north",
            "Move units south", 
            "Move units east",
            "Move units west",
            "Attack nearest enemy",
            "Retreat to starting position",
            "Hold position",
            "Spread out",
            "Group up",
            "Do nothing",
        ]
    
    # Generic descriptions
    return [f"Action {i}" for i in range(10)]
