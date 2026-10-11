import pandas as pd

from src.findings import build_findings
from src.report import build_report_data


def _row(order, product, qty, when, price, customer=1, country="United States"):
    return {
        "InvoiceNo": order,
        "StockCode": product,
        "Description": product,
        "Quantity": qty,
        "InvoiceDate": pd.Timestamp(when),
        "UnitPrice": price,
        "CustomerID": customer,
        "Country": country,
        "LineTotal": qty * price,
    }


def _findings(rows, cancellations=()):
    sales = pd.DataFrame(rows)
    cancels = pd.DataFrame(list(cancellations), columns=sales.columns)
    data = build_report_data(sales, cancels, currency="$")
    return build_findings(sales, data)


def _has(findings, text):
    return any(text in f for f in findings)


def _three_months():
    """Full January to March 2024 (sales on the 1st and last day of each month): $100, $300, then $200."""
    days = [("2024-01-01", 50.0), ("2024-01-31", 50.0), ("2024-02-01", 150.0), ("2024-02-29", 150.0),
            ("2024-03-01", 100.0), ("2024-03-31", 100.0)]
    return [_row(str(i), "Mug", 1, day, price) for i, (day, price) in enumerate(days)]


class TestHeadline:
    def test_totals_for_the_whole_period(self):
        rows = [_row("1", "Mug", 1, "2024-09-03", 100.0, customer=1), _row("2", "Mug", 1, "2024-09-15", 50.0, customer=2)]
        assert _findings(rows)[0] == (
            "From 2024-09-03 to 2024-09-15, 2 orders from 2 customers brought in $150.00 (an average of $75.00 per order)."
        )

    def test_leaves_out_customers_when_they_cant_be_counted(self):
        rows = [_row("1", "Mug", 1, "2024-09-03", 100.0, customer=None)]
        assert _findings(rows)[0] == "From 2024-09-03 to 2024-09-03, 1 order brought in $100.00 (an average of $100.00 per order)."


class TestMonths:
    def test_best_and_weakest_month_and_trend(self):
        findings = _findings(_three_months())
        assert "The best month was February 2024 ($300.00); the weakest was January 2024 ($100.00)." in findings
        assert "Monthly revenue went from $100.00 in January 2024 to $200.00 in March 2024 (+100.0%)." in findings

    def test_partly_covered_months_are_left_out(self):
        findings = _findings(_three_months() + [_row("9", "Mug", 1, "2024-04-10", 999.0)])
        assert "Note: April 2024 is only partly covered by the data, so it is left out of the month-by-month comparisons." in findings
        assert _has(findings, "The best month was February 2024")

    def test_silent_with_fewer_than_two_full_months(self):
        assert not _has(_findings([_row("1", "Mug", 1, "2024-09-03", 100.0)]), "month")


class TestTopCountry:
    def test_names_the_biggest_market_and_the_next(self):
        rows = [
            _row("1", "Mug", 1, "2024-09-03", 80.0, country="United Kingdom"),
            _row("2", "Mug", 1, "2024-09-04", 15.0, country="France"),
            _row("3", "Mug", 1, "2024-09-05", 5.0, country="Germany"),
        ]
        assert "United Kingdom brought in 80% of revenue. The next biggest market was France, with 15%." in _findings(rows)

    def test_silent_with_one_country(self):
        assert not _has(_findings([_row("1", "Mug", 1, "2024-09-03", 100.0)]), "biggest market")


class TestBestSellerAndWeekday:
    def test_best_seller_and_top_ten_share(self):
        rows = [_row(str(i), f"Product {i}", 1, "2024-09-15", 10.0) for i in range(11)]
        rows.append(_row("big", "Lamp", 1, "2024-09-15", 90.0))
        assert _has(_findings(rows), "Best seller: Lamp ($90.00, 45% of revenue). The top 10 products made up 90% of revenue.")

    def test_top_ten_share_skipped_with_few_products(self):
        findings = _findings([_row("1", "Mug", 1, "2024-09-15", 10.0)])
        assert _has(findings, "Best seller: Mug ($10.00, 100% of revenue).")
        assert not _has(findings, "top 10")

    def test_busiest_weekday(self):
        rows = [_row(str(day), "Mug", 1, f"2024-09-{day:02d}", 10.0) for day in range(2, 9)]  # Mon 2nd to Sun 8th
        rows.append(_row("big", "Mug", 1, "2024-09-05", 30.0))  # a big Thursday
        assert "Thursday was the busiest day of the week, with 40% of revenue." in _findings(rows)

    def test_weekday_needs_at_least_a_week_of_days(self):
        assert not _has(_findings([_row("1", "Mug", 1, "2024-09-03", 10.0)]), "busiest day")


class TestCancellations:
    def test_reports_cancelled_orders_and_their_share(self):
        rows = [_row("1", "Mug", 1, "2024-09-15", 200.0), _row("2", "Mug", 1, "2024-09-15", 200.0)]
        cancels = [_row("C1", "Mug", -1, "2024-09-12", 10.0), _row("C2", "Pen", -2, "2024-09-13", 5.0)]
        assert "2 orders were cancelled, worth $20.00 (5.0% of revenue)." in _findings(rows, cancels)

    def test_calls_out_unusually_high_cancellations(self):
        rows = [_row("1", "Mug", 1, "2024-09-15", 200.0)]
        cancels = [_row("C1", "Mug", -1, "2024-09-12", 10.0), _row("C2", "Pen", -2, "2024-09-13", 5.0)]
        assert (
            "2 orders were cancelled, worth $20.00 (10.0% of revenue). "
            "That's unusually high: revenue after cancellations was $180.00."
        ) in _findings(rows, cancels)

    def test_silent_without_cancellations(self):
        assert not _has(_findings([_row("1", "Mug", 1, "2024-09-15", 200.0)]), "cancelled")
