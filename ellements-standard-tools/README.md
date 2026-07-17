# ellements-standard-tools

Framework-agnostic, LLM-callable tools built on stable Ellements tool
primitives.

The package currently contains:

- dependency-light terminal execution tools under `ellements.standard_tools`;
- DDGS-backed web and news search tools;
- Crawl4AI-backed page crawl/read tools;
- YouTube search and transcript tools.

## Install

```bash
pip install "ellements[standard-tools]"
```

More focused extras are available:

```bash
pip install "ellements[web-search]"
pip install "ellements[web-crawl]"
pip install "ellements[web-youtube]"
pip install "ellements[web]"       # all web-oriented tools
```

For crawling, install the browser runtime required by Crawl4AI:

```bash
playwright install chromium
```

## Web search

```python
from ellements.standard_tools.web.search import web_search_tools

tools = web_search_tools()
results = await tools["search_news"].invoke(
    query="AAPL earnings analyst reaction",
    max_results=5,
    time_range="m",
)
```

`web_search_tools()` returns a canonical `ToolRegistry` with `search_web` and
`search_news`.

## Web crawl/read

```python
from ellements.standard_tools.web.crawler import web_crawler_tools

tools = web_crawler_tools(max_content_tokens=4000)
markdown = await tools["crawl_url"].invoke(url="https://example.com/article")
```

`crawl_url` returns clean Markdown content and can optionally truncate long
pages through the shared Ellements text processor.

## Terminal tool

```python
from ellements.standard_tools import terminal_cli_tool

tool = terminal_cli_tool(timeout_seconds=30)
```

The terminal tool is intentionally explicit and bounded: callers pass argv or a
trusted shell script, working directory, environment, stdin, timeout, and output
limits.

## Tests

Deterministic tests run with the normal project test command. Live web/browser
e2e tests are skipped unless explicitly enabled:

```bash
python -m pytest ellements-standard-tools/tests -q
ELLEMENTS_RUN_NETWORK_TESTS=1 python -m pytest \
  ellements-standard-tools/tests/test_standard_tools/test_web_search_tools_e2e.py \
  ellements-standard-tools/tests/test_standard_tools/test_web_crawler_tools_e2e.py -q
```
