#!/usr/bin/env bash
# Creates a small git repository with one Python module and one test.
set -euo pipefail
mkdir -p src tests
cat > src/price.py <<'PY'
def calculate_total(prices: list[float], discount: float = 0.0) -> float:
    """Return the sum of prices minus a relative discount between 0 and 1."""
    subtotal = sum(prices)
    return round(subtotal * (1 - discount), 2)
PY
cat > tests/test_price.py <<'PY'
import unittest

from src.price import calculate_total


class CalculateTotalTest(unittest.TestCase):
    def test_discount(self) -> None:
        self.assertEqual(calculate_total([10.0, 5.0], 0.1), 13.5)


if __name__ == "__main__":
    unittest.main()
PY
touch src/__init__.py tests/__init__.py
git -c init.defaultBranch=main init -q
git add .
git -c user.name=eval -c user.email=eval@example.invalid commit -q -m "initial commit"
printf '/.lockin/\n' >> .git/info/exclude
git checkout -q -b feature
cat > src/price.py <<'PY'
def calculate_total(prices: list[float], discount: float = 0.0) -> float:
    """Return the sum of prices minus a relative discount between 0 and 1."""
    if not 0 <= discount <= 1:
        raise ValueError("discount must be between 0 and 1")
    subtotal = sum(prices)
    return round(subtotal * (1 - discount), 2)
PY
cat >> tests/test_price.py <<'PY'


class DiscountRangeTest(unittest.TestCase):
    def test_rejects_discount_above_one(self) -> None:
        with self.assertRaises(ValueError):
            calculate_total([1.0], 1.5)
PY
git add .
git -c user.name=eval -c user.email=eval@example.invalid commit -q -m "Reject discounts outside 0 to 1"
