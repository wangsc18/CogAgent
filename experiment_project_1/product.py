# product.py
class Product:
    def __init__(self, pid: str, name: str, price: float, category: str):
        self.pid = pid
        self.name = name
        self.price = price
        self.category = category

    def __repr__(self):
        return f"<{self.name}: ${self.price:.2f}>"