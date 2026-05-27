# UI Layout & Move Range Functionality Fixes

- [x] Task 1: Fix Move Range Functionality
    - 1.1: Modify `app/ui/testcases.py` in the `move_to_category_clicked` block.
    - 1.2: Check if any rows are selected via checkbox.
    - 1.3: If no checkboxes are selected, check if `filter_id_from` or `filter_id_to` are provided in the session state.
    - 1.4: If the ID range is provided, use `edited_df` to get the list of IDs to move.
    - 1.5: If neither are provided, show the warning message.

- [x] Task 2: Fix Category Widget Title Layout
    - 2.1: Modify `app/ui/components/category_widget.py`.
    - 2.2: Replace `st.markdown("### 📂 Category")` with a raw HTML tag (`<h3>`) using `unsafe_allow_html=True`.
    - 2.3: Add inline CSS `white-space: nowrap;` and reset margins/padding to prevent wrapping and remove the injected anchor link.
