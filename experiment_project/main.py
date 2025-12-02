# main.py
from product import Product
from cart import Cart
from promotion import PromotionEngine

def run_simulation():
    # 1. 初始化商品库
    p1 = Product("001", "机械键盘", 200.0, "Electronics")
    p2 = Product("002", "游戏鼠标", 100.0, "Electronics")
    p3 = Product("003", "鼠标垫", 50.0, "Accessories")
    
    print("--- 初始化商品价格 ---")
    print(f"{p1.name}: {p1.price}") # 200
    print(f"{p2.name}: {p2.price}") # 100
    print("-" * 20)

    engine = PromotionEngine()

    # 场景 A: 用户想看看“全场8折”后是多少钱
    cart_a = Cart()
    cart_a.add_item(p1, 1) # 200
    cart_a.add_item(p2, 1) # 100
    
    print("\n[场景 A] 试算：全场8折 (预期: 300 * 0.8 = 240)")
    total_a = engine.apply_percentage_discount(cart_a.get_items(), 0.2)
    print(f"试算结果: {total_a}") 
    # 输出 240 (看似正确，但埋下了雷)

    # 场景 B: 用户决定不打折了，改用“满3送1”策略下单
    # 此时用户买了 3 个鼠标
    cart_b = Cart()
    cart_b.add_item(p2, 3) # 预期: 100 * 3 = 300. 买3送1 -> 减去一个100 -> 最终 200。
    
    print("\n[场景 B] 正式下单：3个鼠标 (买3送1)")
    # BUG 触发：由于场景A修改了引用，p2 的价格现在变成了 80！
    # 预期计算基数是 100，实际是 80。
    # 另外 B3G1 逻辑也有问题，但在 3 个的情况下可能看不出来，需要更多数据。
    total_b = engine.apply_b3g1_free(cart_b.get_items())
    
    print(f"下单结果: {total_b}")
    print(f"预期结果: 200.0")
    
    # 检查当前商品库价格（给被试的提示）
    print("\n--- 检查商品库当前价格 ---")
    print(f"{p2.name}: {p2.price}") 
    # 如果被试细心，会发现鼠标变成了 80 块，这是不合理的

if __name__ == "__main__":
    run_simulation()