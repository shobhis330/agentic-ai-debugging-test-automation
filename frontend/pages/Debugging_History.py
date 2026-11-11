
import json
import pandas as pd
import streamlit as st

from core.debugging_history import (
    get_history,
    get_history_summary,
    delete_history_entry,
    clear_history
)

st.set_page_config(
    page_title="Debugging History",
    page_icon="📚",
    layout="wide"
)

st.title("📚 Debugging History")
st.caption("View and manage your previous debugging sessions.")

history = get_history()
summary = get_history_summary()

# Summary cards
col1, col2, col3 = st.columns(3)

col1.metric("Total Sessions", summary["total"])
col2.metric("Successful Sessions", summary["successful"])
col3.metric("Failed Sessions", summary["failed"])

st.divider()

if not history:
    st.info(
        "No debugging history is available yet. "
        "Records will appear here when debugging sessions are saved."
    )
else:
    # Search and filter
    search_col, filter_col = st.columns(2)

    with search_col:
        search_text = st.text_input(
            "Search by file name or issue",
            placeholder="Enter a file name or keyword"
        )

    with filter_col:
        status_options = ["All", "Success", "Fixed", "Passed", "Failed", "Error"]
        selected_status = st.selectbox("Filter by status", status_options)

    filtered_history = []

    for item in history:
        file_name = item.get("file_name", "")
        issue = item.get("issue", "")
        status = item.get("status", "")

        matches_search = (
            search_text.lower() in file_name.lower()
            or search_text.lower() in issue.lower()
        )

        matches_status = (
            selected_status == "All"
            or status.lower() == selected_status.lower()
        )

        if matches_search and matches_status:
            filtered_history.append(item)

    st.subheader(f"Sessions ({len(filtered_history)})")

    # Table
    table_data = []

    for item in filtered_history:
        table_data.append({
            "Date": item.get("timestamp", ""),
            "File": item.get("file_name", ""),
            "Status": item.get("status", ""),
            "Issue": item.get("issue", ""),
            "Tests": item.get("test_summary", "")
        })

    if table_data:
        st.dataframe(
            pd.DataFrame(table_data),
            use_container_width=True,
            hide_index=True
        )

        csv_data = pd.DataFrame(table_data).to_csv(index=False)

        st.download_button(
            "⬇️ Download History CSV",
            data=csv_data,
            file_name="debugging_history.csv",
            mime="text/csv"
        )

    st.divider()
    st.subheader("Session Details")

    for item in filtered_history:
        title = (
            f"{item.get('file_name', 'Unknown file')} | "
            f"{item.get('timestamp', '')} | "
            f"{item.get('status', 'Unknown')}"
        )

        with st.expander(title):
            st.write("**Issue:**", item.get("issue") or "Not provided")
            st.write("**Test Summary:**", item.get("test_summary") or "Not provided")
            st.write("**Details:**", item.get("details") or "Not provided")

            original_code = item.get("original_code", "")
            corrected_code = item.get("corrected_code", "")

            if original_code:
                st.markdown("**Original Code**")
                st.code(original_code, language="python")

            if corrected_code:
                st.markdown("**Corrected Code**")
                st.code(corrected_code, language="python")

            if st.button(
                "Delete this session",
                key=f"delete_{item.get('id')}"
            ):
                delete_history_entry(item.get("id"))
                st.success("Session deleted.")
                st.rerun()

    st.divider()

    if st.button("🗑️ Clear All History", type="secondary"):
        st.session_state["confirm_clear_history"] = True

    if st.session_state.get("confirm_clear_history", False):
        st.warning("Are you sure you want to delete all debugging history?")

        confirm_col, cancel_col = st.columns(2)

        with confirm_col:
            if st.button("Yes, delete all"):
                clear_history()
                st.session_state["confirm_clear_history"] = False
                st.success("All history deleted.")
                st.rerun()

        with cancel_col:
            if st.button("Cancel"):
                st.session_state["confirm_clear_history"] = False
                st.rerun()
