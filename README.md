# 🎮 Claude/Gemini 0 AD Player

An AI system that plays [0 A.D.](https://play0ad.com/) (open-source RTS game) using Claude or Gemini for strategic decision-making.

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    0 AD Game (Pyrogenesis)                  │
│                 RL Interface (TCP:6000)                     │
└─────────────────────────┬──────────────────────────────────┘
                          │ Gym Interface
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Python Controller                         │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │claude_player│→ │claude_policy │→ │observation_formatter│ │
│  │  (main)     │  │  (AI logic)  │  │   (prompts)        │  │
│  └─────────────┘  └──────────────┘  └────────────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          │ API
                          ▼
                ┌──────────────────┐
                │ Claude / Gemini  │
                └──────────────────┘
```

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Install zero_ad_rl (for real 0 AD)
```bash
git clone https://github.com/brollb/zero_ad_rl
cd zero_ad_rl
pip install -e .
```

### 3. Test with Mock Environment
```bash
python claude_player.py --episodes 1
```

### 4. Play Real 0 AD
```bash
# Terminal 1: Start 0 AD
"/Applications/0 A.D..app/Contents/MacOS/pyrogenesis" --rl-interface=127.0.0.1:6000 --mod=rl-scenarios --mod=public

# Terminal 2: Run AI
python claude_player.py --env zero_ad_rl/CavalryVsInfantry-v0 --episodes 1
```

## Usage

```bash
python claude_player.py --help

Options:
  --env ENV          Gym environment name (default: CavalryVsInfantry-v0)
  --episodes N       Number of episodes to play (default: 1)
  --max-steps N      Max steps per episode (default: 500)
  --render           Enable visual rendering
  --provider NAME    AI provider: "gemini" or "anthropic"
  --config FILE      Config file path (default: config.yaml)
  --verbose, -v      Detailed output
  --quiet, -q        Minimal output
```

## Files

| File | Purpose |
|------|---------|
| `claude_player.py` | Main entry point & game loop |
| `claude_policy.py` | AI integration (Claude/Gemini) |
| `observation_formatter.py` | Observation → prompt conversion |
| `utils.py` | Logging, config, episode saving |
| `config.yaml` | Configuration settings |
| `test_basic.py` | Unit tests |

## Configuration

Edit `config.yaml` to customize:
- AI provider (Gemini or Anthropic)
- Model and temperature
- Game settings
- Logging options

## API Keys

Set environment variables:
```bash
export GEMINI_API_KEY=your_key_here
# or
export ANTHROPIC_API_KEY=your_key_here
```

## How It Works

1. **Observation**: Game state received from 0 AD via Gym interface
2. **Simplify**: Raw observation converted to readable summary
3. **Prompt**: Summary formatted as prompt for AI
4. **Decision**: AI chooses action number
5. **Execute**: Action sent to game
6. **Repeat**: Loop until game ends

## Troubleshooting

### "zero_ad_rl not found"
The system uses a mock environment by default. Install zero_ad_rl for real gameplay.

### "Could not connect to 0 AD"
Ensure 0 AD is running with `--rl-interface=127.0.0.1:6000`

### "API error"
Check your API key in config or environment variables.

## Testing

```bash
python -m pytest test_basic.py -v
```
