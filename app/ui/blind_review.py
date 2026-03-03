import streamlit as st
import json
import os
import uuid
import pandas as pd
from datetime import datetime

BLIND_REVIEWS_FILE = "data/blind_reviews.json"

def load_reviews():
    if not os.path.exists(BLIND_REVIEWS_FILE):
        return []
    try:
        with open(BLIND_REVIEWS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_reviews(reviews):
    os.makedirs(os.path.dirname(BLIND_REVIEWS_FILE), exist_ok=True)
    with open(BLIND_REVIEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(reviews, f, indent=4, ensure_ascii=False)

def render_blind_review_page():
    st.title("🙈 Blind Review")
    st.markdown("Compare model outputs side-by-side without knowing the source.")
    
    reviews = load_reviews()
    
    # ----------------------
    # Sidebar: Session List
    # ----------------------
    # We can use the main sidebar or a column. Let's use a selectbox at top for simplicity in standard layout
    
    if not reviews:
        st.info("No review sessions found. Go to **Test Report** and export data to start a Blind Review.")
        return

    session_names = [r["name"] for r in reviews]
    # Reverse order to show newest first usually
    session_names.reverse()
    
    selected_session_name = st.selectbox("Select Review Session", options=session_names)
    
    # Find selected session data
    session_data = next((r for r in reviews if r["name"] == selected_session_name), None)
    
    if not session_data:
        st.error("Session data not found.")
        return

    # ----------------------
    # Statistics
    # ----------------------
    items = session_data.get("items", [])
    total_items = len(items)
    
    # Removed global statistics board per request
    
    # ----------------------
    # Review Cards (Pagination)
    # ----------------------
    ITEMS_PER_PAGE = 10
    
    if "blind_page_idx" not in st.session_state:
        st.session_state.blind_page_idx = 0
        
    page_idx = st.session_state.blind_page_idx
    start_idx = page_idx * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    
    current_items = items[start_idx:end_idx]
    
    # Pagination Controls
    col_prev, col_info, col_next = st.columns([1, 2, 1])
    with col_prev:
        if page_idx > 0:
            if st.button("⬅️ Previous", key="btn_blind_prev"):
                st.session_state.blind_page_idx -= 1
                st.rerun()
                
    with col_info:
        st.markdown(f"<div style='text-align: center'>Page {page_idx + 1} of {(total_items - 1) // ITEMS_PER_PAGE + 1}</div>", unsafe_allow_html=True)
        
    with col_next:
        if end_idx < total_items:
            if st.button("Next ➡️", key="btn_blind_next"):
                st.session_state.blind_page_idx += 1
                st.rerun()

    st.write("") # Spacer

    # Render Items
    for i, item in enumerate(current_items):
        real_idx = start_idx + i
        
        with st.container():
            main_col, stat_col = st.columns([4, 1.5])
            
            with main_col:
                # Card Styling
                st.markdown(f"""
                <div style="
                    border: 1px solid #ddd;
                    border-radius: 8px;
                    padding: 15px;
                    margin-bottom: 20px;
                    background-color: #f9f9f9;
                ">
                    <div style="font-weight: bold; margin-bottom: 10px; color: #555;">
                        CASE #{real_idx + 1}
                    </div>
                    <div style="font-size: 1.1em; margin-bottom: 15px; white-space: pre-wrap;">
                        {item.get('input', '')}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Options (Side by Side)
                options = item.get("options", {})
                opt_keys = sorted(options.keys())
                
                if not opt_keys:
                    st.warning("No options to compare.")
                    continue
                    
                cols = st.columns(len(opt_keys))
                
                for idx, opt_key in enumerate(opt_keys):
                    with cols[idx]:
                        st.info(f"Option {opt_key}")
                        st.markdown(f"""
                        <div style="
                            background: white;
                            padding: 10px;
                            border-radius: 5px;
                            border: 1px solid #eee;
                            min-height: 100px;
                            white-space: pre-wrap;
                            font-family: monospace;
                            font-size: 0.9em;
                        ">
                            {options[opt_key]}
                        </div>
                        """, unsafe_allow_html=True)

            with stat_col:
                st.markdown("### 📊 Statistics")
                
                # Migrate legacy vote format to tally format
                if "votes" not in item:
                    item["votes"] = {k: 0 for k in opt_keys}
                    if "vote" in item and item["vote"] in item["votes"]:
                        item["votes"][item["vote"]] += 1
                
                # Clean up legacy key if exists
                if "vote" in item:
                    del item["vote"]
                    
                # Display Stats
                for k in opt_keys:
                    count = item["votes"].get(k, 0)
                    st.metric(f"Votes for {k}", count)
                    
                st.divider()
                st.markdown("**Cast Vote**")
                
                # Buttons for voting
                for k in opt_keys:
                    if st.button(f"👍 Vote {k}", key=f"vote_{selected_session_name}_{real_idx}_{k}", use_container_width=True):
                         item["votes"][k] = item["votes"].get(k, 0) + 1
                         save_reviews(reviews)
                         st.rerun()

            st.divider()

    # Footer Pagination (Duplicate for ease)
    if total_items > ITEMS_PER_PAGE:
        st.caption(f"Page {page_idx + 1}")
