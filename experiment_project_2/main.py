# main.py
from character import Character
from battle_engine import BattleEngine
from test_data import bug_repro_cases, my_test_cases

def run_simulation(case):
    print(f"\n>>> ⚔️ 战斗模拟: {case['desc']} [{case['id']}]")
    
    engine = BattleEngine()
    
    # 1. 初始化角色
    hero_data = case['hero']
    hero = Character("勇者", hero_data['hp'], hero_data['atk'], 10)
    
    enemies = []
    for i, e_data in enumerate(case['enemies']):
        name = e_data.get('name', f"敌人{i}")
        max_hp = e_data.get('max_hp', e_data['hp'])
        enemy = Character(name, e_data['hp'], 50, 0)
        # 简易 hack: 强行设置 max_hp 用于百分比计算
        enemy.max_hp = max_hp 
        enemies.append(enemy)

    # 2. 执行行动
    action = case['action']
    actual_dmg = 0
    
    if action == "BUFF_50":
        actual_dmg = engine.apply_buff(hero, 1.5)
        print(f"   [Buff生效] 当前回合攻击力: {actual_dmg}")
        
    elif action == "AOE_SKILL":
        damages = engine.calculate_aoe_damage(hero, enemies, hero.attack)
        actual_dmg = sum(damages)
        print(f"   [AOE伤害] 对各目标造成: {damages}")
        
    elif action == "COMBO_STRIKE":
        # 模拟固定的三次判定，方便测试算法逻辑
        # 假设基础伤害 100, 暴击 150, 普通 100
        raw_hits = [100, 150, 100] 
        print(f"   [连击原始值] {raw_hits}")
        actual_dmg = engine.calculate_combo_damage(hero, raw_hits)

    # 3. 结果验证
    if 'expected_damage' in case:
        expected = case['expected_damage']
    else:
        expected = case['expected_total_damage']

    if actual_dmg == expected:
        print(f"✅ 伤害数值正确: {actual_dmg}")
    else:
        print(f"❌ 伤害数值错误! 预期: {expected}, 实际: {actual_dmg}")

    # 4. [关键] 检查属性膨胀 (针对 Bug 1)
    if case.get('check_inflation'):
        print(f"   --- 回合结束，检查属性回滚 ---")
        if hero.attack != hero_data['atk']:
            print(f"⚠️ [严重警告] 角色基础攻击力被永久修改! {hero_data['atk']} -> {hero.attack}")
            print("   -> 这是一个严重的引用传递 Bug，Buff 效果未消失")
        else:
            print("✅ 角色属性已正确回滚")

if __name__ == "__main__":
    print("=== 🛡️ 阶段一：修复战斗核心 Bug ===")
    for case in bug_repro_cases:
        run_simulation(case)
        
    print("\n" + "="*40)
    print("=== ⚔️ 阶段二：验证数值平衡 (用户测试数据) ===")
    if not my_test_cases:
        print("(暂无新数据，请在 test_scenarios.py 中编写)")
    else:
        for case in my_test_cases:
            run_simulation(case)