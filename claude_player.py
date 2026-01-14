#!/usr/bin/env python3
"""
Claude Player - Main entry point for AI playing 0 AD.

Connects directly to 0 AD's RL interface to play any map.
"""
import argparse
import time
import sys
import logging
from typing import Optional, List, Dict, Any

from claude_policy import ClaudePolicy
from zero_ad_client import ZeroADDirectClient, GameState, Commands
from game_knowledge import get_unit_template, build_strategy_prompt, ACTION_DESCRIPTIONS
from utils import setup_logging, load_config, print_episode_summary

logger = logging.getLogger(__name__)


class GameController:
    """Controls the game using AI decisions."""
    
    def __init__(self, client: ZeroADDirectClient, policy: ClaudePolicy):
        self.client = client
        self.policy = policy
        self.civ = "mace"  # Will be detected from game
        self.player_entity_id = None
    
    def detect_civilization(self, state: GameState):
        """Detect player's civilization from game state."""
        if len(state.players) > 1:
            player = state.players[1]
            if isinstance(player, dict):
                self.civ = player.get("civ", "mace")
                self.player_entity_id = player.get("entity")
                logger.info(f"Detected civilization: {self.civ}")
    
    def format_state_for_ai(self, state: GameState) -> str:
        """Create a readable summary for the AI."""
        lines = []
        
        # Resources
        res = state.resources
        lines.append(f"Resources: Food={res.get('food', 0)}, Wood={res.get('wood', 0)}, "
                    f"Stone={res.get('stone', 0)}, Metal={res.get('metal', 0)}")
        lines.append(f"Population: {state.population}/{state.population_limit}")
        
        # Units summary
        workers = [u for u in state.my_units if "female" in u["name"].lower() or "citizen" in u["name"].lower()]
        military = [u for u in state.my_units if u not in workers]
        idle_workers = [u for u in workers if u.get("idle", False)]
        
        lines.append(f"\nYour Forces: {len(workers)} workers ({len(idle_workers)} idle), {len(military)} military")
        lines.append(f"Buildings: {len(state.my_buildings)}")
        
        # Building types
        building_types = {}
        for b in state.my_buildings:
            t = b["name"]
            building_types[t] = building_types.get(t, 0) + 1
        if building_types:
            lines.append(f"  Types: {building_types}")
        
        # Enemy
        lines.append(f"\nEnemy: {len(state.enemy_units)} units, {len(state.enemy_buildings)} buildings visible")
        
        # Warnings
        if idle_workers:
            lines.append("\n⚠️ You have idle workers! Send them to gather resources.")
        if state.population >= state.population_limit - 2:
            lines.append("⚠️ Near population cap! Build houses.")
        
        return "\n".join(lines)
    
    def action_to_commands(self, action: int, state: GameState) -> List[Dict]:
        """Convert action number to game commands with civ-specific templates."""
        commands = []
        
        # Get units
        workers = [u for u in state.my_units if "female" in u["name"].lower() or "citizen" in u["name"].lower()]
        military = [u for u in state.my_units if u not in workers]
        buildings = state.my_buildings
        
        # Get civ-specific templates
        female_template = get_unit_template(self.civ, "female_citizen")
        infantry_template = get_unit_template(self.civ, "infantry_spearman")
        
        if action == 0:
            # Train worker from civic center
            civic = next((b for b in buildings if "civil" in b["name"].lower() or "centre" in b["name"].lower()), None)
            if civic:
                cmd = Commands.train(civic["id"], female_template)
                commands.append(cmd)
                logger.info(f"→ Training worker from building {civic['id']}: {female_template}")
        
        elif action == 1:
            # Train infantry from barracks
            barracks = next((b for b in buildings if "barracks" in b["name"].lower()), None)
            if barracks:
                cmd = Commands.train(barracks["id"], infantry_template)
                commands.append(cmd)
                logger.info(f"→ Training infantry from barracks {barracks['id']}: {infantry_template}")
            else:
                logger.warning("No barracks found for training infantry")
        
        elif action == 2:
            # Attack nearest enemy with military
            if military and state.enemy_units:
                target = state.enemy_units[0]
                unit_ids = [u["id"] for u in military]
                cmd = Commands.attack(unit_ids, target["id"])
                commands.append(cmd)
                logger.info(f"→ Attacking enemy {target['id']} with {len(military)} units")
        
        elif action == 3:
            # Gather food - move workers toward map center (likely has farms/animals)
            if workers:
                # For now, just log - gathering requires finding resource entities
                logger.info(f"→ Would gather food with {len(workers)} workers (not implemented)")
        
        elif action == 4:
            # Attack with ALL units
            if state.my_units and state.enemy_units:
                target = state.enemy_units[0]
                unit_ids = [u["id"] for u in state.my_units]
                cmd = Commands.attack(unit_ids, target["id"])
                commands.append(cmd)
                logger.info(f"→ All-out attack on enemy {target['id']} with {len(state.my_units)} units")
        
        elif action == 5:
            # Defend - move military to base
            if military and buildings:
                civic = next((b for b in buildings if "civil" in b["name"].lower()), buildings[0])
                pos = civic["position"]
                unit_ids = [u["id"] for u in military]
                cmd = Commands.move(unit_ids, pos.get("x", 0), pos.get("z", 0))
                commands.append(cmd)
                logger.info(f"→ Defending base with {len(military)} units")
        
        elif action == 6:
            # Train cavalry (if stable exists)
            stable = next((b for b in buildings if "stable" in b["name"].lower()), None)
            if stable:
                cav_template = get_unit_template(self.civ, "cavalry")
                cmd = Commands.train(stable["id"], cav_template)
                commands.append(cmd)
                logger.info(f"→ Training cavalry from stable")
        
        elif action == 7:
            # Build house
            if workers:
                # Find a location near civic center
                civic = next((b for b in buildings if "civil" in b["name"].lower()), buildings[0] if buildings else None)
                if civic:
                    pos = civic["position"]
                    # Offset position slightly
                    x = pos.get("x", 0) + 20
                    z = pos.get("z", 0) + 20
                    house_template = f"structures/{self.civ}/house"
                    cmd = Commands.build([workers[0]["id"]], house_template, x, z)
                    commands.append(cmd)
                    logger.info(f"→ Building house at ({x}, {z})")
        
        elif action == 8:
            # Retreat to civic center
            if state.my_units and buildings:
                civic = next((b for b in buildings if "civil" in b["name"].lower()), buildings[0])
                pos = civic["position"]
                unit_ids = [u["id"] for u in state.my_units]
                cmd = Commands.move(unit_ids, pos.get("x", 0), pos.get("z", 0))
                commands.append(cmd)
                logger.info(f"→ Retreating all units to base")
        
        # Action 9 = do nothing
        elif action == 9:
            logger.info("→ Waiting (no action)")
        
        return commands


