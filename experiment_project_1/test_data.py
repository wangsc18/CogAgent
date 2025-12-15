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
    # === 测试1: 百分比折扣 - 多次使用同一商品对象 (检测引用污染) ===
    {
        "id": "TEST_001_REF_MULTI",
        "desc": "同一商品多次加入购物车后打折 (引用污染检测)",
        "items": [
            {"name": "咖啡杯", "price": 50.0},
            {"name": "咖啡杯", "price": 50.0},
            {"name": "咖啡杯", "price": 50.0}
        ],
        "strategy": "PERCENT_20",  # 8折
        "expected_total": 120.0  # 150 * 0.8 = 120
    },

    # === 测试2: 满减 - 边界条件 (刚好达到阈值) ===
    {
        "id": "TEST_002_FLAT_EDGE",
        "desc": "满减边界测试 - 总价恰好100元",
        "items": [
            {"name": "书", "price": 50.0},
            {"name": "笔", "price": 50.0}
        ],
        "strategy": "FLAT_10",  # 满100减10
        "expected_total": 90.0  # 100 - 10 = 90
    },

    # === 测试3: 满减 - 未达阈值 ===
    {
        "id": "TEST_003_FLAT_BELOW",
        "desc": "满减测试 - 总价未达100元",
        "items": [
            {"name": "橡皮", "price": 30.0},
            {"name": "尺子", "price": 20.0}
        ],
        "strategy": "FLAT_10",
        "expected_total": 50.0  # 未满100,不减
    },

    # === 测试4: 满减 - 多个高价商品超过阈值 ===
    {
        "id": "TEST_004_FLAT_HIGH",
        "desc": "满减测试 - 多个高价商品(单价均>100)",
        "items": [
            {"name": "显卡", "price": 3000.0},
            {"name": "CPU", "price": 2000.0}
        ],
        "strategy": "FLAT_10",
        "expected_total": 4990.0  # 5000 - 10 = 4990 (应该只减一次)
    },

    # === 测试5: 买3送1 - 刚好3件 ===
    {
        "id": "TEST_005_B3G1_MIN",
        "desc": "买3送1 - 最少件数(3件)",
        "items": [
            {"name": "T恤", "price": 100.0},
            {"name": "T恤", "price": 100.0},
            {"name": "T恤", "price": 100.0}
        ],
        "strategy": "B3G1",
        "expected_total": 200.0  # 买3送1,付2件
    },

    # === 测试6: 买3送1 - 不同价格商品 ===
    {
        "id": "TEST_006_B3G1_MIXED",
        "desc": "买3送1 - 不同价格(应免最便宜的)",
        "items": [
            {"name": "高级键盘", "price": 300.0},
            {"name": "普通鼠标", "price": 80.0},
            {"name": "鼠标垫", "price": 20.0}
        ],
        "strategy": "B3G1",
        "expected_total": 380.0  # 400 - 20(最便宜) = 380
    },

    # === 测试7: 买3送1 - 买9件 (测试多次免单) ===
    {
        "id": "TEST_007_B3G1_NINE",
        "desc": "买3送1 - 买9件(应送3件)",
        "items": [
            {"name": "水杯", "price": 50.0},
            {"name": "水杯", "price": 50.0},
            {"name": "水杯", "price": 50.0},
            {"name": "水杯", "price": 50.0},
            {"name": "水杯", "price": 50.0},
            {"name": "水杯", "price": 50.0},
            {"name": "水杯", "price": 50.0},
            {"name": "水杯", "price": 50.0},
            {"name": "水杯", "price": 50.0}
        ],
        "strategy": "B3G1",
        "expected_total": 300.0  # 买9送3,付6件 = 300
    },

    # === 测试8: 买3送1 - 买7件 (不满第三轮) ===
    {
        "id": "TEST_008_B3G1_SEVEN",
        "desc": "买3送1 - 买7件(送2件,剩1件原价)",
        "items": [
            {"name": "袜子", "price": 10.0},
            {"name": "袜子", "price": 10.0},
            {"name": "袜子", "price": 10.0},
            {"name": "袜子", "price": 10.0},
            {"name": "袜子", "price": 10.0},
            {"name": "袜子", "price": 10.0},
            {"name": "袜子", "price": 10.0}
        ],
        "strategy": "B3G1",
        "expected_total": 50.0  # 买7送2,付5件 = 50
    },

    # === 测试9: 无折扣 - 原价结算 ===
    {
        "id": "TEST_009_NO_PROMO",
        "desc": "无促销活动 - 原价结算",
        "items": [
            {"name": "矿泉水", "price": 3.0},
            {"name": "面包", "price": 5.0}
        ],
        "strategy": "NONE",
        "expected_total": 8.0
    },

    # === 测试10: 百分比折扣 - 高价商品精度测试 ===
    {
        "id": "TEST_010_PERCENT_PRECISION",
        "desc": "百分比折扣 - 测试浮点精度(高价商品)",
        "items": [
            {"name": "笔记本电脑", "price": 6999.99},
            {"name": "鼠标", "price": 199.99}
        ],
        "strategy": "PERCENT_20",
        "expected_total": 5759.98  # 7199.98 * 0.8 = 5759.984 ≈ 5759.98
    }
]