# test_data.py

"""
[实验阶段一]：请运行 main.py，它会读取下方的 initial_scenarios 进行测试。
观察控制台输出，修复代码中的逻辑错误，直到 Actual 等于 Expected。

[实验阶段二]：修复完成后，请模仿格式，在后面补充 10 组测试数据。
"""

# 预置的 Bug 复现场景
initial_scenarios = [
    {
        "id": "CASE_001_REF",
        "desc": "测试全场8折 (检查原价是否被污染)",
        "items": [
            {"name": "机械键盘", "price": 200.0},
            {"name": "游戏鼠标", "price": 100.0}
        ],
        "strategy": "PERCENT_20", # 8折
        "expected_total": 240.0 
        # Bug 预期：运行后，main.py 会检查商品原价是否被修改
    },
    {
        "id": "CASE_002_FLAT",
        "desc": "测试满100减10 (多个高价商品)",
        "items": [
            {"name": "A", "price": 150.0},
            {"name": "B", "price": 150.0}
        ],
        "strategy": "FLAT_10", # 满100减10
        "expected_total": 290.0 # 300 - 10
        # Bug 现状：代码可能对每个商品都减了10，导致结果为 280
    },
    {
        "id": "CASE_003_ALGO",
        "desc": "测试买3送1 (买6件)",
        "items": [
            {"name": "鼠标", "price": 100.0},
            {"name": "鼠标", "price": 100.0},
            {"name": "鼠标", "price": 100.0},
            {"name": "鼠标", "price": 100.0},
            {"name": "鼠标", "price": 100.0},
            {"name": "鼠标", "price": 100.0}
        ],
        "strategy": "B3G1", # 买3送1
        "expected_total": 400.0 # 买6送2，应付4个
        # Bug 现状：贪心算法只减了1个，结果为 500
    }
]

# 请在下方继续编写您的测试数据：
new_scenarios = [
    
]