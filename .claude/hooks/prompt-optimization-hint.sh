#!/bin/bash
# UserPromptSubmit hook: append optimization hint when 8+ tool calls detected.
# Skips exploratory prompts (questions, research, investigation).

set -euo pipefail

INPUT=$(cat)

PROMPT=$(echo "$INPUT" | jq -r '.prompt // ""')
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // ""')

# Skip if no transcript yet (first prompt in session)
if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
  exit 0
fi

# Skip exploratory prompts — questions, research, investigation
LOWER_PROMPT=$(echo "$PROMPT" | tr '[:upper:]' '[:lower:]')
if echo "$LOWER_PROMPT" | grep -qiE '^\s*(what|where|how|why|who|can you explain|show me|tell me|look at|explore|investigate|research|understand|find out|describe|walk me through|help me understand)'; then
  exit 0
fi

# Count tool_use blocks in the transcript
TOOL_CALLS=$(grep -c '"type":\s*"tool_use"' "$TRANSCRIPT_PATH" 2>/dev/null || echo "0")

if [ "$TOOL_CALLS" -lt 8 ]; then
  exit 0
fi

# Pick a hint category based on tool call count mod 3 for variety
HINT_INDEX=$(( TOOL_CALLS % 3 ))

case $HINT_INDEX in
  0)
    HINT="Optimization hint: Consider extracting repeated multi-step sequences into a reusable Claude Code skill (/skill) to reduce future tool call overhead."
    ;;
  1)
    HINT="Optimization hint: If you're re-discovering the same project context each session, save key findings to CLAUDE.md or use /memory to persist patterns for instant recall."
    ;;
  2)
    HINT="Optimization hint: Batch independent tool calls into parallel executions and use the Task agent for multi-file searches instead of sequential grep/glob to cut round-trips."
    ;;
esac

echo "$HINT"
exit 0
