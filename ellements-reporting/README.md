# ellements-reporting

Reporting, chart, and presentation helpers for Ellements applications.

This source root is promoted alongside the finance tools because technical
finance charts use the shared chart-artifact pipeline rather than carrying a
private renderer.

## Install

```bash
pip install "ellements[reporting]"
```

## Chart artifacts

```python
from ellements.reporting import create_chart_artifacts

artifact = create_chart_artifacts(
    {
        "type": "line",
        "title": "Example trend",
        "x": ["Q1", "Q2", "Q3"],
        "y": [1.0, 1.4, 1.2],
    }
)
```

The output is designed for report surfaces and chat/canvas-style interfaces:
structured chart data, embeddable HTML, and image payloads when matplotlib is
available.

## HTML reports

`HTMLReportGenerator` and `MultiFormatReportExporter` provide small reusable
building blocks for application-level report generation. They are intentionally
framework-neutral and do not impose a larger report app.

## Tests

```bash
python -m pytest ellements-reporting/tests -q
```
