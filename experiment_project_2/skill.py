# skill.py
class Skill:
    def __init__(self, name, damage_multiplier, is_aoe=False, is_combo=False):
        self.name = name
        self.multiplier = damage_multiplier
        self.is_aoe = is_aoe
        self.is_combo = is_combo