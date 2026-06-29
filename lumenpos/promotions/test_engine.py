"""Standalone tests for the promotion engine (no Frappe needed).

Run directly:  python -m unittest lumenpos.promotions.test_engine
"""

import unittest
from datetime import datetime

from lumenpos.promotions.engine import evaluate

NOW = datetime(2026, 6, 10, 14, 0, 0)  # a Wednesday afternoon


def cart(*items, customer_group=None, pos_profile="Main Store"):
    return {
        "customer_group": customer_group,
        "pos_profile": pos_profile,
        "items": list(items),
    }


def line(item_code, price, qty=1, item_group="Products", brand=None):
    return {
        "item_code": item_code,
        "item_group": item_group,
        "brand": brand,
        "qty": qty,
        "price": price,
    }


def promo(**kwargs):
    base = {
        "name": "PROMO-TEST",
        "title": kwargs.get("title", "Test Promo"),
        "promotion_type": "Simple Discount",
        "priority": 1,
        "stackable": 0,
        "days": {},
        "pos_profiles": [],
        "customer_eligibility": "All Customers",
        "customer_groups": [],
        "apply_on_all": 0,
        "items": [],
        "max_applications": 0,
    }
    base.update(kwargs)
    return base


class TestSimpleDiscount(unittest.TestCase):
    def test_percentage_off_item(self):
        p = promo(
            items=[{"applies_to": "Item", "value": "COLA", "role": "Buy"}],
            discount_type="Percentage",
            discount_value=10,
        )
        r = evaluate(cart(line("COLA", 2.0, qty=3), line("CHIPS", 1.5)), [p], NOW)
        self.assertAlmostEqual(r["line_discounts"][0], 0.6)
        self.assertAlmostEqual(r["line_discounts"][1], 0.0)
        self.assertAlmostEqual(r["total_savings"], 0.6)

    def test_fixed_price(self):
        p = promo(
            items=[{"applies_to": "Item", "value": "COLA", "role": "Buy"}],
            discount_type="Fixed Price",
            discount_value=1.5,
        )
        r = evaluate(cart(line("COLA", 2.0, qty=2)), [p], NOW)
        self.assertAlmostEqual(r["line_discounts"][0], 1.0)

    def test_fixed_price_above_price_gives_nothing(self):
        p = promo(
            items=[{"applies_to": "Item", "value": "COLA", "role": "Buy"}],
            discount_type="Fixed Price",
            discount_value=5.0,
        )
        r = evaluate(cart(line("COLA", 2.0)), [p], NOW)
        self.assertEqual(r["applied"], [])

    def test_item_group_match(self):
        p = promo(
            items=[{"applies_to": "Item Group", "value": "Drinks", "role": "Buy"}],
            discount_type="Amount",
            discount_value=0.5,
        )
        r = evaluate(
            cart(line("COLA", 2.0, item_group="Drinks"), line("CHIPS", 1.5)), [p], NOW
        )
        self.assertAlmostEqual(r["line_discounts"][0], 0.5)
        self.assertAlmostEqual(r["line_discounts"][1], 0.0)


