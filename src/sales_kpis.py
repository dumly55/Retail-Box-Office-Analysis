"""KPIs for the sales analysis: totals over the whole dataset, a month-by-month trend, and breakdowns."""

from dataclasses import dataclass, field

import pandas as pd


def _summarize(sales: pd.DataFrame, cancellations: pd.DataFrame) -> dict:
    revenue = float(sales["LineTotal"].sum())
    orders = int(sales["InvoiceNo"].nunique())
    # A sheet without a customer column has no IDs at all, so customers can't be counted (not zero).
    count_customers = bool(sales["CustomerID"].notna().any())
    return {
        "revenue": revenue,
        "units": int(sales["Quantity"].sum()),
        "orders": orders,
        "avg_order_value": revenue / orders if orders else 0.0,
        "customers": int(sales["CustomerID"].nunique()) if count_customers else None,
        "cancellations_count": int(cancellations["InvoiceNo"].nunique()),
        "cancellations_value": float(-cancellations["LineTotal"].sum()),
    }


def top_products(sales: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    return (
        sales.groupby(["StockCode", "Description"], dropna=False)
        .agg(Revenue=("LineTotal", "sum"), UnitsSold=("Quantity", "sum"))
        .reset_index()
        .sort_values("Revenue", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )


def revenue_by_country(sales: pd.DataFrame) -> pd.DataFrame:
    return (
        sales.groupby("Country")
        .agg(Revenue=("LineTotal", "sum"), Orders=("InvoiceNo", "nunique"))
        .reset_index()
        .sort_values("Revenue", ascending=False)
        .reset_index(drop=True)
    )


def monthly_revenue(sales: pd.DataFrame) -> pd.DataFrame:
    """Revenue and orders per calendar month (Month = the 1st of the month), including months with no sales."""
    months = sales["InvoiceDate"].dt.to_period("M")
    monthly = sales.groupby(months).agg(Revenue=("LineTotal", "sum"), Orders=("InvoiceNo", "nunique"))
    every_month = pd.period_range(months.min(), months.max(), freq="M")
    monthly = monthly.reindex(every_month, fill_value=0)
    return pd.DataFrame(
        {"Month": every_month.to_timestamp(), "Revenue": monthly["Revenue"].to_numpy(), "Orders": monthly["Orders"].to_numpy()}
    )


@dataclass
class SalesReportData:
    start: pd.Timestamp  # first sale in the data
    end: pd.Timestamp  # last sale in the data
    totals: dict
    monthly: pd.DataFrame
    top_products: pd.DataFrame
    by_country: pd.DataFrame
    currency: str = ""
    findings: list[str] = field(default_factory=list)

    @property
    def period_label(self) -> str:
        return f"{self.start:%Y-%m-%d} to {self.end:%Y-%m-%d}"

    def summary_rows(self) -> list[tuple[str, str]]:
        """Display-formatted (metric, value) rows shared by the CLI and GUI."""
        t, cur = self.totals, self.currency

        def count(value: int | None) -> str:
            return "n/a" if value is None else f"{value:,}"

        return [
            ("Revenue", f"{cur}{t['revenue']:,.2f}"),
            ("Orders", count(t["orders"])),
            ("Average Order Value", f"{cur}{t['avg_order_value']:,.2f}"),
            ("Units Sold", count(t["units"])),
            ("Unique Customers", count(t["customers"])),
        ]


def build_report_data(sales_df: pd.DataFrame, cancellations_df: pd.DataFrame, currency: str = "") -> SalesReportData:
    if sales_df.empty:
        raise ValueError("No valid sales rows found, so there's nothing to analyze.")
    return SalesReportData(
        start=sales_df["InvoiceDate"].min(),
        end=sales_df["InvoiceDate"].max(),
        totals=_summarize(sales_df, cancellations_df),
        monthly=monthly_revenue(sales_df),
        top_products=top_products(sales_df),
        by_country=revenue_by_country(sales_df),
        currency=currency,
    )
