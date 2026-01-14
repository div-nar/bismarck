"""
Basic tests for the Claude 0 AD Player.

Run with: python -m pytest test_basic.py -v
"""
import pytest
from observation_formatter import (
    simplify_observation,
    create_claude_prompt,
    extract_action_from_response,
    _get_unit_type,
)


class TestObservationFormatter:
    """Tests for observation formatting."""
    
    def test_simplify_observation_empty(self):
        """Empty observation returns empty structure."""
        result = simplify_observation({})
        assert "my_units" in result
        assert "enemy_units" in result
        assert result["my_units"] == []
    
    def test_simplify_observation_with_units(self):
        """Units are properly categorized by owner."""
        obs = {
            "time": 100,
            "units": [
                {"id": 1, "template": "cavalry", "owner": 1, "health": 100, "position": {"x": 10, "z": 20}},
                {"id": 2, "template": "infantry", "owner": 2, "health": 80, "position": {"x": 50, "z": 60}},
            ],
            "players": [{}, {"food": 500, "wood": 300}]
        }
        
        result = simplify_observation(obs)
        
        assert len(result["my_units"]) == 1
        assert len(result["enemy_units"]) == 1
        assert result["my_units"][0]["id"] == 1
        assert result["enemy_units"][0]["id"] == 2
    
    def test_get_unit_type(self):
        """Unit type extraction from template string."""
        assert _get_unit_type("units/rome/cavalry_b") == "cavalry"
        assert _get_unit_type("structures/athen/house_a") == "house"
        assert _get_unit_type("") == "unknown"


class TestActionParsing:
    """Tests for parsing AI responses."""
    
    def test_extract_simple_number(self):
        """Simple number response."""
        assert extract_action_from_response("3") == 3
        assert extract_action_from_response("0") == 0
    
    def test_extract_with_prefix(self):
        """Response with action prefix."""
        assert extract_action_from_response("Action 2") == 2
        assert extract_action_from_response("action: 5") == 5
        assert extract_action_from_response("I choose 4") == 4
    
    def test_extract_with_explanation(self):
        """Response with explanation."""
        assert extract_action_from_response("3: Attack the enemy") == 3
        assert extract_action_from_response("Let's do 2 because it's strategic") == 2
    
    def test_extract_invalid(self):
        """Invalid responses return None."""
        assert extract_action_from_response("") is None
        assert extract_action_from_response("I don't know what to do") is None
    
    def test_extract_with_action_space(self):
        """Validation against action space."""
        class MockSpace:
            n = 5
        
        space = MockSpace()
        assert extract_action_from_response("4", space) == 4
        assert extract_action_from_response("10", space) is None  # Out of range


class TestPromptCreation:
    """Tests for prompt creation."""
    
    def test_create_prompt_basic(self):
        """Basic prompt creation."""
        obs = {
            "turn": 10,
            "my_units": [{"type": "cavalry", "id": 1}],
            "enemy_units": [{"type": "infantry", "id": 2}],
            "resources": {"food": 500, "wood": 300, "stone": 100, "metal": 50},
        }
        
        class MockSpace:
            n = 10
        
        prompt = create_claude_prompt(obs, MockSpace())
        
        assert "TURN 10" in prompt
        assert "Food=500" in prompt
        assert "Your Forces" in prompt
        assert "Enemy Forces" in prompt
        assert "INSTRUCTION" in prompt


class TestConfigLoading:
    """Tests for config utilities."""
    
    def test_load_default_config(self):
        """Default config is returned when file doesn't exist."""
        from utils import load_config
        
        config = load_config("nonexistent_config.yaml")
        
        assert "gemini" in config
        assert "game" in config
        assert "logging" in config


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
