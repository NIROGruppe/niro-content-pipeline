import streamlit as st
from shared import inject_css

st.set_page_config(page_title="Test", page_icon="🔒", layout="wide")
inject_css()

# ─── PASSWORD GATE ───────────────────────────────────────────────────────────

def check_password():
    """Returns True if the user entered the correct password."""
    if "test_authenticated" not in st.session_state:
        st.session_state["test_authenticated"] = False

    if st.session_state["test_authenticated"]:
        return True

    st.markdown("""
    <div style="text-align:center; padding: 80px 0 20px 0;">
        <div style="font-size:48px;">🔒</div>
        <h2>Zugang geschützt</h2>
    </div>
    """, unsafe_allow_html=True)

    password = st.text_input("Passwort", type="password", key="test_pw_input")
    if st.button("Login", use_container_width=True, type="primary"):
        try:
            correct_pw = st.secrets["TEST_PAGE_PASSWORD"]
        except Exception:
            import os
            correct_pw = os.getenv("TEST_PAGE_PASSWORD", "")

        if password == correct_pw:
            st.session_state["test_authenticated"] = True
            st.rerun()
        else:
            st.error("Falsches Passwort.")

    return False


if not check_password():
    st.stop()

# ─── AUTHENTICATED CONTENT ──────────────────────────────────────────────────

st.markdown("# 🔒 Test")
st.markdown("---")

st.info("Polymarket Trading Bot kommt hier hin.")
