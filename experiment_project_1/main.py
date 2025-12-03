# main.py
from product import Product
from cart import Cart
from promotion import PromotionEngine
from test_data import initial_scenarios, new_scenarios

def run_test_case(scenario):
    print(f"\n>>> 正在运行测试: {scenario['desc']} [{scenario['id']}]")
    
    # 1. 准备数据
    engine = PromotionEngine()
    cart = Cart()
    
    # 保留对 Product 对象的引用，以便后续检查是否被污染
    product_refs = []
    for item_data in scenario['items']:
        p = Product("00x", item_data['name'], item_data['price'], "General")
        cart.add_item(p)
        product_refs.append(p)
        
    # 2. 执行策略
    strategy = scenario['strategy']
    if strategy == "PERCENT_20":
        actual = engine.apply_percentage_discount(cart.get_items(), 0.2)
    elif strategy == "FLAT_10":
        actual = engine.apply_flat_discount(cart.get_items(), 100, 10)
    elif strategy == "B3G1":
        actual = engine.apply_b3g1_free(cart.get_items())
    else:
        actual = cart.get_raw_subtotal()

    # 3. 结果验证
    expected = scenario['expected_total']
    
    if abs(actual - expected) < 0.01:
        print(f"✅ 金额正确: {actual}")
    else:
        print(f"❌ 金额错误! 预期: {expected}, 实际: {actual}")

    # 4. [关键] 检查数据污染 (针对 Bug 1)
    # 检查内存中的对象价格是否被修改了
    is_corrupted = False
    for i, p in enumerate(product_refs):
        original_price = scenario['items'][i]['price']
        if abs(p.price - original_price) > 0.01:
            print(f"⚠️ [严重警告] 商品原价被篡改! {p.name}: {original_price} -> {p.price}")
            is_corrupted = True
            
    if is_corrupted:
        print("   -> 这会导致后续订单计算错误 (引用传递 Bug)")

if __name__ == "__main__":
    print("=== 开始第一阶段：修复 Bug (运行预置用例) ===")
    for case in initial_scenarios:
        run_test_case(case)
        
    print("\n" + "="*40)
    print("=== 开始第二阶段：验证新数据 (运行您的用例) ===")
    if not new_scenarios:
        print("(暂无新数据，请在 test_data.py 中编写)")
    else:
        for case in new_scenarios:
            run_test_case(case)