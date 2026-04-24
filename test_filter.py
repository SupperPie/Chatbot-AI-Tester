import pandas as pd
from app.ui.components.category_selector import get_category_ids_with_children
from app.ui.testcases import filter_test_cases

df = pd.DataFrame([
    {'id': 'TC0001', 'category_id': 'root'},
    {'id': 'TC0002', 'category_id': 'cat_7bbbb089'}
])

print("Category IDs for cat_7bbbb089:", get_category_ids_with_children('cat_7bbbb089'))
filtered = filter_test_cases(df, category_id='cat_7bbbb089')
print("Filtered count:", len(filtered))
