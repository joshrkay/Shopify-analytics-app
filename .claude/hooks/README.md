# Claude Code Hooks

## prompt-optimization-hint.sh (UserPromptSubmit)

A global UserPromptSubmit hook that appends a one-sentence optimization hint when the session transcript contains 8+ tool calls.

### Behavior

- Reads the session transcript from the path provided on stdin
- Counts `tool_use` blocks in the transcript
- If 8+ tool calls are detected, appends one optimization hint (rotating between three categories):
  - **Reusable skill**: Extract repeated sequences into a Claude Code skill
  - **Memory pattern**: Persist project context to CLAUDE.md or /memory
  - **Workflow fix**: Batch independent tool calls in parallel, use Task agent
- **Skips** exploratory prompts (questions, research, investigation)

### Installation

Copy `prompt-optimization-hint.sh` to `~/.claude/` and add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/prompt-optimization-hint.sh",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```