def run_game(
    client: ZeroADDirectClient,
    policy: ClaudePolicy,
    max_turns: int = 200,
    verbose: bool = True,
    join_existing: bool = False,
) -> Dict:
    """Run a single game."""
    start_time = time.time()
    
    controller = GameController(client, policy)
    
    if join_existing:
        print("\n🎮 Joining existing game...")
        try:
            state = client.step()
            controller.detect_civilization(state)
            print(f"✓ Joined! Civ: {controller.civ.upper()}, "
                  f"{len(state.my_units)} units, {len(state.my_buildings)} buildings")
        except Exception as e:
            print(f"❌ Could not get game state: {e}")
            return {"error": str(e)}
    else:
        print("\n🎮 Starting new game...")
        try:
            state = client.reset()
            controller.detect_civilization(state)
            print(f"✓ Game started! Civ: {controller.civ.upper()}")
        except Exception as e:
            print(f"❌ Could not start game: {e}")
            return {"error": str(e)}
    
    policy.reset()
    
    total_reward = 0.0
    turn = 0
    done = False
    actions_taken = []
    
    print("\n🎯 AI is now playing...")
    print("-" * 40)
    
    while not done and turn < max_turns:
        turn += 1
        
        # Format state for AI
        state_summary = controller.format_state_for_ai(state)
        
        # Use game knowledge prompt
        full_prompt = build_strategy_prompt(state_summary, controller.civ)
        
        # Get AI decision using observation format expected by policy
        obs = {
            "time": state.time,
            "units": [{"id": u["id"], "template": u["template"], "owner": 1} for u in state.my_units],
            "players": [{}, state.resources]
        }
        
        try:
            action = policy.get_action(obs, None)
        except Exception as e:
            logger.error(f"AI error: {e}")
            action = 9  # Do nothing
        
        # Convert to commands
        commands = controller.action_to_commands(action, state)
        
        # Log what we're doing
        if commands:
            print(f"Turn {turn}: Action {action} ({ACTION_DESCRIPTIONS[action].split(':')[1].strip()}) → {len(commands)} command(s)")
        else:
            print(f"Turn {turn}: Action {action} → No commands generated")
        
        # Execute
        try:
            state = client.step(commands)
        except Exception as e:
            logger.error(f"Game error: {e}")
            break
        
        # Reward
        reward = len(state.my_units) * 0.1 + state.resources.get("food", 0) * 0.001
        total_reward += reward
        policy.update_reward(reward)
        
        actions_taken.append(action)
        
        # Don't check game over too early
        if turn > 20:
            if not state.my_units and not state.my_buildings:
                print("💀 Defeat!")
                done = True
        
        # Delay to see what's happening
        time.sleep(0.5)
    
    duration = time.time() - start_time
    
    print_episode_summary(
        episode_num=1,
        total_reward=total_reward,
        total_steps=turn,
        win=None,
        duration_seconds=duration,
    )
    
    return {
        "turns": turn,
        "reward": total_reward,
        "actions": actions_taken,
        "duration": duration,
    }


def main():
    parser = argparse.ArgumentParser(
        description="AI player for 0 AD",
        epilog="""
Examples:
  python claude_player.py --join    # Join YOUR existing game
  python claude_player.py           # Start a new game
        """
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6000)
    parser.add_argument("--turns", type=int, default=200)
    parser.add_argument("--join", "-j", action="store_true",
                       help="Join existing game instead of starting new one")
    parser.add_argument("--verbose", "-v", action="store_true", default=True)
    parser.add_argument("--provider", choices=["gemini", "anthropic"], default="gemini")
    parser.add_argument("--config", default="config.yaml")
    
    args = parser.parse_args()
    
    config = load_config(args.config)
    setup_logging(config.get("logging", {}))
    
    print("=" * 60)
    print("🎮 0 AD AI Player")
    print("=" * 60)
    
    client = ZeroADDirectClient(args.host, args.port)
    
    if not client.connect():
        print("\n❌ Could not connect to 0 AD")
        print('Start with: "/Applications/0 A.D..app/Contents/MacOS/pyrogenesis" --rl-interface=127.0.0.1:6000')
        sys.exit(1)
    
    policy = ClaudePolicy(provider=args.provider)
    
    try:
        result = run_game(
            client, policy, args.turns, args.verbose,
            join_existing=args.join
        )
        print(f"\n✓ Completed in {result.get('turns', 0)} turns")
    except KeyboardInterrupt:
        print("\n\n⏹️ Stopped by user")
    finally:
        client.close()


if __name__ == "__main__":
    main()
