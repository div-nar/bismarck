#!/usr/bin/env python3
"""
Bismarck - Advanced AI Player for 0 A.D.

Features:
- Two-phase decision making (Strategic + Tactical)
- Short-term and long-term memory
- Dynamic action generation
- Game knowledge base

Usage:
    # Start 0 AD with RL interface:
    "/Applications/0 A.D..app/Contents/MacOS/pyrogenesis" --rl-interface=127.0.0.1:6000
    
    # Join existing game:
    python claude_player.py --join
"""
import argparse
import time
import sys
import logging
from typing import Optional, List, Dict, Any

from zero_ad_client import ZeroADDirectClient, GameState
from memory_manager import MemoryManager
from dynamic_actions import DynamicActionGenerator
from strategic_ai import StrategicAI
from utils import setup_logging, load_config, print_episode_summary

logger = logging.getLogger(__name__)


class LLMInterface:
    """Interface to LLM (Gemini/Claude) for decision making."""
    
    def __init__(self, provider: str = "gemini", model: str = None):
        self.provider = provider
        self.client = None
        self.model = model or "gemini-3-flash-preview"
        self._init_client()
    
    def _init_client(self):
        """Initialize the LLM client."""
        if self.provider == "gemini":
            from google import genai
            import os
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY environment variable not set")
            self.client = genai.Client(api_key=api_key)
            logger.info(f"Initialized Gemini with model {self.model}")
        else:
            import anthropic
            import os
            api_key = os.getenv("ANTHROPIC_API_KEY")
            self.client = anthropic.Anthropic(api_key=api_key)
            self.model = "claude-sonnet-4-20250514"
            logger.info(f"Initialized Claude with model {self.model}")
    
    def call(self, prompt: str) -> str:
        """Call the LLM with a prompt and return response."""
        try:
            if self.provider == "gemini":
                from google.genai import types
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=50,
                    )
                )
                return response.text.strip()
            else:
                message = self.client.messages.create(
                    model=self.model,
                    max_tokens=50,
                    temperature=0.3,
                    messages=[{"role": "user", "content": prompt}]
                )
                return message.content[0].text.strip()
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return "0"  # Default action


def run_game(
    client: ZeroADDirectClient,
    llm: LLMInterface,
    max_turns: int = 200,
    join_existing: bool = False,
    verbose: bool = True,
) -> Dict:
    """Run a game with the strategic AI."""
    start_time = time.time()
    
    # Initialize components
    memory = MemoryManager(memory_dir="./memory/")
    
    # Get initial state
    if join_existing:
        print("\n🎮 Joining existing game...")
        try:
            state = client.step()
        except Exception as e:
            print(f"❌ Could not get game state: {e}")
            return {"error": str(e)}
    else:
        print("\n🎮 Starting new game...")
        try:
            state = client.reset()
            memory.reset()
        except Exception as e:
            print(f"❌ Could not start game: {e}")
            return {"error": str(e)}
    
    # Detect civilization
    civ = "mace"
    if len(state.players) > 1:
        player = state.players[1]
        if isinstance(player, dict):
            civ = player.get("civ", "mace")
    
    print(f"✓ Connected! Civ: {civ.upper()}, Units: {len(state.my_units)}, Buildings: {len(state.my_buildings)}")
    
    # Initialize AI
    action_generator = DynamicActionGenerator(civ=civ)
    strategic_ai = StrategicAI(
        memory=memory,
        action_generator=action_generator,
        strategic_interval=15,  # Re-evaluate strategy every 15 turns
    )
    
    total_reward = 0.0
    done = False
    
    print("\n🎯 Bismarck AI is now playing...")
    print("=" * 60)
    
    while not done and strategic_ai.turn_count < max_turns:
        # Make decision using two-phase AI
        commands, action_desc = strategic_ai.make_decision(
            state=state,
            call_llm_func=llm.call,
        )
        
        # Log action
        print(f"[{strategic_ai.get_status_summary()}] → {action_desc}")
        
        # Execute commands
        try:
            state = client.step(commands)
        except Exception as e:
            logger.error(f"Game error: {e}")
            break
        
        # Calculate reward (simple version)
        reward = len(state.my_units) * 0.1 + sum(state.resources.values()) * 0.001
        total_reward += reward
        
        # Record to memory
        strategic_ai.record_turn_result(state, action_desc, reward)
        
        # Check game over (after 20 turns)
        if strategic_ai.turn_count > 20:
            if not state.my_units and not state.my_buildings:
                print("\n💀 Defeat - all forces lost!")
                done = True
                memory.save_game_summary("defeat")
        
        # Show progress every 10 turns
        if verbose and strategic_ai.turn_count % 10 == 0:
            workers = len([u for u in state.my_units if "female" in u["name"].lower()])
            military = len(state.my_units) - workers
            print(f"\n--- Turn {strategic_ai.turn_count} Summary ---")
            print(f"    Workers: {workers}, Military: {military}")
            print(f"    Resources: F={state.resources.get('food')}, W={state.resources.get('wood')}")
            print(f"    Strategy: {strategic_ai.current_strategy.upper()}")
        
        # Small delay
        time.sleep(0.3)
    
    # Game finished
    duration = time.time() - start_time
    memory.save_game_summary("completed")
    
    print_episode_summary(
        episode_num=1,
        total_reward=total_reward,
        total_steps=strategic_ai.turn_count,
        win=None,
        duration_seconds=duration,
    )
    
    return {
        "turns": strategic_ai.turn_count,
        "reward": total_reward,
        "duration": duration,
        "final_strategy": strategic_ai.current_strategy,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Bismarck - Advanced AI for 0 A.D.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python claude_player.py --join     # Join your running game
  python claude_player.py            # Start new game
  python claude_player.py --turns 50 # Run for 50 turns
        """
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6000)
    parser.add_argument("--turns", type=int, default=200, help="Max turns to play")
    parser.add_argument("--join", "-j", action="store_true", help="Join existing game")
    parser.add_argument("--provider", choices=["gemini", "anthropic"], default="gemini")
    parser.add_argument("--verbose", "-v", action="store_true", default=True)
    parser.add_argument("--config", default="config.yaml")
    
    args = parser.parse_args()
    
    # Setup
    config = load_config(args.config)
    setup_logging(config.get("logging", {}))
    
    print("=" * 60)
    print("  🎖️  BISMARCK - Advanced 0 A.D. AI Player")
    print("=" * 60)
    print("  Features: Strategic Planning | Dynamic Actions | Memory")
    print("=" * 60)
    
    # Connect to 0 AD
    client = ZeroADDirectClient(args.host, args.port)
    
    if not client.connect():
        print("\n❌ Could not connect to 0 AD")
        print('\nStart 0 AD with:')
        print('  "/Applications/0 A.D..app/Contents/MacOS/pyrogenesis" --rl-interface=127.0.0.1:6000')
        sys.exit(1)
    
    # Initialize LLM
    llm = LLMInterface(provider=args.provider)
    
    try:
        result = run_game(
            client=client,
            llm=llm,
            max_turns=args.turns,
            join_existing=args.join,
            verbose=args.verbose,
        )
        print(f"\n✓ Game completed! Final strategy: {result.get('final_strategy', 'unknown').upper()}")
    except KeyboardInterrupt:
        print("\n\n⏹️ Stopped by user")
    finally:
        client.close()


if __name__ == "__main__":
    main()
