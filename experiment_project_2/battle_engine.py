# battle_engine.py
from typing import List
from character import Character
from skill import Skill

class BattleEngine:
    
    def apply_buff(self, hero: Character, buff_factor: float):
        """
        [Bug 1: 引用修改陷阱]
        预期：计算临时的攻击力用于本回合。
        现状：直接修改了 hero.attack，导致下一回合攻击力暴涨。
        """
        # BUG: 直接修改了对象属性！
        hero.attack = hero.attack * buff_factor
        return hero.attack

    def calculate_aoe_damage(self, hero: Character, enemies: List[Character], base_dmg: float) -> List[int]:
        """
        [Bug 2: 循环逻辑范围错误]
        预期：对每个敌人单独判断斩杀（HP < 30%）。
        现状：逻辑写反了，或者标志位放错了位置。
        """
        damages = []
        is_execute = False # 致命错误：标志位放在了循环外
        
        for enemy in enemies:
            # BUG: 如果第一个敌人触发了斩杀，is_execute 变成 True
            # 后面的敌人无论血量多少，都会吃到双倍伤害
            if enemy.hp < (enemy.hp * 0.3) + 50: # 模拟个简单的阈值逻辑 
                is_execute = True
            
            final_dmg = base_dmg * 2 if is_execute else base_dmg
            damages.append(int(final_dmg))
            
        return damages

    def calculate_combo_damage(self, hero: Character, hits: List[int]) -> int:
        """
        [Bug 3: 贪心算法错误]
        预期：三连击中，伤害最高的 1 次减半。
        现状：排序逻辑或切片逻辑错误。
        hits: [100, 150, 100] -> 应该是 150 减半
        """
        if len(hits) < 3:
            return sum(hits)
        
        # 按伤害从低到高排序
        sorted_hits = sorted(hits)
        
        # BUG: 这里本意是减去最高伤害的一半
        # 但 sorted_hits[0] 是最低伤害！
        # 导致玩家不仅没被削弱，反而只减了一点点伤害
        penalty = sorted_hits[0] * 0.5 
        
        total = sum(hits) - penalty
        return int(total)