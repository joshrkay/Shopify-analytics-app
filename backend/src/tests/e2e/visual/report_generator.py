"""
HTML Report Generator for E2E Visual Tests.

Generates beautiful, interactive HTML reports for visual verification
of API test results.
"""

import json
import html
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from src.tests.e2e.visual.run_visual_tests import PlatformTestResults, TestResult, TestStatus


class HTMLReportGenerator:
    """Generates HTML reports from test results."""

    def __init__(self, results: List[PlatformTestResults], output_dir: Path):
        self.results = results
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self) -> Path:
        """Generate HTML report and return the path."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = self.output_dir / f"visual_test_report_{timestamp}.html"

        html_content = self._generate_html()

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return report_path

    def _generate_html(self) -> str:
        """Generate the full HTML content."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>E2E Visual Test Report - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</title>
    <style>
        {self._get_css()}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>E2E Visual API Test Report</h1>
            <p class="timestamp">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </header>

        <section class="summary">
            <h2>Summary</h2>
            {self._generate_summary()}
        </section>

        <section class="results">
            <h2>Test Results</h2>
            {self._generate_platform_results()}
        </section>

        <footer>
            <p>Shopify Analytics App - E2E Visual Testing Suite</p>
        </footer>
    </div>

    <script>
        {self._get_js()}
    </script>
