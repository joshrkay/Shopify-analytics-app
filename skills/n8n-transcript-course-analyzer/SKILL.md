---
name: n8n-transcript-course-analyzer
description: Build, troubleshoot, and extend n8n workflows that ingest full YouTube transcripts and convert long-form course content into structured notes, key points, action items, and reusable workflow patterns. Use when tasks involve (1) extracting transcript text from a YouTube video, (2) chunking and summarizing long transcripts, (3) analyzing n8n/automation course content, or (4) producing implementation-ready workflow plans from tutorial videos.
---

# n8n Transcript Course Analyzer

## Overview
Use this skill to turn a YouTube course into an end-to-end n8n knowledge pipeline: fetch transcript, normalize text, split into chunks, summarize key points, and output actionable implementation plans.

Read resources in this order:
1. `references/transcript-sourcing.md` for reliable transcript ingestion methods.
2. `references/n8n-course-2GZ2SNXWK-c-key-points.md` for the analyzed course breakdown.
3. `assets/workflows/youtube-transcript-breakdown.json` for a ready-to-import n8n template.

## Workflow Decision Tree
- If transcript is directly accessible from a transcript provider endpoint, use **Path A (Direct Pull)**.
- If direct transcript pull fails but video metadata is available, use **Path B (Fallback Provider + HTML extraction)**.
- If no transcript is available, use **Path C (ASR fallback)** and mark output as machine-transcribed.

## Path A — Direct Pull
1. Start with `Manual Trigger` or `Webhook` input (`video_url`, `video_id`, `analysis_goal`).
2. Use `HTTP Request` to call transcript source.
3. Normalize rows into `[start, duration, text]` records.
4. Use `Code` node to join into full transcript and estimate token count.
5. Use `Text Splitter` / chunking logic at semantic boundaries (headings, timestamp breaks, sentence endings).
6. Send chunks to LLM node with strict JSON schema output:
   - `module`
   - `concepts`
   - `n8n_nodes_mentioned`
   - `business_use_case`
   - `implementation_notes`
7. Aggregate chunk summaries into final synthesis:
   - executive summary
   - key workflows taught
   - monetizable services
   - implementation checklist

## Path B — Fallback Provider + HTML Extraction
1. Resolve `video_id` from URL in a `Code` node.
2. Request fallback transcript page (example pattern in references file).
3. Extract transcript blocks with `HTML Extract` or regex in `Code`.
4. Clean artifacts (timestamps, duplicate whitespace, UI text).
5. Continue with chunking and synthesis from Path A.

## Path C — ASR Fallback
1. Download audio (or use existing audio URL).
2. Transcribe with speech-to-text provider.
3. Add confidence metadata and clear disclaimer (`source=asr`).
4. Continue through same chunk/analyze/synthesize pipeline.

## Output Contract
Return a JSON object with:
- `video_title`
- `summary`
- `key_points` (array)
- `workflow_patterns` (array of `{name, n8n_nodes, purpose, monetization_angle}`)
- `action_plan_7_days`
- `risks_and_gaps`
- `transcript_source`

## Quality Rules
- Preserve original meaning; do not invent claims not grounded in transcript.
- Use timestamps when available for each major takeaway.
- Separate beginner setup steps from advanced agent orchestration steps.
- Flag all advice that depends on external credentials, pricing, or API limits.

## Troubleshooting
- Empty transcript response: rotate provider or switch to ASR fallback.
- Over-token transcript: summarize per chunk, then recursively summarize summaries.
- Poor extraction quality: remove boilerplate lines before chunking.
- Inconsistent outputs: enforce JSON schema and retry with deterministic settings.
