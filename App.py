import streamlit as st
import pandas as pd
import requests
from sqlalchemy import create_engine
import base64

# --- CONFIG: API endpoints (ideally on a separate sheet)---
EXTRACT_URL = "https://plankton-app-qajlk.ondigitalocean.app/extraction_api"
MATCH_URL   = "https://endeavor-interview-api-gzwki.ondigitalocean.app/match/batch"

# --- PAGE SETUP ---
st.set_page_config(
    page_title="Sales Order Entry Automation",
    page_icon="🏭",
    layout="wide"
)
tabs = st.tabs(["📤 Upload", "🔍 Extract", "🔗 Match"])

# --- 1) UPLOAD TAB ---
with tabs[0]:
    left, right = st.columns([2, 1])

    # PDF upload & preview
    uploaded = left.file_uploader("Drag PDF here or click to upload", type="pdf")
    if uploaded:
        pdf_bytes = uploaded.read()
        b64 = base64.b64encode(pdf_bytes).decode("utf-8")
        iframe = f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="600px"></iframe>'
        st.components.v1.html(iframe, height=600)
        st.session_state.pdf_bytes = pdf_bytes
        st.session_state.uploaded_filename = uploaded.name
    # Purchase Order Info form
    right.markdown("### Purchase Order Information")
    if "po_fields" not in st.session_state or not isinstance(st.session_state.po_fields, dict):
        st.session_state.po_fields = {
            "Request ID": "",
            "Delivery Address": "",
            "PO Date": "",
            "PO Number": ""
        }

    def add_field():
        st.session_state.po_fields[f"Field {len(st.session_state.po_fields) + 1}"] = ""

    def clear_fields():
        st.session_state.po_fields.clear()

    # Render each input
    for field in list(st.session_state.po_fields.keys()):
        st.session_state.po_fields[field] = right.text_input(
            label=field,
            value=st.session_state.po_fields[field]
        )

    right.button("➕ Add Extract Field", on_click=add_field)
    right.button("🗑️ Clear All Fields", on_click=clear_fields)

# --- 2) EXTRACT TAB ---
with tabs[1]:
    st.markdown("### Extracted Line Items")

    if st.session_state.get("pdf_bytes") and "uploaded_filename" in st.session_state:
        if st.button("▶️ Generate Extraction"):
            files = {
                "file": (st.session_state.uploaded_filename, st.session_state.pdf_bytes, "application/pdf")
        
            }
            try:
                res = requests.post(EXTRACT_URL, files=files)
                res.raise_for_status()
                items = res.json()
                st.session_state.df = pd.DataFrame(items)
                st.success("Extraction successful!")
            except Exception as e:
                st.error(f"Extraction failed: {e}")

    if "df" in st.session_state:
        st.session_state.df = st.data_editor(
            st.session_state.df,
            num_rows="dynamic",
            use_container_width=True
        )

# --- 3) MATCH & SAVE TAB ---
with tabs[2]:
    st.markdown("### Match Line Items & Persist")

    if "df" not in st.session_state:
        st.info("Run the **Generate Extraction** step first.")
    else:
        df = st.session_state.df.copy()
        # Ensure a column exists for matches
        if "Matched Item" not in df.columns:
            df["Matched Item"] = ""

        # Generate matches from the API
        if st.button("🔗 Generate Mapping"):
            # Use the correct column for descriptions
            desc_col = "Request Item" if "Request Item" in df.columns else df.columns[0]
            desc_list = df[desc_col].astype(str).tolist()
            payload = {"queries": desc_list}
            params = {"limit": 5}
            try:
                res = requests.post(MATCH_URL, json=payload, params=params)
                res.raise_for_status()
                matches_dict = res.json()
                # Order matches to correspond to input order
                match_lists = [matches_dict.get(desc, []) for desc in desc_list]
                st.session_state.matches = match_lists
                st.success("Matching complete!")
            except Exception as e:
                st.error(f"Matching failed: {e}")

        # Show dropdowns for each row to select match
        if "matches" in st.session_state:
            for i, options in enumerate(st.session_state.matches):
                # For fallback if no matches, use empty string
                df.at[i, "Matched Item"] = st.selectbox(
                    f"Match for row {i+1}",
                    options if options else [""],
                    key=f"match_{i}"
                )

        # Save to SQLite
        if st.button("✅ Confirm & Save to SQLite"):
            try:
                engine = create_engine("sqlite:///orders.db", echo=False)
                df.to_sql("order_matches", con=engine, if_exists="append", index=False)
                st.success("Saved to `orders.db` ➡️ table `order_matches`")
                preview = pd.read_sql(
                    "SELECT * FROM order_matches ORDER BY rowid DESC LIMIT 5",
                    con=engine
                )
                st.dataframe(preview, use_container_width=True)
            except Exception as e:
                st.error(f"Saving to database failed: {e}")

        # CSV download fallback
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download CSV",
            data=csv_bytes,
            file_name="order_matches.csv",
            mime="text/csv"
        )

        # keep updated DF in session
        st.session_state.df = df