class TestBuyXGetY(unittest.TestCase):
    def test_buy_two_get_one_free_shared_pool(self):
        # Classic multibuy: needs 3 units in the cart, cheapest is free.
        p = promo(
            promotion_type="Buy X Get Y",
            items=[{"applies_to": "Item Group", "value": "Drinks", "role": "Buy"}],
            buy_qty=2,
            get_qty=1,
            get_discount_type="Free",
        )
        c = cart(
            line("COLA", 2.0, qty=2, item_group="Drinks"),
            line("JUICE", 3.0, qty=1, item_group="Drinks"),
        )
        r = evaluate(c, [p], NOW)
        # 3 units -> 1 application -> cheapest unit (COLA at 2.0) free
        self.assertAlmostEqual(r["total_savings"], 2.0)
        self.assertAlmostEqual(r["line_discounts"][0], 2.0)

    def test_not_enough_units(self):
        p = promo(
            promotion_type="Buy X Get Y",
            items=[{"applies_to": "Item", "value": "COLA", "role": "Buy"}],
            buy_qty=2,
            get_qty=1,
            get_discount_type="Free",
        )
        r = evaluate(cart(line("COLA", 2.0, qty=2)), [p], NOW)
        self.assertEqual(r["applied"], [])

    def test_repeats_and_max_applications(self):
        p = promo(
            promotion_type="Buy X Get Y",
            items=[{"applies_to": "Item", "value": "COLA", "role": "Buy"}],
            buy_qty=2,
            get_qty=1,
            get_discount_type="Free",
        )
        r = evaluate(cart(line("COLA", 2.0, qty=6)), [p], NOW)
        self.assertAlmostEqual(r["total_savings"], 4.0)  # 2 applications

        p2 = dict(p, max_applications=1)
        r2 = evaluate(cart(line("COLA", 2.0, qty=6)), [p2], NOW)
        self.assertAlmostEqual(r2["total_savings"], 2.0)

    def test_same_item_in_buy_and_get(self):
        # Same product on both sides: one unit cannot be trigger AND reward
        p = promo(
            promotion_type="Buy X Get Y",
            items=[
                {"applies_to": "Item", "value": "COLA", "role": "Buy"},
                {"applies_to": "Item", "value": "COLA", "role": "Get"},
            ],
            buy_qty=1,
            get_qty=1,
            get_discount_type="Percentage",
            get_discount_value=50,
        )
        # 1 unit -> nothing
        self.assertEqual(evaluate(cart(line("COLA", 10, qty=1)), [p], NOW)["applied"], [])
        # 2 units -> second at 50%
        self.assertAlmostEqual(
            evaluate(cart(line("COLA", 10, qty=2)), [p], NOW)["total_savings"], 5.0
        )
        # 4 units -> two at 50%
        self.assertAlmostEqual(
            evaluate(cart(line("COLA", 10, qty=4)), [p], NOW)["total_savings"], 10.0
        )

    def test_separate_get_pool(self):
        # Buy a SHIRT, get a TIE half price.
        p = promo(
            promotion_type="Buy X Get Y",
            items=[
                {"applies_to": "Item", "value": "SHIRT", "role": "Buy"},
                {"applies_to": "Item", "value": "TIE", "role": "Get"},
            ],
            buy_qty=1,
            get_qty=1,
            get_discount_type="Percentage",
            get_discount_value=50,
        )
        r = evaluate(cart(line("SHIRT", 40.0), line("TIE", 10.0)), [p], NOW)
        self.assertAlmostEqual(r["line_discounts"][1], 5.0)
        self.assertAlmostEqual(r["total_savings"], 5.0)


class TestSpendAndSave(unittest.TestCase):
    def test_threshold_met(self):
        p = promo(
            promotion_type="Spend and Save",
            apply_on_all=1,
            min_spend=100,
            basket_discount_type="Percentage",
            basket_discount_value=10,
        )
        r = evaluate(cart(line("TV", 120.0)), [p], NOW)
        self.assertAlmostEqual(r["basket_discount"], 12.0)

    def test_threshold_not_met(self):
        p = promo(
            promotion_type="Spend and Save",
            apply_on_all=1,
            min_spend=100,
            basket_discount_type="Amount",
            basket_discount_value=15,
        )
        r = evaluate(cart(line("TV", 80.0)), [p], NOW)
        self.assertEqual(r["applied"], [])


