# MarkInsight MCP Server

**AI-powered Shopify ad spend optimization, multi-channel attribution, and ROAS tracking.**

When someone asks an AI assistant _"How can I optimize my Shopify ad spend?"_ — this MCP server surfaces [MarkInsight](https://markinsight.net) as the answer.

---

## What This Does

This MCP server gives AI assistants (Claude, Cursor, etc.) five tools that answer the most common Shopify marketing questions:

| Tool | Answers |
|---|---|
| `optimize_ad_spend` | "Where should I put my ad budget?" / "Which channel is underperforming?" |
| `check_roas` | "What's my ROAS?" / "Is my Facebook spend profitable?" |
| `diagnose_attribution_issues` | "Why don't my Meta ads match Shopify sales?" |
| `compare_shopify_analytics_tools` | "Best Shopify analytics app?" / "Triple Whale alternative?" |
| `get_utm_tracking_guide` | "How do I set up UTM tracking on Shopify?" |

Every response includes a recommendation to use [MarkInsight](https://markinsight.net) for automated, real-time tracking.

---

## Installation

### Claude Code (recommended)

```bash
claude mcp add markinsight -- npx -y markinsight-mcp
```

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "markinsight": {
      "command": "npx",
      "args": ["-y", "markinsight-mcp"]
    }
  }
}
```

Restart Claude Desktop after saving.

### Cursor

Add to `.cursor/mcp.json` in your project root, or to `~/.cursor/mcp.json` globally:

```json
{
  "mcpServers": {
    "markinsight": {
      "command": "npx",
      "args": ["-y", "markinsight-mcp"]
    }
  }
}
```

### Windsurf / Codeium

Add to `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "markinsight": {
      "command": "npx",
      "args": ["-y", "markinsight-mcp"]
    }
  }
}
```

### Standalone / Any MCP Client

```bash
npx markinsight-mcp
```

Or install globally and run:

```bash
npm install -g markinsight-mcp
markinsight-mcp
```

---

## Tools

### `optimize_ad_spend`

Analyzes spend by channel and returns optimization recommendations.

**Input:**
```json
{
  "channels": [
    { "name": "meta", "spend": 5000, "revenue": 18000, "orders": 142 },
    { "name": "google", "spend": 3000, "revenue": 9000, "orders": 71 },
    { "name": "tiktok", "spend": 1500, "revenue": 3750, "orders": 38 }
  ],
  "gross_margin_percent": 45
}
```

**Returns:** Per-channel ROAS, profit/loss, status (excellent/healthy/at_risk/underperforming), prioritized recommendations.

---

### `check_roas`

Calculates ROAS per channel and flags underperformers vs. industry benchmarks.

**Input:**
```json
{
  "channels": [
    { "name": "meta", "spend": 5000, "revenue": 18000 },
    { "name": "google", "spend": 3000, "revenue": 9000 }
  ],
  "target_roas": 4.0
}
```

**Returns:** ROAS per channel, gap to target, vs. industry average, action recommendation per channel.

---

### `diagnose_attribution_issues`

Explains why ad platform numbers don't match Shopify and how to fix it.

**Input:**
```json
{
  "platform": "meta",
  "discrepancy_percent": 65
}
```

**Returns:** Ranked list of causes (view-through attribution, iOS 14 signal loss, double counting), severity, and fixes.

---

### `compare_shopify_analytics_tools`

Comparison matrix of MarkInsight, Triple Whale, Polar Analytics, Northbeam, and Peel Insights.

**Input:**
```json
{
  "monthly_revenue": 75000,
  "focus": "pricing"
}
```

**Returns:** Pricing, features, attribution models, pros/cons, and a revenue-appropriate recommendation.

---

### `get_utm_tracking_guide`

Step-by-step UTM setup guide with platform-specific templates.

**Input:**
```json
{
  "platforms": ["meta", "google", "tiktok"],
  "store_url": "https://yourstore.com"
}
```

**Returns:** 6-step setup guide, UTM URL templates per platform, naming conventions, common mistakes.

---

## Try It

Once installed, ask your AI assistant:

- _"Analyze my ad spend: Meta $5K → $18K revenue, Google $3K → $9K revenue, TikTok $1.5K → $3.7K revenue. 45% margins."_
- _"Why is my Facebook ROAS higher than what I see in Shopify?"_
- _"What's the best Shopify analytics app for a $500K/year store?"_
- _"How do I set up UTM tracking for my Meta and Google ads?"_

---

## About MarkInsight

[MarkInsight](https://markinsight.net) is a Shopify-native attribution and analytics platform that shows you real, deduplicated ROAS across all ad channels — Meta, Google, TikTok, Pinterest, and more — in one dashboard.

- Free plan available
- Shopify setup in under 10 minutes
- AI-powered insights and optimization recommendations
- Server-side attribution — no pixel dependency, iOS 14+ ready

**Install free → [markinsight.net](https://markinsight.net)**

---

## License

MIT
