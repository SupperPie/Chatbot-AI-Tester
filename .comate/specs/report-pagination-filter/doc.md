# Report Page Pagination, Filtering, and API Name Display

## Background
The Test Report page (`app/ui/report.py`) currently loads and renders all history entries in one flat list. As the number of reports grows, the page becomes slow and hard to navigate. The data model (`TestHistory`) already stores `api_name`, so no backend schema changes are needed.

## Requirements
1. **Pagination**: Support 10 or 20 entries per page, with page navigation controls.
2. **Date filter**: Filter entries by a specific date (calendar date picker).
3. **API filter**: Filter entries by API name (dropdown from available values in history).
4. **Expander label**: Append API name to the existing label format.

## Architecture & Technical Approach

### Data Flow
- `service.get_all(include_results=False)` → `history` (full list, summaries only)
- Apply date + API filters in Python → `filtered_history`
- Slice by page → `page_history`
- Render expander per entry in `page_history`

### 1. Pagination
Add session state keys:
- `report_page` (int, default 1)
- `report_page_size` (int, default 10)

After filtering, slice:
```python
total = len(filtered_history)
total_pages = max(1, math.ceil(total / page_size))
start = (page - 1) * page_size
end = start + page_size
page_history = filtered_history[start:end]
```

Render pagination controls using `st.columns` + `st.selectbox` for page size, and `st.number_input` or `st.select_slider` for page number.

### 2. Filters
Add two controls in a compact row at the top:

**Date filter** (`st.date_input`, optional / clearable via a checkbox or None default):
```python
filter_date = st.date_input("Date", value=None, key="rpt_filter_date")
```
If set, keep only entries where `entry['timestamp']` starts with the selected date string (`YYYY-MM-DD`).

**API filter** (`st.selectbox` with "All" option):
```python
all_apis = sorted(set(e.get('api_name', '') for e in history if e.get('api_name')))
api_options = ["All"] + all_apis
filter_api = st.selectbox("API", api_options, key="rpt_filter_api")
```
If not "All", keep only entries where `entry['api_name'] == filter_api`.

Reset page to 1 whenever filters change (detect via session state comparison).

### 3. Expander Label
Current:
```python
label = f"{entry.get('timestamp')} - Pass Rate: {pass_rate:.1f}% ({passed_count}/{total_count})"
```
Updated:
```python
api_name = entry.get('api_name') or 'Unknown'
label = f"{entry.get('timestamp')} - Pass Rate: {pass_rate:.1f}% ({passed_count}/{total_count}) - API: {api_name}"
```

### 4. Layout
```
[Filter row]   Date: [date picker]    API: [dropdown]    [Clear Filters button]
[Stats row]    Showing X–Y of Z reports    Per page: [10 | 20]
[Report list]  (expanders, paginated)
[Pagination]   [< Prev]  Page 3 of 12  [Next >]
```

## Affected Files
- `app/ui/report.py` — All changes (filters, pagination, label update)
- No changes needed to `app/services/history_service.py` (api_name already returned)

## Boundary Conditions
- If `filtered_history` is empty, show "No reports match the current filters."
- Changing page size resets to page 1.
- Changing filter resets to page 1.
- `api_name` may be `None` for older records; treat as `"Unknown"`.

## Expected Outcomes
- Page loads quickly because only summary data is fetched upfront.
- Users can filter by date/API and paginate through large sets of reports.
- Expander header clearly shows time, pass rate, and API name.