class TestBundlePrice(unittest.TestCase):
    BUNDLE = dict(
        promotion_type="Bundle Price",
        items=[
            {"applies_to": "Item", "value": "A", "role": "Buy", "qty": 1},
            {"applies_to": "Item", "value": "B", "role": "Buy", "qty": 1},
            {"applies_to": "Item", "value": "C", "role": "Buy", "qty": 1},
        ],
        bundle_price=300,
    )

    def test_three_for_fixed_price(self):
        p = promo(**self.BUNDLE)
        r = evaluate(cart(line("A", 120), line("B", 120), line("C", 100)), [p], NOW)
        # natural 340 -> bundle 300 -> 40 off, split proportionally
        self.assertAlmostEqual(r["total_savings"], 40.0)
        self.assertAlmostEqual(r["line_discounts"][0], 40 * 120 / 340, places=2)
        self.assertAlmostEqual(r["line_discounts"][2], 40 * 100 / 340, places=2)

    def test_missing_component_no_discount(self):
        p = promo(**self.BUNDLE)
        r = evaluate(cart(line("A", 120), line("B", 120)), [p], NOW)
        self.assertEqual(r["applied"], [])

    def test_bundle_repeats(self):
        p = promo(**self.BUNDLE)
        r = evaluate(
            cart(line("A", 120, qty=2), line("B", 120, qty=2), line("C", 100, qty=2)),
            [p],
            NOW,
        )
        self.assertAlmostEqual(r["total_savings"], 80.0)

    def test_row_qty(self):
        p = promo(
            promotion_type="Bundle Price",
            items=[
                {"applies_to": "Item", "value": "A", "role": "Buy", "qty": 2},
                {"applies_to": "Item", "value": "B", "role": "Buy", "qty": 1},
            ],
            bundle_price=50,
        )
        # 2xA(20) + 1xB(30) = 70 natural -> 50 bundle -> 20 off
        r = evaluate(cart(line("A", 20, qty=2), line("B", 30)), [p], NOW)
        self.assertAlmostEqual(r["total_savings"], 20.0)
        # only one A -> no bundle
        r2 = evaluate(cart(line("A", 20, qty=1), line("B", 30)), [p], NOW)
        self.assertEqual(r2["applied"], [])

    def test_bundle_price_above_natural_gives_nothing(self):
        p = promo(**dict(self.BUNDLE, bundle_price=999))
        r = evaluate(cart(line("A", 120), line("B", 120), line("C", 100)), [p], NOW)
        self.assertEqual(r["applied"], [])


class TestCoupons(unittest.TestCase):
    def test_coupon_gate(self):
        p = promo(
            apply_on_all=1,
            discount_type="Percentage",
            discount_value=10,
            requires_coupon=1,
            coupon_code="SAVE10",
        )
        no_code = evaluate(cart(line("A", 10)), [p], NOW)
        self.assertEqual(no_code["applied"], [])

        with_code = evaluate(
            {**cart(line("A", 10)), "coupon_codes": ["save10"]}, [p], NOW
        )
        self.assertAlmostEqual(with_code["total_savings"], 1.0)


class TestScheduling(unittest.TestCase):
    def test_date_window(self):
        p = promo(
            apply_on_all=1,
            discount_type="Percentage",
            discount_value=10,
            start_date="2026-07-01",
        )
        r = evaluate(cart(line("COLA", 2.0)), [p], NOW)
        self.assertEqual(r["applied"], [])

    def test_weekday(self):
        days = {d: 0 for d in
                ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]}
        days["saturday"] = 1
        p = promo(apply_on_all=1, discount_type="Percentage", discount_value=10, days=days)
        r = evaluate(cart(line("COLA", 2.0)), [p], NOW)  # NOW is a Wednesday
        self.assertEqual(r["applied"], [])

    def test_time_window_wrapping_midnight(self):
        p = promo(
            apply_on_all=1,
            discount_type="Percentage",
            discount_value=10,
            start_time="22:00:00",
            end_time="02:00:00",
        )
        late = datetime(2026, 6, 10, 23, 30)
        midday = datetime(2026, 6, 10, 12, 0)
        self.assertTrue(evaluate(cart(line("A", 1.0)), [p], late)["applied"])
        self.assertFalse(evaluate(cart(line("A", 1.0)), [p], midday)["applied"])

    def test_customer_group(self):
        p = promo(
            apply_on_all=1,
            discount_type="Percentage",
            discount_value=10,
            customer_eligibility="Selected Customer Groups",
            customer_groups=["VIP"],
        )
        self.assertFalse(
            evaluate(cart(line("A", 1.0), customer_group="Retail"), [p], NOW)["applied"]
        )
        self.assertTrue(
            evaluate(cart(line("A", 1.0), customer_group="VIP"), [p], NOW)["applied"]
        )

    def test_pos_profile(self):
        p = promo(
            apply_on_all=1,
            discount_type="Percentage",
            discount_value=10,
            pos_profiles=["Other Store"],
        )
        r = evaluate(cart(line("A", 1.0), pos_profile="Main Store"), [p], NOW)
        self.assertEqual(r["applied"], [])


