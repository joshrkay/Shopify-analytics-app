# Transcript Sourcing for YouTube Workflows

## Goal
Provide reliable options for obtaining complete transcript text in n8n.

## Method 1: Direct transcript provider pull (fastest)
1. Input: `video_url` or `video_id`.
2. Request a transcript provider endpoint that returns text blocks.
3. Parse into records: `[{start, duration, text}]`.
4. Join records into full transcript and preserve timestamps.

## Method 2: Transcript webpage extraction (fallback)
1. Pull transcript webpage with `HTTP Request`.
2. Use `HTML Extract` (or `Code` node regex) to extract transcript lines.
3. Remove navigation/footer text.
4. Validate quality with minimum length threshold before analysis.

## Method 3: Speech-to-text (last resort)
1. Obtain audio stream or downloaded audio file.
2. Send to ASR provider.
3. Capture confidence metrics and label output `machine_transcribed=true`.

## Validation Checklist
- Confirm transcript length is plausible for the video duration.
- Confirm text is in expected language.
- Confirm at least 1 timestamp per chunk if available.
- Reject transcript if too sparse (e.g., mostly boilerplate lines).

## Normalization Pattern (Code Node)
- Trim whitespace
- Collapse repeated line breaks
- De-duplicate near-identical adjacent lines
- Preserve semantic separators at timestamp boundaries
