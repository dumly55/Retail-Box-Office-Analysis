"""Plain-English findings about the sales data, from fixed rules (no AI), so the same data always
produces the same text. Each rule returns a sentence only when it has something to say."""

import pandas as pd

from .sales_kpis import SalesReportData

HIGH_CANCELLATION_SHARE = 0.10  # cancellations worth at least this share of revenue get called out


def _money(value: float, currency: str) -> str:
    return f"{'-' if value < 0 else ''}{currency}{abs(value):,.2f}"


def _headline(data: SalesReportData) -> str:
    t, cur = data.totals, data.currency

    def plural(n: int, word: str) -> str:
        return f"{n:,} {word}{'' if n == 1 else 's'}"

    customers = f" from {plural(t['customers'], 'customer')}" if t["customers"] is not None else ""
    return (
        f"From {data.start:%Y-%m-%d} to {data.end:%Y-%m-%d}, {plural(t['orders'], 'order')}{customers} brought in "
        f"{_money(t['revenue'], cur)} (an average of {_money(t['avg_order_value'], cur)} per order)."
    )


def _months(data: SalesReportData) -> list[str]:
    """Best and weakest month and the overall trend, counting only months the data fully covers."""
    monthly = data.monthly
    month_end = monthly["Month"] + pd.offsets.MonthEnd(0)
    full = (monthly["Month"] >= data.start.normalize()) & (month_end <= data.end.normalize())
    complete = monthly[full]
    if len(complete) < 2:
        return []

    findings = []
    partial = [f"{m:%B %Y}" for m in monthly.loc[~full, "Month"]]
    if partial:
        one = len(partial) == 1
        findings.append(
            f"Note: {' and '.join(partial)} {'is' if one else 'are'} only partly covered by the data, "
            f"so {'it is' if one else 'they are'} left out of the month-by-month comparisons."
        )

    best, worst = complete.loc[complete["Revenue"].idxmax()], complete.loc[complete["Revenue"].idxmin()]
    findings.append(
        f"The best month was {best['Month']:%B %Y} ({_money(best['Revenue'], data.currency)}); "
        f"the weakest was {worst['Month']:%B %Y} ({_money(worst['Revenue'], data.currency)})."
    )
    first, last = complete.iloc[0], complete.iloc[-1]
    if first["Revenue"]:
        change = (last["Revenue"] - first["Revenue"]) / first["Revenue"] * 100
        findings.append(
            f"Monthly revenue went from {_money(first['Revenue'], data.currency)} in {first['Month']:%B %Y} "
            f"to {_money(last['Revenue'], data.currency)} in {last['Month']:%B %Y} ({change:+.1f}%)."
        )
    return findings


def _top_country(data: SalesReportData) -> str | None:
    by_country = data.by_country
    if len(by_country) < 2:
        return None
    total = by_country["Revenue"].sum()
    top, runner_up = by_country.iloc[0], by_country.iloc[1]
    return (
        f"{top['Country']} brought in {top['Revenue'] / total:.0%} of revenue. "
        f"The next biggest market was {runner_up['Country']}, with {runner_up['Revenue'] / total:.0%}."
    )


def _best_seller(sales: pd.DataFrame, currency: str) -> str:
    by_product = sales.groupby("Description")["LineTotal"].sum().sort_values(ascending=False)
    total = by_product.sum()
    top_name, top_revenue = by_product.index[0], by_product.iloc[0]
    sentence = f"Best seller: {top_name} ({_money(top_revenue, currency)}, {top_revenue / total:.0%} of revenue)."
    if len(by_product) > 10:
        sentence += f" The top 10 products made up {by_product.head(10).sum() / total:.0%} of revenue."
    return sentence


def _busiest_weekday(sales: pd.DataFrame) -> str | None:
    if sales["InvoiceDate"].dt.normalize().nunique() < 7:
        return None
    by_day = sales.groupby(sales["InvoiceDate"].dt.day_name())["LineTotal"].sum()
    return f"{by_day.idxmax()} was the busiest day of the week, with {by_day.max() / by_day.sum():.0%} of revenue."


def _cancellations(data: SalesReportData) -> str | None:
    count, value = data.totals["cancellations_count"], data.totals["cancellations_value"]
    if not count:
        return None
    revenue = data.totals["revenue"]
    sentence = f"{count:,} order{'s were' if count != 1 else ' was'} cancelled, worth {_money(value, data.currency)}"
    sentence += f" ({value / revenue:.1%} of revenue)."
    if value / revenue >= HIGH_CANCELLATION_SHARE:
        sentence += f" That's unusually high: revenue after cancellations was {_money(revenue - value, data.currency)}."
    return sentence


def build_findings(sales_df: pd.DataFrame, data: SalesReportData) -> list[str]:
    candidates = [
        _headline(data),
        *_months(data),
        _top_country(data),
        _best_seller(sales_df, data.currency),
        _busiest_weekday(sales_df),
        _cancellations(data),
    ]
    return [finding for finding in candidates if finding]
