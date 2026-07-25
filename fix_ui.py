import re
path = r"C:\Users\Imman\Kiwi_Bot_model\dashboard.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()
# 1. Remove the streamlit_autorefresh import and call
content = re.sub(r'\n\s*import streamlit_autorefresh\n', '\n', content)
content = re.sub(r'\s*streamlit_autorefresh\.st_autorefresh\([^)]+\)\n', '\n', content)
# 2. Remove the spinner around get_data() in main() - replace with clean call
content = content.replace(
    '    with st.spinner("Loading dashboard..."):\n        data = get_data()',
    '    data = get_data()'
)
# 3. Add a refresh button inside render_status_bar
# Find the status bar function and add a refresh button in the cols
old_status_line = 'with cols[1]:\n        st.markdown(f'
new_status_line = 'with cols[1]:\n        if st.button("Refresh", key="statusbar_refresh", use_container_width=True):\n            st.rerun()\n        st.markdown(f'
content = content.replace(old_status_line, new_status_line, 1)
with open(path, "w", encoding="utf-8") as f:
    f.write(content)
# Verify
has_autorefresh = "streamlit_autorefresh" in content
has_refresh_btn = 'statusbar_refresh' in content
print(f"Auto-refresh removed: {not has_autorefresh}")
print(f"Refresh button added: {has_refresh_btn}")
