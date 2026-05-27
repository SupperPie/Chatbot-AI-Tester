# Report Page Pagination, Filtering, and API Name Display — Summary

## Changes Made
All changes are in `app/ui/report.py`.

### Filter Controls
- Added `import math` to the top.
- Extracted unique API names from `history` to build the API filter dropdown.
- Rendered a 3-column filter row: **date picker** | **API dropdown** | **Clear Filters** button.
- Applied filters via Python list comprehension — original timestamp-desc order is preserved.
- When no results match, shows `st.info("No reports match the current filters.")` and returns early.

### Pagination
- Session state keys: `report_page` (default 1), `report_page_size` (default 10).
- Filter-change detection resets page to 1 via a dynamic session state key per filter combination.
- Displayed "Showing X–Y of Z reports" caption with a per-page selector (10 / 20).
- Bottom pagination: ← Prev | Page N of M | Next → buttons.
- The `for` loop now iterates over `page_history` (the sliced list) instead of `history`.

### Expander Label
Updated both running and completed label strings:
- Running: `⏳ {timestamp} - Running... {started}/{total} - API: {api_name}`
- Completed: `{timestamp} - Pass Rate: X.X% (n/m) - API: {api_name}`
- Falls back to `'Unknown'` if `api_name` is `None` (older records).
