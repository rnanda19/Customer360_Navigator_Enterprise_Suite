# BP6 - GenAI Resolution Assistant - notebooks

**CLOSED.** All 6 gates + Gate 7 executive rollup real-run confirmed end to end.

CFPB + Banking77 (Banking77 is the sole real narrative-text source - CFPB's real extract carries no complaint narrative column). Retrieval-grounded generation, not a classifier - no `target_definition` gate.

Gate 3 champion retrieval strategy: **taxonomy_bucket_match** (real coverage 0.333). Gate 5 makes the suite's only live external API call, to **Google Gemini** (free tier) - every generated recommendation is grounded in cited real evidence IDs and routes to **PENDING_HUMAN_REVIEW** before use (human-in-the-loop governance guardrail, never auto-applied).

Gate 6 ships a mandatory FastAPI resolution service (`bp6_resolution_service.py`, port 8006) per the Master Plan's own governance requirement for this BP.
