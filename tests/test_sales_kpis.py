import pandas as pd
import pytest

from src.sales_kpis import build_report_data, monthly_revenue, revenue_by_country, top_products


def _sales_row(invoice_no, stock_code, description, quantity, invoice_date, unit_price, customer_id, country):
    return {
        "InvoiceNo": invoice_no,
        "StockCode": stock_code,
        "Description": description,
        "Quantity": quantity,
        "InvoiceDate": pd.Timestamp(invoice_date),
        "UnitPrice": unit_price,
        "CustomerID": customer_id,
        "Country": country,
        "LineTotal": quantity * unit_price,
    }


@pytest.fixture
def sales_df():
    rows = [
        # November: revenue 280, units 28, 4 orders, 3 customers
        _sales_row("600001", "A1", "Widget", 10, "2011-11-21 10:00:00", 10.0, 1001, "United Kingdom"),
        _sales_row("600002", "B1", "Gadget", 5, "2011-11-23 11:00:00", 10.0, 1002, "France"),
        _sales_row("600003", "A1", "Widget", 3, "2011-11-25 09:00:00", 10.0, 1001, "United Kingdom"),
        _sales_row("500001", "A1", "Widget", 10, "2011-11-14 10:00:00", 10.0, 2001, "United Kingdom"),
        # October: revenue 990, units 99, 1 order, 1 more customer
        _sales_row("400001", "A1", "Widget", 99, "2011-10-01 10:00:00", 10.0, 3001, "United Kingdom"),
    ]
    return pd.DataFrame(rows)


@pytest.fixture
def cancellations_df():
    rows = [
        # cancellation: quantity -2 * price 10 -> LineTotal -20, so cancellations_value = 20
        _sales_row("C600004", "A1", "Widget", -2, "2011-11-22 08:00:00", 10.0, 1001, "United Kingdom"),
    ]
    return pd.DataFrame(rows)


class TestBuildReportData:
    def test_totals_cover_the_whole_dataset(self, sales_df, cancellations_df):
        data = build_report_data(sales_df, cancellations_df)
        assert (data.start, data.end) == (pd.Timestamp("2011-10-01 10:00"), pd.Timestamp("2011-11-25 09:00"))
        assert data.totals["revenue"] == pytest.approx(1270.0)
        assert data.totals["units"] == 127
        assert data.totals["orders"] == 5
        assert data.totals["avg_order_value"] == pytest.approx(254.0)
        assert data.totals["customers"] == 4
        assert data.totals["cancellations_count"] == 1
        assert data.totals["cancellations_value"] == pytest.approx(20.0)

    def test_customers_are_not_counted_without_customer_ids(self, sales_df, cancellations_df):
        data = build_report_data(sales_df.assign(CustomerID=float("nan")), cancellations_df)
        assert data.totals["customers"] is None
        assert data.summary_rows()[4] == ("Unique Customers", "n/a")

    def test_empty_data_raises_friendly_error(self, sales_df, cancellations_df):
        with pytest.raises(ValueError, match="nothing to analyze"):
            build_report_data(sales_df.iloc[0:0], cancellations_df)

    def test_breakdowns_included(self, sales_df, cancellations_df):
        data = build_report_data(sales_df, cancellations_df)
        assert list(data.top_products["StockCode"]) == ["A1", "B1"]
        assert list(data.by_country["Country"]) == ["United Kingdom", "France"]
        assert list(data.monthly["Month"]) == [pd.Timestamp("2011-10-01"), pd.Timestamp("2011-11-01")]


class TestDisplayHelpers:
    def test_period_label(self, sales_df, cancellations_df):
        assert build_report_data(sales_df, cancellations_df).period_label == "2011-10-01 to 2011-11-25"

    def test_summary_rows_are_formatted(self, sales_df, cancellations_df):
        data = build_report_data(sales_df, cancellations_df, currency="£")
        assert data.summary_rows() == [
            ("Revenue", "£1,270.00"),
            ("Orders", "5"),
            ("Average Order Value", "£254.00"),
            ("Units Sold", "127"),
            ("Unique Customers", "4"),
        ]

    def test_amounts_have_no_symbol_when_currency_unknown(self, sales_df, cancellations_df):
        assert build_report_data(sales_df, cancellations_df).summary_rows()[0] == ("Revenue", "1,270.00")


class TestMonthlyRevenue:
    def test_totals_each_month_and_fills_gaps_with_zero(self, sales_df):
        result = monthly_revenue(pd.concat([sales_df, pd.DataFrame([_sales_row("700001", "A1", "Widget", 1, "2012-01-05 10:00:00", 5.0, 1001, "UK")])]))
        assert list(result["Month"].dt.strftime("%Y-%m")) == ["2011-10", "2011-11", "2011-12", "2012-01"]
        assert list(result["Revenue"]) == pytest.approx([990.0, 280.0, 0.0, 5.0])
        assert list(result["Orders"]) == [1, 4, 0, 1]


class TestTopProducts:
    def test_ranks_by_revenue_descending(self, sales_df):
        result = top_products(sales_df)
        assert list(result["StockCode"]) == ["A1", "B1"]
        assert result.loc[0, "Revenue"] == pytest.approx(1220.0)
        assert result.loc[0, "UnitsSold"] == 122
        assert result.loc[1, "Revenue"] == pytest.approx(50.0)

    def test_respects_n_limit(self, sales_df):
        result = top_products(sales_df, n=1)
        assert list(result["StockCode"]) == ["A1"]


class TestRevenueByCountry:
    def test_ranks_and_counts_orders_by_country(self, sales_df):
        result = revenue_by_country(sales_df)
        assert list(result["Country"]) == ["United Kingdom", "France"]
        uk_row = result[result["Country"] == "United Kingdom"].iloc[0]
        assert uk_row["Revenue"] == pytest.approx(1220.0)
        assert uk_row["Orders"] == 4
        france_row = result[result["Country"] == "France"].iloc[0]
        assert france_row["Revenue"] == pytest.approx(50.0)
        assert france_row["Orders"] == 1
