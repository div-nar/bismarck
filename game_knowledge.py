"""
0 AD Game Knowledge Base for AI Player.

This module contains:
- Game mechanics knowledge
- Unit/building templates by civilization
- Strategy guidelines
- System prompts for the LLM
"""

# Civilization unit templates
CIV_UNITS = {
    "mace": {  # Macedon
        "female_citizen": "units/mace/support_female_citizen",
        "infantry_spearman": "units/mace/infantry_spearman_b",
        "infantry_pikeman": "units/mace/infantry_pikeman_b",
        "cavalry": "units/mace/cavalry_spearman_b",
    },
    "athen": {  # Athens
        "female_citizen": "units/athen/support_female_citizen",
        "infantry_spearman": "units/athen/infantry_spearman_b",
        "infantry_slinger": "units/athen/infantry_slinger_b",
        "cavalry": "units/athen/cavalry_javelinist_b",
    },
    "spart": {  # Sparta
        "female_citizen": "units/spart/support_female_citizen",
        "infantry_spearman": "units/spart/infantry_spearman_b",
        "infantry_pikeman": "units/spart/infantry_pikeman_b",
    },
    "rome": {  # Rome
        "female_citizen": "units/rome/support_female_citizen",
        "infantry_swordsman": "units/rome/infantry_swordsman_b",
        "infantry_spearman": "units/rome/infantry_spearman_b",
    },
    "pers": {  # Persia
        "female_citizen": "units/pers/support_female_citizen",
        "infantry_spearman": "units/pers/infantry_spearman_b",
        "cavalry": "units/pers/cavalry_spearman_b",
    },
    # Default fallback
    "default": {
        "female_citizen": "units/mace/support_female_citizen",
        "infantry_spearman": "units/mace/infantry_spearman_b",
    }
}

# Building templates (mostly universal)
BUILDINGS = {
    "house": "structures/{civ}/house",
    "barracks": "structures/{civ}/barracks",
    "civic_center": "structures/{civ}/civil_centre",
    "storehouse": "structures/{civ}/storehouse",
    "farmstead": "structures/{civ}/farmstead",
    "farm": "structures/{civ}/field",
}


def get_unit_template(civ: str, unit_type: str) -> str:
    """Get unit template for a civilization."""
    civ = civ.lower()
    if civ not in CIV_UNITS:
        civ = "default"
    
    units = CIV_UNITS[civ]
    return units.get(unit_type, units.get("female_citizen", ""))


# System prompt for the LLM
GAME_KNOWLEDGE_PROMPT = """You are an AI playing 0 A.D., an open-source real-time strategy game similar to Age of Empires.

## Game Basics
- You control a civilization with workers, military units, and buildings
- Resources: Food, Wood, Stone, Metal
- Population: Each unit costs population space; build houses to increase limit
- Victory: Destroy all enemy buildings/units OR achieve other victory conditions

## Your Assets
- **Workers (female citizens)**: Gather resources, construct buildings
- **Military units**: Infantry, cavalry, ranged units - used for combat
- **Buildings**: Civic center (trains workers, main building), Barracks (trains infantry), Houses (increase pop limit)

## Key Strategies
1. **Economy First**: Keep workers gathering resources. Idle workers = wasted resources.
2. **Build Houses**: When near population cap, build houses.
3. **Train Military**: Once economy is stable, train military from barracks.
4. **Scout**: Know where enemies are before attacking.
5. **Defend**: Keep some units near your base.
6. **Attack**: When you have a strong army, attack enemy economy.

## Available Actions
You will choose from numbered actions. Pick the action number that best matches your strategy.

## Response Format
Reply with ONLY a single number (0-9). No explanation needed.
Example: 4
"""


# Action descriptions for the LLM prompt
ACTION_DESCRIPTIONS = [
    "0: Train a worker from civic center (costs food)",
    "1: Train infantry from barracks (costs food + wood)", 
    "2: Attack nearest enemy with military units",
    "3: Send workers to gather food",
    "4: Attack with ALL units (aggressive)",
    "5: Defend - move military to base",
    "6: Train cavalry (if available)",
    "7: Build a house (increases pop limit)",
    "8: Retreat all units to civic center",
    "9: Do nothing (wait)",
]


def build_strategy_prompt(state_summary: str, civ: str = "mace") -> str:
    """Build the full prompt for the LLM."""
    return f"""{GAME_KNOWLEDGE_PROMPT}

## Current Civilization: {civ.upper()}

## Current Game State:
{state_summary}

## Available Actions:
{chr(10).join(ACTION_DESCRIPTIONS)}

What action do you choose? Reply with ONLY the number:"""
