# Private Search Research Assistant Diagrams

Generated on 2026-04-26T04:29:37Z from README narrative plus project blueprint requirements.

## Search aggregation pipeline

```mermaid
flowchart TD
    N1["Step 1\nStarted from the client's research workflow and targeted repeated pain points such"]
    N2["Step 2\nUsed SearXNG to aggregate results from multiple search sources so the team was not"]
    N1 --> N2
    N3["Step 3\nAdded deduplication and candidate filtering before summarization so the assistant "]
    N2 --> N3
    N4["Step 4\nExtracted content from selected pages and asked Gemini Flash to write short summar"]
    N3 --> N4
    N5["Step 5\nKept citations and links central to the output because the goal was to support res"]
    N4 --> N5
```

## Deduplication + filtering flow

```mermaid
flowchart LR
    N1["Inputs\nLive yard-state entities such as docks, trailers, queues, and jockey availability"]
    N2["Decision Layer\nDeduplication + filtering flow"]
    N1 --> N2
    N3["User Surface\nAPI-facing integration surface described in the README"]
    N2 --> N3
    N4["Business Outcome\nCitation precision / grounding"]
    N3 --> N4
```

## Evidence Gap Map

```mermaid
flowchart LR
    N1["Present\nREADME, diagrams.md, local SVG assets"]
    N2["Missing\nSource code, screenshots, raw datasets"]
    N1 --> N2
    N3["Next Task\nReplace inferred notes with checked-in artifacts"]
    N2 --> N3
```
