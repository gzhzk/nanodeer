---
name: office_artifacts
description: Produce or inspect DOCX, XLSX, and PPTX deliverables from user content.
disable-model-invocation: true
compatibility: office_artifact read_file ls read_image
---

# Office artifact workflow

1. Inspect `/uploads` and read the supplied source material before drafting.
2. Preserve names, numbers, dates, hierarchy, and requested language. Do not invent missing data.
3. Choose the smallest suitable format:
   - DOCX for prose, briefs, letters, and meeting notes;
   - XLSX for tabular data and calculations;
   - PPTX for concise slide narratives.
4. Call `office_artifact(action="create")` with structured content and write the result to
   `/outputs` using the matching extension.
5. Call `office_artifact(action="inspect")` on the result before finishing. Report its canonical
   output path and any formatting limitations.

Basic generation prioritizes correct, portable content over elaborate templates. If exact brand
layout or visual design is required and no template was supplied, use `wait` only when guessing
would create material rework.
