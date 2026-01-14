"""
Claude Policy - AI integration for making game decisions.

Supports both Anthropic Claude API and Google Gemini API.
Uses conversation history for context and strategic continuity.
"""
import os
import time
import random
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from observation_formatter import (
    simplify_observation,
    create_claude_prompt,
    extract_action_from_response,
    get_default_action_descriptions,
)

logger = logging.getLogger(__name__)


@dataclass
class TurnHistory:
    """Record of a single turn."""
    turn: int
    observation_summary: str
    action: int
    reward: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            "turn": self.turn,
            "action": self.action,
            "reward": self.reward,
        }


class ClaudePolicy:
    """
    AI policy that uses Claude or Gemini to make game decisions.
    
    Supports:
    - Anthropic Claude API
    - Google Gemini API (fallback/alternative)
    """
    
    def __init__(
        self,
        api_key: str = None,
        model: str = "gemini-2.0-flash",
        provider: str = "gemini",  # "gemini" or "anthropic"
        max_history: int = 20,
        temperature: float = 0.3,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        """
        Initialize the AI policy.
        
        Args:
            api_key: API key (reads from env if not provided)
            model: Model name to use
            provider: "gemini" or "anthropic"
            max_history: Number of turns to keep in history
            temperature: Sampling temperature
            max_retries: Number of API retry attempts
            retry_delay: Base delay between retries
        """
        self.provider = provider.lower()
        self.model = model
        self.max_history = max_history
        self.temperature = temperature
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        self.history: List[TurnHistory] = []
        self.turn_count = 0
        self.client = None
        self.action_descriptions: List[str] = []
        
        # Initialize API client
        self._init_client(api_key)
    
    def _init_client(self, api_key: str = None):
        """Initialize the appropriate API client."""
        if self.provider == "anthropic":
            try:
                import anthropic
                key = api_key or os.getenv("ANTHROPIC_API_KEY")
                if not key:
                    raise ValueError("ANTHROPIC_API_KEY not set")
                self.client = anthropic.Anthropic(api_key=key)
                logger.info(f"Initialized Anthropic client with model {self.model}")
            except ImportError:
                logger.warning("anthropic package not found, falling back to Gemini")
                self.provider = "gemini"
                self._init_client(api_key)
        else:
            # Default to Gemini
            from google import genai
            key = api_key or os.getenv("GEMINI_API_KEY")
            if not key:
                raise ValueError("GEMINI_API_KEY environment variable not set")
            self.client = genai.Client(api_key=key)
            self.model = "gemini-3-flash-preview"
            logger.info(f"Initialized Gemini client with model {self.model}")
    
    def get_action(self, observation: Dict[str, Any], env=None) -> int:
        """
        Given game observation, ask AI for action.
        
        Args:
            observation: Dict from env with game state
            env: Gym environment (for action space)
            
        Returns:
            action: Integer action ID valid for the action space
        """
        self.turn_count += 1
        action_space = env.action_space if env else None
        
        # Simplify observation
        simplified = simplify_observation(observation, env)
        
        # Get action descriptions
        if not self.action_descriptions and env:
            env_name = getattr(env, 'spec', None)
            env_name = env_name.id if env_name else "unknown"
            self.action_descriptions = get_default_action_descriptions(env_name)
        
        # Create prompt
        history_dicts = [h.to_dict() for h in self.history[-5:]]
        prompt = create_claude_prompt(
            simplified,
            action_space,
            self.action_descriptions,
            history_dicts
        )
        
        # Call AI with retries
        action = self._call_ai_with_retry(prompt, action_space)
        
        # Record history
        self.history.append(TurnHistory(
            turn=self.turn_count,
            observation_summary=f"Units: {len(simplified.get('my_units', []))} vs {len(simplified.get('enemy_units', []))}",
            action=action,
        ))
        
        # Trim history
        if len(self.history) > self.max_history * 2:
            self.history = self.history[-self.max_history:]
        
        logger.info(f"Turn {self.turn_count}: Selected action {action}")
        return action
    
    def _call_ai_with_retry(self, prompt: str, action_space) -> int:
        """Call AI with exponential backoff retry."""
        for attempt in range(self.max_retries):
            try:
                response = self._call_ai(prompt)
                action = extract_action_from_response(response, action_space)
                
                if action is not None:
                    return action
                
                logger.warning(f"Could not parse action from: {response[:100]}")
                
            except Exception as e:
                logger.error(f"API error (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    time.sleep(delay)
        
        # Fallback to random action
        default = self._get_default_action(action_space)
        logger.warning(f"Using default action: {default}")
        return default
    
    def _call_ai(self, prompt: str) -> str:
        """Call the AI API and get response."""
        if self.provider == "anthropic":
            return self._call_anthropic(prompt)
        else:
            return self._call_gemini(prompt)
    
    def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic Claude API."""
        message = self.client.messages.create(
            model=self.model,
            max_tokens=100,
            temperature=self.temperature,
            system="You are playing a real-time strategy game. Choose actions by responding with ONLY a number.",
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    
    def _call_gemini(self, prompt: str) -> str:
        """Call Google Gemini API."""
        from google.genai import types
        
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are playing a real-time strategy game. Choose actions by responding with ONLY a number.",
                temperature=self.temperature,
                max_output_tokens=50,
            )
        )
        return response.text
    
    def _get_default_action(self, action_space) -> int:
        """Get a safe default action."""
        if action_space and hasattr(action_space, 'n'):
            # Random valid action
            return random.randint(0, action_space.n - 1)
        return 0
    
    def update_reward(self, reward: float):
        """Update the last turn's reward."""
        if self.history:
            self.history[-1].reward = reward
    
    def reset(self):
        """Reset for new episode."""
        self.history = []
        self.turn_count = 0
        logger.info("Policy reset for new episode")
    
    def get_strategy_summary(self) -> str:
        """Get a summary of the strategy used."""
        if not self.history:
            return "No actions taken"
        
        total_reward = sum(h.reward for h in self.history)
        action_counts = {}
        for h in self.history:
            action_counts[h.action] = action_counts.get(h.action, 0) + 1
        
        most_common = max(action_counts.items(), key=lambda x: x[1])
        
        return f"Turns: {len(self.history)}, Total Reward: {total_reward:.1f}, Most Used Action: {most_common[0]} ({most_common[1]} times)"
