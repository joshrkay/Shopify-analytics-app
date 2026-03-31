# Key Points: "N8N FULL COURSE 6 HOURS (Build & Sell AI Automations + Agents)"

Source analyzed: https://ytscribe.com/v/2GZ2SNXWK-c

## Course Arc
The course progresses from n8n fundamentals to business-facing automation patterns, then to AI agents, regex/data transformation, and self-hosting/deployment.

## Core Workflow Patterns Taught

### 1) Lead intake to CRM automation
- Trigger on form submission or meeting-booked event.
- Send immediate confirmation email with personalized fields.
- Write/update CRM entry (including status updates and custom field JSON).
- Business value: faster follow-up and reduced manual admin.

### 2) Prompt engineering inside n8n AI nodes
- Distinguish system prompt vs user prompt vs assistant examples.
- Use role-based prompt setup for predictable outputs.
- Treat prompts as reusable workflow assets, not one-off text.

### 3) Tool-calling AI agent architecture
- Build an AI agent that can call external tools (e.g., Google Calendar, Gmail).
- Use natural-language instructions to trigger tool usage.
- Add guardrails by constraining node fields and expected outputs.

### 4) Memory-enabled chat agents
- Add window/buffer memory for multi-turn context.
- Tune memory size for accuracy vs cost.
- Demonstrate behavior differences between stateless and stateful agents.

### 5) Web extraction + structured JSON output
- Scrape site text into arrays.
- Join/clean text before LLM processing.
- Return strict JSON fields for downstream automations.

### 6) Regex and transformation fundamentals
- Use extraction patterns for targeted values.
- Normalize inbound strings before routing and enrichment.
- Use lightweight transforms to reduce model load.

### 7) Self-hosting and deployment options
- Compare managed vs self-hosted setup tradeoffs.
- Show DigitalOcean flow (marketplace deployment, DNS mapping).
- Mention Docker/local options for advanced users.

## Reusable Business Offers (derived from the course)
- AI inbox triage agent for founders.
- Meeting-booked to CRM automation for agencies.
- Customer inquiry routing with memory-enabled support agent.
- Website intelligence extraction for sales and marketing research.

## Implementation Notes for Skill Users
- Start with one clear trigger + one clear business outcome.
- Keep every workflow observable: log node inputs/outputs at each stage.
- Prefer schema-constrained JSON outputs for reliability.
- Productize automations by templating credentials, prompts, and outputs.
