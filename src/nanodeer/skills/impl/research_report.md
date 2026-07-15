---
name: research_report
description: Answer a research question with verified sources, explicit uncertainty, and citations.
disable-model-invocation: true
compatibility: web_search web_fetch read_file write_file edit_file
---

# Research report workflow

1. Restate the research question internally as concrete claims that need evidence.
2. Search broadly enough to identify primary or authoritative sources and competing explanations.
3. Fetch source pages before relying on them. Check author or institution, publication date,
   relevance, and whether the page actually supports the claim.
4. Distinguish evidence, inference, and unresolved uncertainty. For time-sensitive questions,
   state the date through which the answer was checked.
5. Write the result under `/outputs` when an artifact is requested. Put inline Markdown links next
   to supported claims and end with a compact source list only when it improves readability.

Never invent sources or citations. If a required source cannot be accessed, say exactly what is
missing and narrow the conclusion accordingly.