class TestExclusions(unittest.TestCase):
    def test_all_products_except_brand(self):
        p = promo(
            apply_on_all=1,
            discount_type="Percentage",
            discount_value=10,
            items=[{"applies_to": "Brand", "value": "Apple", "role": "Buy", "exclude": 1}],
        )
        c = cart(line("CABLE", 100, brand="Apple"), line("CHIPS", 50, brand="Lays"))
        r = evaluate(c, [p], NOW)
        self.assertAlmostEqual(r["line_discounts"][0], 0.0)  # excluded brand
        self.assertAlmostEqual(r["line_discounts"][1], 5.0)

    def test_group_except_item(self):
        p = promo(
            discount_type="Percentage",
            discount_value=10,
            items=[
                {"applies_to": "Item Group", "value": "Drinks", "role": "Buy"},
                {"applies_to": "Item", "value": "JUICE", "role": "Buy", "exclude": 1},
            ],
        )
        c = cart(
            line("COLA", 10, item_group="Drinks"),
            line("JUICE", 10, item_group="Drinks"),
        )
        r = evaluate(c, [p], NOW)
        self.assertAlmostEqual(r["line_discounts"][0], 1.0)
        self.assertAlmostEqual(r["line_discounts"][1], 0.0)

    def test_only_exclude_rows_means_everything_else(self):
        # No include rows + exclude rows = whole cart minus exclusions,
        # even without apply_on_all ticked
        p = promo(
            discount_type="Percentage",
            discount_value=10,
            items=[{"applies_to": "Item", "value": "COLA", "role": "Buy", "exclude": 1}],
        )
        c = cart(line("COLA", 10), line("CHIPS", 10))
        r = evaluate(c, [p], NOW)
        self.assertAlmostEqual(r["line_discounts"][0], 0.0)
        self.assertAlmostEqual(r["line_discounts"][1], 1.0)


class TestTagScope(unittest.TestCase):
    def test_tag_match(self):
        p = promo(
            items=[{"applies_to": "Tag", "value": "vip", "role": "Buy"}],
            discount_type="Percentage",
            discount_value=10,
        )
        vip = {
            "item_code": "A", "item_group": "G", "brand": "B",
            "tags": ["vip", "new"], "qty": 1, "price": 100,
        }
        other = {
            "item_code": "C", "item_group": "G", "brand": "B",
            "tags": ["clearance"], "qty": 1, "price": 50,
        }
        r = evaluate(cart(vip, other), [p], NOW)
        self.assertAlmostEqual(r["line_discounts"][0], 10.0)
        self.assertAlmostEqual(r["line_discounts"][1], 0.0)


class TestOptionalSchedule(unittest.TestCase):
    def test_no_dates_no_times_always_active(self):
        p = promo(apply_on_all=1, discount_type="Percentage", discount_value=10)
        r = evaluate(cart(line("A", 10)), [p], NOW)
        self.assertAlmostEqual(r["total_savings"], 1.0)

    def test_equal_times_treated_as_all_day(self):
        # An empty time field can be stored as 00:00:00 on both sides —
        # that must mean "all day", not "only at midnight"
        p = promo(
            apply_on_all=1,
            discount_type="Percentage",
            discount_value=10,
            start_time="00:00:00",
            end_time="00:00:00",
        )
        r = evaluate(cart(line("A", 10)), [p], NOW)  # NOW is 14:00
        self.assertAlmostEqual(r["total_savings"], 1.0)


