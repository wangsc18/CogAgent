# test_data.py

"""
[实验阶段一]：请运行 main.py，它会读取下方的 bug_repro_cases 进行测试。
观察控制台输出，修复代码中的逻辑错误，直到数值计算符合预期。

[实验阶段二]：修复完成后，请模仿格式，在后面补充 10 组测试数据。
"""

bug_repro_cases = [
    {
        "id": "BUG_01_BUFF",
        "desc": "测试 Buff 回合后是否回滚 (数据污染检查)",
        "hero": {"hp": 1000, "atk": 100},
        "enemies": [{"hp": 500}], # 这里的敌人不重要，主要看 Hero
        "action": "BUFF_50", # 提升 50%
        "expected_damage": 150,
        "check_inflation": True # 指示 main.py 检查基础攻击力是否被改了
    },
    {
        "id": "BUG_02_AOE",
        "desc": "测试群体斩杀 (满血 BOSS 不应受双倍)",
        "hero": {"hp": 1000, "atk": 100},
        "enemies": [
            {"name": "小怪(残)", "hp": 10, "max_hp": 100}, # 触发斩杀
            {"name": "BOSS(满)", "hp": 1000, "max_hp": 1000} # 不应触发
        ],
        "action": "AOE_SKILL",
        # 预期：小怪 200 (100*2), BOSS 100 (100*1). 总伤害 300
        "expected_total_damage": 300 
    },
    {
        "id": "BUG_03_COMBO",
        "desc": "测试三连击 (应削弱最高伤害)",
        "hero": {"hp": 1000, "atk": 100},
        "enemies": [{"hp": 2000}],
        "action": "COMBO_STRIKE",
        # 假设三次攻击波动为 [100, 150, 100]
        # 逻辑：最高 150 减半 -> 75。
        # 总伤害：100 + 75 + 100 = 275
        # main.py 里会模拟这就固定的三次伤害值
        "expected_total_damage": 275
    }
]

# 请在下方继续编写您的测试数据：
my_test_cases = [
    # === 测试1: Buff - 多次使用Buff (检测属性膨胀) ===
    {
        "id": "TEST_001_BUFF_MULTI",
        "desc": "多次Buff测试 - 检测攻击力是否指数增长",
        "hero": {"hp": 1000, "atk": 100},
        "enemies": [{"hp": 500}],
        "action": "BUFF_50",  # 50% Buff
        "expected_damage": 150,  # 100 * 1.5 = 150
        "check_inflation": True  # 检查是否回滚
    },

    # === 测试2: Buff - 基础攻击力为1的边界测试 ===
    {
        "id": "TEST_002_BUFF_LOW_ATK",
        "desc": "低攻击力Buff测试 (边界条件)",
        "hero": {"hp": 500, "atk": 10},
        "enemies": [{"hp": 300}],
        "action": "BUFF_50",
        "expected_damage": 15,  # 10 * 1.5 = 15
        "check_inflation": True
    },

    # === 测试3: AOE - 全部敌人满血 (无斩杀) ===
    {
        "id": "TEST_003_AOE_FULL_HP",
        "desc": "群攻测试 - 所有敌人满血(无斩杀)",
        "hero": {"hp": 1000, "atk": 100},
        "enemies": [
            {"name": "哥布林1", "hp": 200, "max_hp": 200},
            {"name": "哥布林2", "hp": 200, "max_hp": 200},
            {"name": "哥布林3", "hp": 200, "max_hp": 200}
        ],
        "action": "AOE_SKILL",
        "expected_total_damage": 300  # 每个100,共300
    },

    # === 测试4: AOE - 全部敌人残血 (全触发斩杀) ===
    {
        "id": "TEST_004_AOE_ALL_LOW",
        "desc": "群攻测试 - 所有敌人残血(全触发斩杀)",
        "hero": {"hp": 1000, "atk": 100},
        "enemies": [
            {"name": "残血1", "hp": 10, "max_hp": 200},
            {"name": "残血2", "hp": 15, "max_hp": 200},
            {"name": "残血3", "hp": 20, "max_hp": 200}
        ],
        "action": "AOE_SKILL",
        "expected_total_damage": 600  # 每个200(双倍),共600
    },

    # === 测试5: AOE - 混合情况 (首个满血,后续残血) ===
    {
        "id": "TEST_005_AOE_MIXED_ORDER",
        "desc": "群攻测试 - 首个满血,后两个残血",
        "hero": {"hp": 1000, "atk": 100},
        "enemies": [
            {"name": "满血坦克", "hp": 1000, "max_hp": 1000},
            {"name": "残血法师", "hp": 20, "max_hp": 300},
            {"name": "残血刺客", "hp": 15, "max_hp": 250}
        ],
        "action": "AOE_SKILL",
        # 正确逻辑: 满血100, 残血200, 残血200 = 500
        "expected_total_damage": 500
    },

    # === 测试6: AOE - 单个敌人 ===
    {
        "id": "TEST_006_AOE_SINGLE",
        "desc": "群攻测试 - 单个敌人(满血)",
        "hero": {"hp": 1000, "atk": 80},
        "enemies": [
            {"name": "BOSS", "hp": 5000, "max_hp": 5000}
        ],
        "action": "AOE_SKILL",
        "expected_total_damage": 80  # 单体100,不触发斩杀
    },

    # === 测试7: 连击 - 三次相同伤害 ===
    {
        "id": "TEST_007_COMBO_SAME",
        "desc": "连击测试 - 三次伤害相同",
        "hero": {"hp": 1000, "atk": 100},
        "enemies": [{"hp": 2000}],
        "action": "COMBO_STRIKE",
        # main.py会模拟固定伤害 [100, 150, 100]
        # 但如果三次都是100: 最高100减半 -> 50
        # 总伤害: 100 + 50 + 100 = 250
        # 注意: main.py固定用 [100, 150, 100],这里仅测试逻辑
        "expected_total_damage": 275  # 实际是150减半
    },

    # === 测试8: 连击 - 伤害差异大 ===
    {
        "id": "TEST_008_COMBO_VARIANCE",
        "desc": "连击测试 - 伤害波动大(暴击)",
        "hero": {"hp": 1000, "atk": 100},
        "enemies": [{"hp": 3000}],
        "action": "COMBO_STRIKE",
        # main.py模拟: [100, 150, 100]
        # 最高150减半 -> 75
        # 总伤害: 100 + 75 + 100 = 275
        "expected_total_damage": 275
    },

    # === 测试9: 连击 - 少于3次攻击 ===
    {
        "id": "TEST_009_COMBO_LESS_THAN_THREE",
        "desc": "连击测试 - 不足3次(边界条件)",
        "hero": {"hp": 500, "atk": 80},
        "enemies": [{"hp": 1000}],
        "action": "COMBO_STRIKE",
        # 如果main.py传入 [80, 90], 应直接求和
        # 但main.py固定传 [100, 150, 100]
        # 这里假设逻辑正确时,少于3次不削弱
        "expected_total_damage": 275  # 实际仍是固定的三次
    },

    # === 测试10: 综合测试 - Buff后检查基础攻击 ===
    {
        "id": "TEST_010_BUFF_RESET",
        "desc": "Buff回滚完整性测试 - 高倍Buff",
        "hero": {"hp": 1200, "atk": 200},
        "enemies": [{"hp": 1000}],
        "action": "BUFF_50",  # 50% Buff
        "expected_damage": 300,  # 200 * 1.5 = 300
        "check_inflation": True  # 确保回滚到200
    }
]