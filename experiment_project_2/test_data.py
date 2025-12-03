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
    
]