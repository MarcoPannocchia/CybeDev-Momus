class OutOfStock(Exception):
    pass


class Inventory:
    def __init__(self, low_stock_limit=5):
        self._items = {}
        self.low_stock_limit = low_stock_limit

    def add(self, name, quantity, unit_price):
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        current = self._items.get(name)
        if current is None:
            self._items[name] = {"quantity": quantity, "unit_price": unit_price}
        else:
            current["quantity"] += quantity
            current["unit_price"] = unit_price

    def remove(self, name, quantity):
        current = self._items.get(name)
        if current is None or current["quantity"] < quantity:
            raise OutOfStock(name)
        current["quantity"] -= quantity
        if current["quantity"] == 0:
            del self._items[name]

    def total_value(self):
        return sum(item["quantity"] * item["unit_price"] for item in self._items.values())

    def low_stock(self):
        return sorted(
            name
            for name, item in self._items.items()
            if item["quantity"] <= self.low_stock_limit
        )

    @property
    def names(self):
        return sorted(self._items)

    @staticmethod
    def format_price(amount):
        return f"{amount:,.2f}"
