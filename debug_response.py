#!/usr/bin/env python3
"""Debug script to see raw 0 AD RL interface response."""
import requests
import json

BASE_URL = "http://127.0.0.1:6000"

print("🔍 Sending step request to 0 AD...")

try:
    response = requests.post(f"{BASE_URL}/step", data="", timeout=10)
    data = response.json()
    
    print(f"\n✓ Got response!")
    print(f"\n📋 Top-level keys: {list(data.keys())}")
    
    # Check entities type
    entities = data.get("entities", {})
    print(f"\n🎮 Entities type: {type(entities).__name__}")
    print(f"🎮 Entities count: {len(entities)}")
    
    if isinstance(entities, dict):
        # It's a dict - keys are entity IDs
        keys = list(entities.keys())[:5]
        print(f"\n📦 First 5 entity IDs: {keys}")
        
        print("\n📦 Sample entities:")
        for key in keys[:2]:
            entity = entities[key]
            print(f"\n  Entity ID {key}:")
            if isinstance(entity, dict):
                for k, v in list(entity.items())[:12]:
                    val_str = str(v)[:60]
                    print(f"    {k}: {val_str}")
            else:
                print(f"    Value: {str(entity)[:100]}")
    elif isinstance(entities, list):
        print("\n📦 First 2 entities:")
        for i, e in enumerate(entities[:2]):
            print(f"\n  Entity {i}: {type(e)}")
            if isinstance(e, dict):
                for k, v in list(e.items())[:10]:
                    print(f"    {k}: {str(v)[:50]}")
    
    # Check players
    players = data.get("players", [])
    print(f"\n👥 Players type: {type(players).__name__}, count: {len(players)}")
    
    if players:
        print("\n📦 Player 1 data (your player):")
        if len(players) > 1:
            p = players[1]
            if isinstance(p, dict):
                for k, v in list(p.items())[:15]:
                    print(f"    {k}: {str(v)[:80]}")
    
    # Save full response
    with open("debug_response.json", "w") as f:
        json.dump(data, f, indent=2)
    print("\n💾 Full response saved to debug_response.json")
    
except Exception as e:
    import traceback
    print(f"❌ Error: {e}")
    traceback.print_exc()
