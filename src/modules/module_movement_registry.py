LEGS_ONLY = "legs_only"
HAS_ARMS = "has_arms"

MOVEMENTS = {
    "step_forward": {"name": "Step Forward", "type": LEGS_ONLY},
    "walk_forward": {"name": "Walk Forward", "type": LEGS_ONLY},
    "step_backward": {"name": "Step Backward", "type": LEGS_ONLY},
    "walk_backward": {"name": "Walk Backward", "type": LEGS_ONLY},
    "turn_right": {"name": "Turn Right", "type": LEGS_ONLY},
    "turn_right_slow": {"name": "Turn Right Slow", "type": LEGS_ONLY},
    "turn_left": {"name": "Turn Left", "type": LEGS_ONLY},
    "turn_left_slow": {"name": "Turn Left Slow", "type": LEGS_ONLY},
    "pose": {"name": "Pose", "type": LEGS_ONLY},
    "bow": {"name": "Bow", "type": LEGS_ONLY},
    "tilt_right": {"name": "Tilt Right", "type": LEGS_ONLY},
    "tilt_left": {"name": "Tilt Left", "type": LEGS_ONLY},
    "side_side": {"name": "Side Side", "type": LEGS_ONLY},
    "wave_right": {"name": "Wave Right", "type": LEGS_ONLY},
    "wave_left": {"name": "Wave Left", "type": LEGS_ONLY},
    "neutral_legs": {"name": "Neutral Legs", "type": LEGS_ONLY},
    "excited": {"name": "Excited", "type": LEGS_ONLY},
    "laugh": {"name": "Laugh", "type": LEGS_ONLY},
    "swing_legs": {"name": "Swing Legs", "type": LEGS_ONLY},
    "right_hi": {"name": "Right Hi", "type": HAS_ARMS},
    "left_hi": {"name": "Left Hi", "type": HAS_ARMS},
    "pezz_dispenser": {"name": "Pezz Dispenser", "type": HAS_ARMS},
    "monster": {"name": "Monster", "type": HAS_ARMS},
}

def get_all():
    return MOVEMENTS

def get_by_type(movement_type):
    return {k: v for k, v in MOVEMENTS.items() if v["type"] == movement_type}

def get_legs_only():
    return get_by_type(LEGS_ONLY)

def get_has_arms():
    return get_by_type(HAS_ARMS)

def get_names():
    return [(v["name"], k) for k, v in MOVEMENTS.items()]

def get_names_by_type(movement_type):
    return [(v["name"], k) for k, v in MOVEMENTS.items() if v["type"] == movement_type]