</body>
</html>"""

    def _get_css(self) -> str:
        """Return CSS styles."""
        return """
        :root {
            --color-pass: #22c55e;
            --color-fail: #ef4444;
            --color-error: #f97316;
            --color-skip: #6b7280;
            --color-pending: #3b82f6;
            --color-bg: #f8fafc;
            --color-card: #ffffff;
            --color-border: #e2e8f0;
            --color-text: #1e293b;
            --color-text-muted: #64748b;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background-color: var(--color-bg);
            color: var(--color-text);
            line-height: 1.6;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }

        header {
            text-align: center;
            margin-bottom: 2rem;
            padding-bottom: 2rem;
            border-bottom: 1px solid var(--color-border);
        }

        header h1 {
            font-size: 2rem;
            margin-bottom: 0.5rem;
        }

        .timestamp {
            color: var(--color-text-muted);
        }

        section {
            margin-bottom: 2rem;
        }

        section h2 {
            font-size: 1.5rem;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 2px solid var(--color-border);
        }

        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
        }

        .summary-card {
            background: var(--color-card);
            border-radius: 8px;
            padding: 1.5rem;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            text-align: center;
        }

        .summary-card h3 {
            font-size: 0.875rem;
            color: var(--color-text-muted);
            text-transform: uppercase;
            margin-bottom: 0.5rem;
        }

        .summary-card .value {
            font-size: 2rem;
            font-weight: bold;
        }

        .summary-card.passed .value { color: var(--color-pass); }
        .summary-card.failed .value { color: var(--color-fail); }
        .summary-card.error .value { color: var(--color-error); }
        .summary-card.skipped .value { color: var(--color-skip); }

        .platform-section {
            background: var(--color-card);
            border-radius: 8px;
            margin-bottom: 1.5rem;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }

        .platform-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem 1.5rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            cursor: pointer;
        }

        .platform-header.shopify {
            background: linear-gradient(135deg, #96bf48 0%, #5fa23a 100%);
        }

        .platform-header.meta {
            background: linear-gradient(135deg, #1877f2 0%, #0d5ed6 100%);
        }

        .platform-header.google {
            background: linear-gradient(135deg, #4285f4 0%, #ea4335 50%, #fbbc04 100%);
        }

        .platform-header h3 {
            font-size: 1.25rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .platform-meta {
            display: flex;
            gap: 1rem;
            font-size: 0.875rem;
        }

        .status-badge {
            display: inline-flex;
            align-items: center;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }

        .status-badge.passed { background: var(--color-pass); color: white; }
        .status-badge.failed { background: var(--color-fail); color: white; }
        .status-badge.error { background: var(--color-error); color: white; }
        .status-badge.skipped { background: var(--color-skip); color: white; }

        .test-list {
            padding: 0;
        }

        .test-item {
            border-bottom: 1px solid var(--color-border);
        }

        .test-item:last-child {
            border-bottom: none;
        }

        .test-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem 1.5rem;
            cursor: pointer;
            transition: background-color 0.2s;
        }

        .test-header:hover {
            background-color: var(--color-bg);
        }

        .test-name {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .test-name .icon {
            font-size: 1.25rem;
        }

        .test-name .icon.passed { color: var(--color-pass); }
        .test-name .icon.failed { color: var(--color-fail); }
        .test-name .icon.error { color: var(--color-error); }
        .test-name .icon.skipped { color: var(--color-skip); }

        .test-meta {
            display: flex;
            gap: 1rem;
            color: var(--color-text-muted);
            font-size: 0.875rem;
        }

        .test-details {
            display: none;
            padding: 1rem 1.5rem;
            background: var(--color-bg);
            border-top: 1px solid var(--color-border);
        }

        .test-details.open {
            display: block;
        }

        .test-message {
            margin-bottom: 1rem;
            padding: 0.75rem 1rem;
            background: white;
            border-radius: 4px;
            border-left: 4px solid var(--color-pass);
        }

        .test-message.error {
            border-left-color: var(--color-fail);
            color: var(--color-fail);
        }

        .test-data {
            background: #1e293b;
            color: #e2e8f0;
            padding: 1rem;
            border-radius: 4px;
            overflow-x: auto;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.875rem;
        }

        .test-data pre {
            margin: 0;
            white-space: pre-wrap;
            word-break: break-word;
        }

        footer {
            text-align: center;
            padding-top: 2rem;
            color: var(--color-text-muted);
            font-size: 0.875rem;
        }

        .expand-icon {
            transition: transform 0.2s;
        }

        .expanded .expand-icon {
            transform: rotate(90deg);
        }
        """

    def _get_js(self) -> str:
        """Return JavaScript for interactivity."""
        return """
        document.querySelectorAll('.test-header').forEach(header => {
            header.addEventListener('click', () => {
                const item = header.closest('.test-item');
                const details = item.querySelector('.test-details');
                details.classList.toggle('open');
                header.classList.toggle('expanded');
            });
        });

        document.querySelectorAll('.platform-header').forEach(header => {
            header.addEventListener('click', () => {
                const section = header.closest('.platform-section');
                const testList = section.querySelector('.test-list');
                testList.style.display = testList.style.display === 'none' ? 'block' : 'none';
            });
        });
        """

    def _generate_summary(self) -> str:
        """Generate summary cards."""
        total_tests = 0
        passed = 0
        failed = 0
        errors = 0
        skipped = 0

        for result in self.results:
            for test in result.tests:
                total_tests += 1
                if test.status == TestStatus.PASSED:
                    passed += 1
                elif test.status == TestStatus.FAILED:
                    failed += 1
                elif test.status == TestStatus.ERROR:
                    errors += 1
                elif test.status == TestStatus.SKIPPED:
                    skipped += 1

        return f"""
        <div class="summary-grid">
            <div class="summary-card">
                <h3>Total Tests</h3>
                <div class="value">{total_tests}</div>
            </div>
            <div class="summary-card passed">
                <h3>Passed</h3>
                <div class="value">{passed}</div>
            </div>
            <div class="summary-card failed">
                <h3>Failed</h3>
                <div class="value">{failed}</div>
            </div>
            <div class="summary-card error">
                <h3>Errors</h3>
                <div class="value">{errors}</div>
            </div>
            <div class="summary-card skipped">
                <h3>Skipped</h3>
                <div class="value">{skipped}</div>
            </div>
        </div>
        """

    def _generate_platform_results(self) -> str:
        """Generate platform result sections."""
        sections = []

        for result in self.results:
            platform_class = result.platform.lower().replace(" ", "-")
            if "shopify" in platform_class:
                platform_class = "shopify"
            elif "meta" in platform_class:
                platform_class = "meta"
            elif "google" in platform_class:
                platform_class = "google"

            status_class = result.status.value.lower()

            tests_html = self._generate_test_items(result.tests)

            section = f"""
            <div class="platform-section">
                <div class="platform-header {platform_class}">
                    <h3>
                        {self._get_platform_icon(result.platform)}
                        {result.platform}
                    </h3>
                    <div class="platform-meta">
                        <span class="status-badge {status_class}">{result.status.value}</span>
                        <span>{result.passed_count}/{len(result.tests)} passed</span>
                        <span>{result.duration_ms:.0f}ms</span>
                    </div>
                </div>
                <div class="test-list">
                    {tests_html}
                </div>
            </div>
            """
            sections.append(section)

        return "\n".join(sections)

    def _generate_test_items(self, tests: List[TestResult]) -> str:
        """Generate test item HTML."""
        items = []

        for test in tests:
            status_class = test.status.value.lower()
            icon = self._get_status_icon(test.status)

            message_html = ""
            if test.message:
                message_html = f'<div class="test-message">{html.escape(test.message)}</div>'
            if test.error:
                message_html = f'<div class="test-message error">{html.escape(test.error)}</div>'

            data_html = ""
            if test.data:
                formatted_data = json.dumps(test.data, indent=2, default=str)
                data_html = f'<div class="test-data"><pre>{html.escape(formatted_data)}</pre></div>'

            item = f"""
            <div class="test-item">
                <div class="test-header">
                    <div class="test-name">
                        <span class="icon {status_class}">{icon}</span>
                        <span>{html.escape(test.name)}</span>
                    </div>
                    <div class="test-meta">
                        <span class="status-badge {status_class}">{test.status.value}</span>
                        <span>{test.duration_ms:.0f}ms</span>
                        <span class="expand-icon">&#9654;</span>
                    </div>
                </div>
                <div class="test-details">
                    {message_html}
                    {data_html}
                </div>
            </div>
            """
            items.append(item)

        return "\n".join(items)

    def _get_platform_icon(self, platform: str) -> str:
        """Get emoji icon for platform."""
        icons = {
            "Shopify": "🛍️",
            "Meta Ads": "📘",
            "Google Ads": "🔍",
        }
        return icons.get(platform, "📊")

    def _get_status_icon(self, status: TestStatus) -> str:
        """Get emoji icon for status."""
        icons = {
            TestStatus.PASSED: "✅",
            TestStatus.FAILED: "❌",
            TestStatus.ERROR: "⚠️",
            TestStatus.SKIPPED: "⏭️",
            TestStatus.PENDING: "⏳",
            TestStatus.RUNNING: "🔄",
        }
        return icons.get(status, "❓")
