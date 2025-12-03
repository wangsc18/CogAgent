# promotion.py
from typing import List
from product import Product

class PromotionEngine:
    
    def apply_flat_discount(self, items: List[Product], threshold: float, discount_amount: float) -> float:
        """
        [逻辑 Bug]: 满减计算逻辑顺序错误
        预期：如果总价 > 100，减 10 块。
        现状：代码逻辑写成了先计算折扣，再判断是否满足原来的阈值？
        或者更隐蔽的：它只对'category'符合某种条件的生效，但代码里漏了逻辑。
        
        设定 Bug: 计算总价时，错误的把 discount_amount 当作了倍率。
        """
        current_total = sum(item.price for item in items)
        if current_total >= threshold:
            # BUG: 这里应该减去 discount_amount，但写成了乘法或者逻辑判断位置不对
            # 这里我们做一个隐蔽的逻辑错：满100减10，
            # 但它在循环里对每个商品判断了阈值（逻辑完全错误），导致大额商品被多次减免
            discounted_total = 0
            for item in items:
                if item.price > threshold: # 居然是单品判断
                    discounted_total += (item.price - discount_amount)
                else:
                    discounted_total += item.price
            return discounted_total
        return current_total

    def apply_percentage_discount(self, items: List[Product], percent_off: float) -> float:
        """
        [状态 Bug - 引用陷阱]: 致命的 Reference Bug
        预期：计算打折后的总价，不改变原价。
        现状：直接修改了 item.price，导致后续计算（或第二次结账）基数变小。
        """
        total = 0
        for item in items:
            # BUG: 直接修改了对象属性！因为 Python 是引用传递
            # 这会污染全局的 Product 对象
            item.price = item.price * (1 - percent_off) 
            total += item.price
        return total

    def apply_b3g1_free(self, items: List[Product]) -> float:
        """
        [算法 Bug]: 买3送1 (Buy 3 Get 1 Free)
        预期：每买3个商品，其中最便宜的那个免费。买6个应该免2个。
        现状：贪心算法写错了。
        """
        if len(items) < 3:
            return sum(item.price for item in items)
        
        # 按价格排序（低到高）
        sorted_items = sorted(items, key=lambda x: x.price)
        
        # BUG: 它只减去了列表里的第一个（最便宜的），无论买多少个
        # 如果买了 6 个，应该免去 sorted_items[0] 和 sorted_items[1]
        # 但这里只减了一次
        discount_amount = sorted_items[0].price
        
        total = sum(item.price for item in items)
        return total - discount_amount