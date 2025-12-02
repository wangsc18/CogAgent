# cart.py
from typing import List
from product import Product

class Cart:
    def __init__(self):
        self.items: List[Product] = []

    def add_item(self, product: Product, quantity: int = 1):
        for _ in range(quantity):
            self.items.append(product)

    def get_items(self) -> List[Product]:
        return self.items

    def get_raw_subtotal(self) -> float:
        """计算不含优惠的基础总价"""
        return sum(item.price for item in self.items)