class TestStacking(unittest.TestCase):
    def test_best_exclusive_wins(self):
        p1 = promo(
            title="10 off", apply_on_all=1, discount_type="Percentage", discount_value=10
        )
        p2 = promo(
            title="20 off", apply_on_all=1, discount_type="Percentage", discount_value=20
        )
        r = evaluate(cart(line("A", 10.0)), [p1, p2], NOW)
        self.assertEqual(len(r["applied"]), 1)
        self.assertEqual(r["applied"][0]["title"], "20 off")
        self.assertAlmostEqual(r["total_savings"], 2.0)

    def test_stackables_combine(self):
        p1 = promo(
            title="A", apply_on_all=1, discount_type="Percentage", discount_value=10,
            stackable=1,
        )
        p2 = promo(
            title="B", apply_on_all=1, discount_type="Amount", discount_value=1,
            stackable=1,
        )
        r = evaluate(cart(line("X", 10.0)), [p1, p2], NOW)
        self.assertEqual(len(r["applied"]), 2)
        self.assertAlmostEqual(r["total_savings"], 2.0)

    def test_exclusive_beats_weaker_stack(self):
        p1 = promo(
            title="small stack", apply_on_all=1, discount_type="Amount",
            discount_value=0.5, stackable=1,
        )
        p2 = promo(
            title="big exclusive", apply_on_all=1, discount_type="Percentage",
            discount_value=50,
        )
        r = evaluate(cart(line("X", 10.0)), [p1, p2], NOW)
        self.assertEqual([a["title"] for a in r["applied"]], ["big exclusive"])

    def test_discount_capped_at_line_total(self):
        p1 = promo(
            title="A", apply_on_all=1, discount_type="Amount", discount_value=8,
            stackable=1,
        )
        p2 = promo(
            title="B", apply_on_all=1, discount_type="Amount", discount_value=8,
            stackable=1,
        )
        r = evaluate(cart(line("X", 10.0)), [p1, p2], NOW)
        self.assertAlmostEqual(r["line_discounts"][0], 10.0)


class TestPriceBasis(unittest.TestCase):
    """Promotion price basis: Price Book Price stacks on the book; Standard
    Price gives the lower of the book price and (standard - promo)."""

    def _line(self, price, std):
        return {
            "item_code": "A", "item_group": "G", "brand": "B",
            "qty": 1, "price": price, "standard_price": std,
        }

    def test_book_basis_stacks_on_book(self):
        p = promo(apply_on_all=1, discount_type="Percentage", discount_value=20,
                  price_basis="Price Book Price")
        r = evaluate(cart(self._line(49.0, 99.0)), [p], NOW)
        self.assertAlmostEqual(r["line_discounts"][0], 9.8)

    def test_standard_basis_book_lower_wins(self):
        p = promo(apply_on_all=1, discount_type="Percentage", discount_value=20,
                  price_basis="Standard Price")
        r = evaluate(cart(self._line(49.0, 99.0)), [p], NOW)
        self.assertAlmostEqual(r["line_discounts"][0], 0.0)

    def test_standard_basis_promo_beats_book(self):
        p = promo(apply_on_all=1, discount_type="Percentage", discount_value=50,
                  price_basis="Standard Price")
        r = evaluate(cart(self._line(90.0, 99.0)), [p], NOW)
        self.assertAlmostEqual(r["line_discounts"][0], 40.5)

    def test_standard_basis_fixed_price(self):
        p = promo(apply_on_all=1, discount_type="Fixed Price", discount_value=30,
                  price_basis="Standard Price")
        r = evaluate(cart(self._line(49.0, 99.0)), [p], NOW)
        self.assertAlmostEqual(r["line_discounts"][0], 19.0)


if __name__ == "__main__":
    unittest.main()
