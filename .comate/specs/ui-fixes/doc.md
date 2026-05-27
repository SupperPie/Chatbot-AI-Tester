# UI Layout & Move Range Functionality

## Requirements
1. **Move Range Functionality**: Currently, the "From ID" and "To ID" inputs only apply to the "Run Range" button. When users try to use the "Move" button with an ID range (without selecting checkboxes), it prompts "请先选择要移动的测试用例". The user wants the Move button to support the same ID range functionality as the Run Range button.
2. **Category Widget Title Layout**: In the Category widget, the folder icon "📂" and the text "Category" sometimes break into separate lines due to width constraints. Additionally, Streamlit automatically injects an anchor link icon (`stHeaderActionElements`) next to markdown headers, which also wraps to the next line and is unnecessary. The user wants the icon and text to stay on the same line and the anchor link icon removed.

## Technical Approach
### 1. Move Range Functionality
- **File**: `app/ui/testcases.py`
- **Location**: Inside `render_testcases_page()`, specifically the `elif move_to_category_clicked:` block.
- **Modification**: 
  - First, check if any rows are explicitly checked (`edited_df["Select"] == True`).
  - If no rows are selected, check if `filter_id_from` or `filter_id_to` are provided.
  - If the ID range is provided, use the entire `edited_df` (which is already filtered by the range) as the set of cases to move.
  - If neither checkboxes are selected nor ID range is provided, show the warning "请先选择要移动的测试用例".

### 2. Category Widget Title Layout
- **File**: `app/ui/components/category_widget.py`
- **Location**: Inside `render_category_widget()`, the `col_title` block.
- **Modification**: 
  - Replace `st.markdown("### 📂 Category")` with raw HTML to prevent Streamlit from injecting the header anchor link.
  - Use inline CSS `white-space: nowrap;` to ensure the folder icon and the text "Category" remain on the same line.
  - Example: `st.markdown('<h3 style="white-space: nowrap; margin-bottom: 0; margin-top: 0; padding-top: 0;">📂 Category</h3>', unsafe_allow_html=True)`

## Affected Files
- `app/ui/testcases.py`
- `app/ui/components/category_widget.py`

## Expected Outcomes
- Users can fill in "From ID" and "To ID" and directly click "Move" to move the filtered test cases.
- The Category title "📂 Category" stays neatly on a single line and no longer shows the superfluous anchor link.