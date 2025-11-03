# Private Search Research Assistant

This repository documents a self-hosted search assistant that aggregates results through SearXNG, removes duplicate links, extracts useful page content, and returns short cited summaries.

## Domain
Research / Search

## Overview
Built to reduce research friction without hiding the underlying sources.

## Methodology
1. Started from the client's research workflow and targeted repeated pain points such as too many tabs, repeated links, and slow first-pass reading.
2. Used SearXNG to aggregate results from multiple search sources so the team was not tied to a single commercial search experience.
3. Added deduplication and candidate filtering before summarization so the assistant surfaced fewer but more useful links.
4. Extracted content from selected pages and asked Gemini Flash to write short summaries that still preserved source visibility.
5. Kept citations and links central to the output because the goal was to support research, not replace it with an opaque answer engine.
6. Introduced Redis caching so repeated or similar queries returned faster and felt more practical in day-to-day usage.

## Skills
- SearXNG
- Python
- Gemini Flash
- Redis
- FastAPI
- Content Extraction
- Deduplication
- Citation-Aware Summarization

## Source
This README was generated from the portfolio project data used by `/Users/harshitpanikar/Documents/Test_Projs/harshitpaunikar1.github.io/index.html`.
