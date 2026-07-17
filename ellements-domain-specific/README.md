# ellements-domain-specific

Domain packages that turn stable Ellements primitives into vertical application
tools.

The first public domain is finance. It includes reusable financial calculators,
valuation helpers, portfolio/risk utilities, technical indicators, and a Yahoo
Finance-backed asset-data tool registry.

## Install

```bash
pip install "ellements[finance]"
```

Optional finance extensions:

```bash
pip install "ellements[finance-technical]"  # TA-Lib/mplfinance chart helpers
pip install "ellements[finance-quant]"      # QuantStats-backed risk summaries
```

## Finance tool registry

```python
from ellements.domain_specific.finance.yahoo_finance import finance_tools

tools = finance_tools()
print(sorted(tools))
```

The registry currently exposes:

- `search_asset`
- `get_asset_quote`
- `get_asset_profile`
- `get_financial_metrics`
- `get_income_statement`
- `get_balance_sheet`
- `get_cash_flow`
- `get_analyst_recommendations`
- `get_technical_indicators`
- `get_technical_chart`

These are canonical `ellements.core.ToolRegistry`/`ToolSpec` objects. They can
be bound directly to an Ellements `LLMClient`, an agent adapter, or a PromptSpec
tool-calling example.

## Direct Yahoo Finance access

```python
from ellements.domain_specific.finance.yahoo_finance import YahooFinanceSearcher

searcher = YahooFinanceSearcher()
quote = searcher.get_asset_quote("AAPL")
profile = searcher.get_asset_profile("AAPL")
```

Live Yahoo Finance calls require network access and may be rate-limited by the
upstream service. Keep examples and tests explicit about that boundary.

## Tests

Deterministic tests run with the normal project test command. Live e2e tests are
available but skipped unless explicitly enabled:

```bash
python -m pytest ellements-domain-specific/tests -q
ELLEMENTS_RUN_NETWORK_TESTS=1 python -m pytest \
  ellements-domain-specific/tests/test_finance/test_finance_tools_e2e.py -q
```
