"""
Direct 0 AD Client - Connects to the game's RL interface via HTTP.

This bypasses the zero_ad_rl Gym package and connects directly to 0 AD's
built-in RL interface, allowing play of any map/scenario.

Usage:
    Start 0 AD with: pyrogenesis --rl-interface=127.0.0.1:6000
"""
import requests
import json
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class GameState:
    """Current game state from 0 AD."""
    entities: List[Dict[str, Any]] = field(default_factory=list)
    players: List[Dict[str, Any]] = field(default_factory=list)
    time: float = 0.0
    
    # Parsed data
    my_units: List[Dict] = field(default_factory=list)
    my_buildings: List[Dict] = field(default_factory=list)
    enemy_units: List[Dict] = field(default_factory=list)
    enemy_buildings: List[Dict] = field(default_factory=list)
    resources: Dict[str, int] = field(default_factory=dict)
    population: int = 0
    population_limit: int = 0


class ZeroADDirectClient:
    """
    Direct HTTP client for 0 AD's RL interface.
    
    Connects to the game via HTTP to:
    - Reset/start games
    - Step the simulation
    - Send commands (train, move, attack, build, etc.)
    """
    
    def __init__(self, host: str = "127.0.0.1", port: int = 6000, player_id: int = 1):
        self.base_url = f"http://{host}:{port}"
        self.player_id = player_id
        self.session = requests.Session()
        self.timeout = 30
        self.connected = False
        self.game_started = False
    
    def connect(self) -> bool:
        """Test connection to 0 AD."""
        try:
            # Try a step to see if game is running
            response = self.session.post(
                f"{self.base_url}/step",
                data="",
                timeout=5
            )
            self.connected = True
            logger.info(f"Connected to 0 AD at {self.base_url}")
            return True
        except requests.exceptions.ConnectionError:
            logger.error(f"Could not connect to 0 AD at {self.base_url}")
            logger.info('Start 0 AD with: "/Applications/0 A.D..app/Contents/MacOS/pyrogenesis" --rl-interface=127.0.0.1:6000')
            return False
        except Exception as e:
            # May get errors but still be connected
            self.connected = True
            logger.info(f"Connected to 0 AD at {self.base_url}")
            return True
    
    def reset(self, config: Dict[str, Any] = None) -> GameState:
        """
        Reset/start a new game.
        
        Args:
            config: Game configuration (map, players, etc.)
        """
        if config is None:
            config = self._default_game_config()
        
        try:
            response = self.session.post(
                f"{self.base_url}/reset",
                json=config,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            self.game_started = True
            logger.info("Game reset successfully")
            return self._parse_state(data)
        except Exception as e:
            logger.error(f"Reset failed: {e}")
            raise
    
    def step(self, commands: List[Dict] = None) -> GameState:
        """
        Advance the game by one step.
        
        Args:
            commands: List of commands to execute
        """
        try:
            if commands:
                payload = {"commands": [{"player": self.player_id, **cmd} for cmd in commands]}
                response = self.session.post(
                    f"{self.base_url}/step",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=self.timeout
                )
            else:
                response = self.session.post(
                    f"{self.base_url}/step",
                    data="",
                    timeout=self.timeout
                )
            
            response.raise_for_status()
            data = response.json()
            return self._parse_state(data)
        except Exception as e:
            logger.error(f"Step failed: {e}")
            raise
    
    def _parse_state(self, data: Dict) -> GameState:
        """Parse raw JSON into GameState."""
        # Entities is a DICT with entity IDs as string keys
        entities_dict = data.get("entities", {})
        
        # Convert dict to list of entities
        entities_list = []
        if isinstance(entities_dict, dict):
            entities_list = list(entities_dict.values())
        elif isinstance(entities_dict, list):
            entities_list = entities_dict
        
        state = GameState(
            entities=entities_list,
            players=data.get("players", []),
            time=data.get("timeElapsed", 0),  # Note: timeElapsed not time
        )
        
        # Parse entities
        for entity in entities_list:
            if not isinstance(entity, dict):
                continue
            
            owner = entity.get("owner", 0)
            template = entity.get("template", "")
            if not template:
                continue
            
            # Position is [x, z] array, not a dict
            pos = entity.get("position", [0, 0])
            if isinstance(pos, list) and len(pos) >= 2:
                position = {"x": pos[0], "z": pos[1]}
            elif isinstance(pos, dict):
                position = pos
            else:
                position = {"x": 0, "z": 0}
            
            info = {
                "id": entity.get("id"),
                "template": template,
                "name": self._extract_name(template),
                "health": entity.get("hitpoints", 100),
                "position": position,
                "idle": entity.get("idle", False),
            }
            
            is_building = self._is_building(template)
            
            # owner 0 = Gaia (resources, animals, etc)
            # owner 1 = Player 1 (usually us)
            # owner 2+ = Other players (enemies)
            if owner == self.player_id:
                if is_building:
                    state.my_buildings.append(info)
                else:
                    state.my_units.append(info)
            elif owner > 0 and owner != self.player_id:
                if is_building:
                    state.enemy_buildings.append(info)
                else:
                    state.enemy_units.append(info)
        
        # Parse player resources
        if len(state.players) > self.player_id:
            player = state.players[self.player_id]
            if isinstance(player, dict):
                res = player.get("resourceCounts", {})
                state.resources = {
                    "food": int(res.get("food", 0)),
                    "wood": int(res.get("wood", 0)),
                    "stone": int(res.get("stone", 0)),
                    "metal": int(res.get("metal", 0)),
                }
                state.population = player.get("popCount", 0)
                state.population_limit = player.get("popLimit", 0)
        
        logger.info(f"Parsed: {len(state.my_units)} units, {len(state.my_buildings)} buildings, "
                   f"vs {len(state.enemy_units)} enemy units")
        
        return state
    
    def _extract_name(self, template: str) -> str:
        """Get readable name from template."""
        parts = template.split("/")
        if parts:
            name = parts[-1]
            for suffix in ["_a", "_b", "_c", "_e"]:
                if name.endswith(suffix):
                    name = name[:-2]
            return name.replace("_", " ")
        return template
    
    def _is_building(self, template: str) -> bool:
        """Check if template is a building."""
        keywords = ["house", "barracks", "stable", "tower", "wall", "gate",
                   "centre", "center", "farm", "dock", "market", "temple",
                   "fortress", "storehouse", "farmstead", "field"]
        return any(kw in template.lower() for kw in keywords)
    
    def _default_game_config(self) -> Dict:
        """Default game configuration."""
        return {
            "settings": {
                "Name": "AI Game",
                "mapType": "scenario",
                "CheatsEnabled": True,
                "PlayerData": [
                    None,  # Gaia
                    {
                        "Name": "AI Player",
                        "Civ": "athen",
                        "AI": "",  # External control
                        "AIDiff": 3,
                        "Team": -1
                    },
                    {
                        "Name": "Enemy",
                        "Civ": "spart", 
                        "AI": "petra",  # Built-in AI
                        "AIDiff": 1,
                        "Team": -1
                    }
                ]
            },
            "map": "maps/scenarios/arcadia",
            "mapType": "scenario",
        }
    
    def close(self):
        """Close the session."""
        self.session.close()
        self.connected = False


# Command builders
class Commands:
    """Factory for creating game commands."""
    
    @staticmethod
    def train(building_id: int, unit_template: str) -> Dict:
        """Train a unit from a building."""
        return {
            "type": "train",
            "entities": [building_id],
            "template": unit_template
        }
    
    @staticmethod
    def move(unit_ids: List[int], x: float, z: float) -> Dict:
        """Move units to position."""
        return {
            "type": "walk",
            "entities": unit_ids,
            "x": x,
            "z": z
        }
    
    @staticmethod
    def attack(unit_ids: List[int], target_id: int) -> Dict:
        """Attack a target."""
        return {
            "type": "attack",
            "entities": unit_ids,
            "target": target_id
        }
    
    @staticmethod
    def gather(unit_ids: List[int], target_id: int) -> Dict:
        """Gather from a resource."""
        return {
            "type": "gather", 
            "entities": unit_ids,
            "target": target_id
        }
    
    @staticmethod
    def build(unit_ids: List[int], building_template: str, x: float, z: float) -> Dict:
        """Construct a building."""
        return {
            "type": "construct",
            "entities": unit_ids,
            "template": building_template,
            "x": x,
            "z": z
        }
