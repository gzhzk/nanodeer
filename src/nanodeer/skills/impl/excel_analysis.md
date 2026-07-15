---
name: excel_analysis
description: Inspect spreadsheet data, calculate requested metrics, and create a clean XLSX output.
disable-model-invocation: true
compatibility: office_artifact read_file write_file bash
---

# Spreadsheet workflow

1. Use `office_artifact(action="inspect")` to extract workbook values. For CSV or JSON inputs,
   use `read_file` instead.
2. Confirm headers, units, missing values, date meaning, and requested calculation before deriving
   metrics. Use `bash` only when code execution materially simplifies a larger calculation.
3. Keep source values separate from derived columns. Never silently coerce invalid data to zero.
4. Create the final workbook with `office_artifact(action="create", data=...)` under `/outputs`.
5. Inspect the generated workbook once and summarize formulas or assumptions in the response.
