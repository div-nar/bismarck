"""
Strategic AI - Two-phase decision making for 0 AD.

Phase 1: Strategic Planning (every N turns)
- Assess overall game state
- Choose high-level strategy: Economy, Military, Defense, Expansion

Phase 2: Tactical Execution (every turn)
- Select specific action that supports current strategy
- Execute using dynamic action system
"""
import logging
from typing import List, Dict, Any, Optional, Tuple

from memory_manager import MemoryManager, TurnEvent
from dynamic_actions import DynamicActionGenerator, DynamicAction
from zero_ad_client import GameState
from game_knowledge import GAME_KNOWLEDGE_PROMPT

logger = logging.getLogger(__name__)


class StrategicAI:
    """
    Two-phase AI decision maker.
    
    Separates strategic thinking (what should we focus on?)
    from tactical execution (what specific action to take?).
    """
    
    STRATEGIES = {
        "economy": {
            "description": "Focus on building economy - workers, resources, infrastructure",
            "priority_categories": ["economy", "build"],
            "worker_threshold": 20,  # Goal: reach this many workers
        },
        "military": {
            "description": "Focus on military - train soldiers, prepare for attack",
            "priority_categories": ["military", "build"],
            "military_threshold": 15,  # Goal: reach this many military
        },
        "defense": {
            "description": "Defensive posture - protect base, counter enemy threats",
            "priority_categories": ["defense", "military"],
        },
        "attack": {
            "description": "Aggressive attack - push to destroy enemy",
            "priority_categories": ["military"],
        },
    }
    
    def __init__(
        self,
        memory: MemoryManager,
        action_generator: DynamicActionGenerator,
        strategic_interval: int = 20,  # Re-evaluate strategy every N turns
    ):
        self.memory = memory
        self.action_generator = action_generator
        self.strategic_interval = strategic_interval
        
        self.current_strategy = "economy"
        self.last_strategic_turn = 0
        self.turn_count = 0
    
    def should_reevaluate_strategy(self) -> bool:
        """Check if it's time to re-evaluate strategy."""
        return (self.turn_count - self.last_strategic_turn) >= self.strategic_interval
    
    def create_strategic_prompt(self, state: GameState) -> str:
        """
        Create prompt for strategic planning (Phase 1).
        
        This asks the LLM to choose a high-level strategy.
        """
        # Count units by type
        workers = len([u for u in state.my_units if "female" in u["name"].lower()])
        military = len(state.my_units) - workers
        
        # Build state summary
        summary = f"""## Current Game Status (Turn {self.turn_count})

**Resources:**
- Food: {state.resources.get('food', 0)}
- Wood: {state.resources.get('wood', 0)}
- Stone: {state.resources.get('stone', 0)}
- Metal: {state.resources.get('metal', 0)}

**Population:** {state.population}/{state.population_limit}
- Workers: {workers}
- Military: {military}

**Buildings:** {len(state.my_buildings)}

**Enemy Status:**
- Visible enemy units: {len(state.enemy_units)}
- Visible enemy buildings: {len(state.enemy_buildings)}

**Recent History:**
{self.memory.get_short_term_summary()}
"""

        # Add knowledge context
        knowledge = self.memory.get_long_term_knowledge("strategies")
        knowledge_excerpt = knowledge[:500] if knowledge else ""

        prompt = f"""You are the strategic commander for a 0 A.D. game.

{summary}

**Known Strategies:**
{knowledge_excerpt}

**Available Strategies:**
1. ECONOMY - Build up workers and resources (recommended when workers < 15)
2. MILITARY - Train soldiers and prepare army (recommended when economy stable)
3. DEFENSE - Protect base from enemy attacks (recommended when under threat)
4. ATTACK - Launch offensive against enemy (recommended when army is strong)

Based on the current game state, which strategy should we focus on?

Reply with ONLY one word: ECONOMY, MILITARY, DEFENSE, or ATTACK"""

        return prompt
    
    def parse_strategy_response(self, response: str) -> str:
        """Parse LLM response to get strategy."""
        response = response.strip().upper()
        
        for strategy in self.STRATEGIES.keys():
            if strategy.upper() in response:
                return strategy
        
        # Default to economy if unclear
        return "economy"
    
    def create_tactical_prompt(
        self,
        state: GameState,
        actions: List[DynamicAction],
    ) -> str:
        """
        Create prompt for tactical execution (Phase 2).
        
        This asks the LLM to choose a specific action.
        """
        strategy_info = self.STRATEGIES[self.current_strategy]
        
        # Build state summary (concise)
        workers = len([u for u in state.my_units if "female" in u["name"].lower()])
        military = len(state.my_units) - workers
        
        summary = f"""Turn {self.turn_count} | Strategy: {self.current_strategy.upper()}
Resources: F={state.resources.get('food', 0)} W={state.resources.get('wood', 0)} S={state.resources.get('stone', 0)} M={state.resources.get('metal', 0)}
Units: {workers} workers, {military} military | Pop: {state.population}/{state.population_limit}
Enemy: {len(state.enemy_units)} units visible"""

        # Format actions
        action_list = self.action_generator.format_actions_for_prompt(actions)
        
        # Priority hint based on strategy
        priority_cats = strategy_info["priority_categories"]
        priority_hint = f"Prioritize [{', '.join(priority_cats).upper()}] actions for {self.current_strategy.upper()} strategy."

        prompt = f"""{summary}

Current Strategy: {self.current_strategy.upper()}
{strategy_info['description']}

{priority_hint}

Available Actions:
{action_list}

Choose the best action number for our {self.current_strategy.upper()} strategy.
Reply with ONLY the action number:"""

        return prompt
    
    def make_decision(
        self,
        state: GameState,
        call_llm_func,  # Function to call LLM: (prompt) -> response
    ) -> Tuple[List[Dict], str]:
        """
        Make a decision for this turn.
        
        Args:
            state: Current game state
            call_llm_func: Function to call LLM with a prompt
        
        Returns:
            Tuple of (commands, action_description)
        """
        self.turn_count += 1
        
        # Phase 1: Strategic planning (periodic)
        if self.should_reevaluate_strategy():
            logger.info("=== Phase 1: Strategic Planning ===")
            
            strategic_prompt = self.create_strategic_prompt(state)
            response = call_llm_func(strategic_prompt)
            
            new_strategy = self.parse_strategy_response(response)
            
            if new_strategy != self.current_strategy:
                logger.info(f"Strategy changed: {self.current_strategy} → {new_strategy}")
                self.current_strategy = new_strategy
                self.memory.set_strategy(new_strategy)
            
            self.last_strategic_turn = self.turn_count
        
        # Phase 2: Tactical execution
        logger.info(f"=== Phase 2: Tactical ({self.current_strategy.upper()}) ===")
        
        # Generate available actions
        actions = self.action_generator.generate_actions(state)
        
        # Filter/prioritize based on strategy
        actions = self._prioritize_for_strategy(actions)
        
        # Get tactical decision from LLM
        tactical_prompt = self.create_tactical_prompt(state, actions)
        response = call_llm_func(tactical_prompt)
        
        # Parse action choice
        action_id = self._parse_action_response(response, actions)
        
        # Execute action
        commands = self.action_generator.execute_action(action_id, actions, state)
        
        # Get action description for memory
        chosen_action = next((a for a in actions if a.id == action_id), None)
        action_desc = chosen_action.name if chosen_action else "Unknown"
        
        return commands, action_desc
    
    def _prioritize_for_strategy(self, actions: List[DynamicAction]) -> List[DynamicAction]:
        """Adjust action priorities based on current strategy."""
        strategy_info = self.STRATEGIES[self.current_strategy]
        priority_categories = strategy_info["priority_categories"]
        
        for action in actions:
            if action.category in priority_categories:
                action.priority += 3  # Boost priority
        
        # Re-sort by priority
        actions.sort(key=lambda a: -a.priority)
        
        return actions
    
    def _parse_action_response(self, response: str, actions: List[DynamicAction]) -> int:
        """Parse LLM response to get action ID."""
        import re
        
        response = response.strip()
        
        # Try to find number in response
        match = re.search(r'\d+', response)
        if match:
            action_id = int(match.group())
            # Validate it's a valid action
            valid_ids = [a.id for a in actions]
            if action_id in valid_ids:
                return action_id
        
        # Default to highest priority action
        if actions:
            return actions[0].id
        
        return 0
    
    def record_turn_result(
        self,
        state: GameState,
        action_desc: str,
        reward: float = 0.0,
    ):
        """Record the turn result to memory."""
        workers = len([u for u in state.my_units if "female" in u["name"].lower()])
        
        event = TurnEvent(
            turn=self.turn_count,
            timestamp=0,
            game_time=state.time,
            action=0,  # Not tracking action ID here
            action_description=action_desc,
            my_units=len(state.my_units),
            my_buildings=len(state.my_buildings),
            enemy_units=len(state.enemy_units),
            resources=dict(state.resources),
            outcome="",
            reward=reward,
        )
        
        self.memory.record_turn(event)
    
    def get_status_summary(self) -> str:
        """Get current AI status for logging."""
        return (f"Turn {self.turn_count} | Strategy: {self.current_strategy.upper()} | "
                f"Next eval in {self.strategic_interval - (self.turn_count - self.last_strategic_turn)} turns")
