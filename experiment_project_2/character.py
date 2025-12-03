# character.py
class Character:
    def __init__(self, name, hp, attack, defense):
        self.name = name
        self.hp = hp
        self.attack = attack # Base Attack
        self.defense = defense

    def __repr__(self):
        return f"[{self.name} HP:{self.hp} ATK:{self.attack}]"