# Report Page Pagination, Filtering, and API Name Display

- [ ] Task 1: Add filter controls (Date + API)
    - 1.1: In `render_report_page()`, after loading `history`, extract unique API names from the list to populate the API filter dropdown.
    - 1.2: Render a compact filter row using `st.columns`: a `st.date_input` for date filter (default `None`) and a `st.selectbox` for API filter (options: `["All"] + all_apis`).
    - 1.3: Add a "Clear Filters" button that resets both filter session state keys and resets page to 1.
    - 1.4: Apply filters in Python to produce `filtered_history`:
        - Date filter: match `entry['timestamp'][:10]` against selected date string.
        - API filter: match `entry['api_name']` against selected API (skip if "All").
        - Preserve the original order (already timestamp DESC from DB); do NOT re-sort after filtering.
    - 1.5: If `filtered_history` is empty, show `st.info("No reports match the current filters.")` and return early.

- [ ] Task 2: Add pagination controls and logic
    - 2.1: Initialize session state keys: `report_page` (default 1), `report_page_size` (default 10).
    - 2.2: Detect filter changes: if either filter value differs from previous render, reset `report_page` to 1.
    - 2.3: Render a stats + page-size row below filters: display "Showing X–Y of Z reports" and a `st.selectbox` for page size (`[10, 20]`). Changing page size resets `report_page` to 1.
    - 2.4: Compute `total_pages`, slice `filtered_history` to get `page_history`.
    - 2.5: Render Prev / Next pagination buttons at the bottom of the report list using `st.columns`.

- [ ] Task 3: Update expander label to include API name
    - 3.1: In the label construction block, read `api_name = entry.get('api_name') or 'Unknown'`.
    - 3.2: Append `- API: {api_name}` to both the running label and the completed label strings.

- [ ] Task 4: Loop over `page_history` instead of `history`
    - 4.1: Change `for i, entry in enumerate(history):` to `for i, entry in enumerate(page_history):`.
    - 4.2: Verify that all per-entry keys (`btn_del_`, `hist_tbl_`, etc.) remain unique — they already use `entry_id` so no changes needed.
