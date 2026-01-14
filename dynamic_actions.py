"""
Dynamic Action Generator - Creates context-aware actions based on game state.

Instead of fixed 10 actions, generates relevant actions based on:
- Current buildings and what they can train
- Available resources and what can be afforded
- Military situation (enemies visible, under attack)
- Economy state (idle workers, resource needs)
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from zero_ad_client import GameState, Commands
from game_knowledge import get_unit_template, CIV_UNITS

logger = logging.getLogger(__name__)


@dataclass
class DynamicAction:
    """A dynamically generated action."""
    id: int
    name: str
    description: str
    category: str  # economy, military, defense, build
    priority: int  # Higher = more important (1-10)
    command_generator: callable  # Function that generates the command
    requirements: Dict[str, int] = None  # Resource requirements


class DynamicActionGenerator:
    """
    Generates available actions based on current game state.
    
    Actions are context-aware:
    - Only show train options for buildings that exist
    - Only show attack if enemies are visible
    - Prioritize actions based on game phase
    """
    
    # Resource costs for common actions (approximate)
    COSTS = {
        "female_citizen": {"food": 50},
        "infantry_spearman": {"food": 50, "wood": 35},
        "infantry_pikeman": {"food": 50, "wood": 40},
        "cavalry": {"food": 100, "wood": 50},
        "house": {"wood": 100},
        "barracks": {"wood": 150, "stone": 100},
        "farmstead": {"wood": 100},
    }
    
    def __init__(self, civ: str = "mace"):
        self.civ = civ
        self.action_counter = 0
    
    def generate_actions(self, state: GameState) -> List[DynamicAction]:
        """Generate all available actions for current state."""
        self.action_counter = 0
        actions = []
        
        # Economy actions
        actions.extend(self._generate_economy_actions(state))
        
        # Training actions
        actions.extend(self._generate_training_actions(state))
        
        # Building actions
        actions.extend(self._generate_building_actions(state))
        
        # Military actions
        actions.extend(self._generate_military_actions(state))
        
        # Always include wait action
        actions.append(DynamicAction(
            id=self._next_id(),
            name="Wait",
            description="Do nothing this turn",
            category="misc",
            priority=1,
            command_generator=lambda s: []
        ))
        
        # Sort by priority (highest first)
        actions.sort(key=lambda a: -a.priority)
        
        return actions
    
    def _next_id(self) -> int:
        self.action_counter += 1
        return self.action_counter - 1
    
    def _can_afford(self, state: GameState, item: str) -> bool:
        """Check if we can afford an item."""
        costs = self.COSTS.get(item, {})
        for resource, amount in costs.items():
            if state.resources.get(resource, 0) < amount:
                return False
        return True
    
    def _generate_economy_actions(self, state: GameState) -> List[DynamicAction]:
        """Generate economy-related actions."""
        actions = []
        
        # Find idle workers
        workers = [u for u in state.my_units if "female" in u["name"].lower() or "citizen" in u["name"].lower()]
        idle_workers = [u for u in workers if u.get("idle", False)]
        
        if idle_workers:
            # High priority: put idle workers to work
            for resource in ["food", "wood", "stone", "metal"]:
                priority = 8 if resource == "food" else 6
                
                # Check what we're low on
                if state.resources.get(resource, 0) < 100:
                    priority += 2
                
                actions.append(DynamicAction(
                    id=self._next_id(),
                    name=f"Gather {resource.title()}",
                    description=f"Send {len(idle_workers)} idle workers to gather {resource}",
                    category="economy",
                    priority=priority,
                    command_generator=lambda s, r=resource, w=idle_workers: self._gather_command(s, w, r)
                ))
        
        return actions
    
    def _generate_training_actions(self, state: GameState) -> List[DynamicAction]:
        """Generate unit training actions based on available buildings."""
        actions = []
        
        for building in state.my_buildings:
            name = building["name"].lower()
            
            # Civic center - train workers
            if "civil" in name or "centre" in name or "center" in name:
                if self._can_afford(state, "female_citizen"):
                    # Higher priority if few workers
                    workers = len([u for u in state.my_units if "female" in u["name"].lower()])
                    priority = 7 if workers < 10 else 4
                    
                    actions.append(DynamicAction(
                        id=self._next_id(),
                        name="Train Worker",
                        description="Train a female citizen from civic center",
                        category="economy",
                        priority=priority,
                        requirements=self.COSTS["female_citizen"],
                        command_generator=lambda s, b=building: [Commands.train(
                            b["id"], get_unit_template(self.civ, "female_citizen")
                        )]
                    ))
            
            # Barracks - train infantry
            elif "barracks" in name:
                if self._can_afford(state, "infantry_spearman"):
                    actions.append(DynamicAction(
                        id=self._next_id(),
                        name="Train Spearman",
                        description="Train infantry spearman from barracks",
                        category="military",
                        priority=5,
                        requirements=self.COSTS["infantry_spearman"],
                        command_generator=lambda s, b=building: [Commands.train(
                            b["id"], get_unit_template(self.civ, "infantry_spearman")
                        )]
                    ))
            
            # Stable - train cavalry
            elif "stable" in name:
                if self._can_afford(state, "cavalry"):
                    actions.append(DynamicAction(
                        id=self._next_id(),
                        name="Train Cavalry",
                        description="Train cavalry unit from stable",
                        category="military",
                        priority=5,
                        requirements=self.COSTS["cavalry"],
                        command_generator=lambda s, b=building: [Commands.train(
                            b["id"], get_unit_template(self.civ, "cavalry")
                        )]
                    ))
        
        return actions
    
    def _generate_building_actions(self, state: GameState) -> List[DynamicAction]:
        """Generate building construction actions."""
        actions = []
        workers = [u for u in state.my_units if "female" in u["name"].lower()]
        
        if not workers:
            return actions
        
        # Build house if near pop cap
        if state.population >= state.population_limit - 3:
            if self._can_afford(state, "house"):
                actions.append(DynamicAction(
                    id=self._next_id(),
                    name="Build House",
                    description=f"Build house (pop: {state.population}/{state.population_limit})",
                    category="build",
                    priority=9,  # High priority when pop capped
                    requirements=self.COSTS["house"],
                    command_generator=lambda s, w=workers: self._build_command(s, w[0], "house")
                ))
        
        # Build barracks if none
        has_barracks = any("barracks" in b["name"].lower() for b in state.my_buildings)
        if not has_barracks and self._can_afford(state, "barracks"):
            actions.append(DynamicAction(
                id=self._next_id(),
                name="Build Barracks",
                description="Build barracks to train military",
                category="build",
                priority=6,
                requirements=self.COSTS["barracks"],
                command_generator=lambda s, w=workers: self._build_command(s, w[0], "barracks")
            ))
        
        return actions
    
    def _generate_military_actions(self, state: GameState) -> List[DynamicAction]:
        """Generate military actions."""
        actions = []
        
        military = [u for u in state.my_units if "female" not in u["name"].lower() and "citizen" not in u["name"].lower()]
        
        if not military:
            return actions
        
        # Attack if enemies visible
        if state.enemy_units:
            closest_enemy = state.enemy_units[0]
            
            actions.append(DynamicAction(
                id=self._next_id(),
                name="Attack Enemy",
                description=f"Attack nearest enemy with {len(military)} military units",
                category="military",
                priority=5,
                command_generator=lambda s, m=military, e=closest_enemy: [
                    Commands.attack([u["id"] for u in m], e["id"])
                ]
            ))
            
            # All-out attack
            all_units = state.my_units
            actions.append(DynamicAction(
                id=self._next_id(),
                name="All-Out Attack",
                description=f"Attack with ALL {len(all_units)} units (risky!)",
                category="military",
                priority=3,
                command_generator=lambda s, a=all_units, e=closest_enemy: [
                    Commands.attack([u["id"] for u in a], e["id"])
                ]
            ))
        
        # Defend base
        if state.my_buildings:
            civic = next((b for b in state.my_buildings if "civil" in b["name"].lower()), state.my_buildings[0])
            pos = civic["position"]
            
            actions.append(DynamicAction(
                id=self._next_id(),
                name="Defend Base",
                description=f"Move {len(military)} military units to defend base",
                category="defense",
                priority=4,
                command_generator=lambda s, m=military, p=pos: [
                    Commands.move([u["id"] for u in m], p.get("x", 0), p.get("z", 0))
                ]
            ))
        
        return actions
    
    def _gather_command(self, state: GameState, workers: List[Dict], resource: str) -> List[Dict]:
        """Generate gather commands (simplified - moves workers in a direction)."""
        # In a full implementation, we'd find actual resource entities
        # For now, just move workers to approximate locations
        if not workers or not state.my_buildings:
            return []
        
        civic = next((b for b in state.my_buildings if "civil" in b["name"].lower()), state.my_buildings[0])
        base_x = civic["position"].get("x", 0)
        base_z = civic["position"].get("z", 0)
        
        # Direction offsets for different resources
        offsets = {
            "food": (50, 0),
            "wood": (-50, 0),
            "stone": (0, 50),
            "metal": (0, -50),
        }
        
        offset = offsets.get(resource, (30, 30))
        target_x = base_x + offset[0]
        target_z = base_z + offset[1]
        
        return [Commands.move([w["id"] for w in workers], target_x, target_z)]
    
    def _build_command(self, state: GameState, worker: Dict, building_type: str) -> List[Dict]:
        """Generate build command."""
        if not state.my_buildings:
            return []
        
        civic = next((b for b in state.my_buildings if "civil" in b["name"].lower()), state.my_buildings[0])
        base_x = civic["position"].get("x", 0)
        base_z = civic["position"].get("z", 0)
        
        # Offset for new building
        import random
        offset_x = random.randint(-30, 30)
        offset_z = random.randint(-30, 30)
        
        template = f"structures/{self.civ}/{building_type}"
        
        return [Commands.build([worker["id"]], template, base_x + offset_x, base_z + offset_z)]
    
    def format_actions_for_prompt(self, actions: List[DynamicAction]) -> str:
        """Format actions as numbered list for LLM prompt."""
        lines = []
        for action in actions:
            cost_str = ""
            if action.requirements:
                costs = [f"{v} {k}" for k, v in action.requirements.items()]
                cost_str = f" (cost: {', '.join(costs)})"
            
            lines.append(f"{action.id}: [{action.category.upper()}] {action.name}{cost_str}")
            lines.append(f"    {action.description}")
        
        return "\n".join(lines)
    
    def execute_action(self, action_id: int, actions: List[DynamicAction], state: GameState) -> List[Dict]:
        """Execute an action by ID and return commands."""
        for action in actions:
            if action.id == action_id:
                commands = action.command_generator(state)
                logger.info(f"Executing: {action.name} → {len(commands)} command(s)")
                return commands
        
        logger.warning(f"Action ID {action_id} not found")
        return []
