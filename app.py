"""Streamlit chat UI for Sodhnus, on the offline rules backend and the committed data snapshot.

streamlit run app.py
"""

import streamlit as st

import brand
from sodhnus import assistant
from sodhnus.config import Settings
from sodhnus.data import load

brand.page("sodhnus")

EXAMPLES = [
    "How unusual was the rain in Kathmandu on असोज १२, 2081?",
    "२०८१ असोज १२ मा कहाँ सबैभन्दा धेरै पानी पर्यो?",
    "Melamchi rainfall on 15 June 2021",
    "Dhankuta monsoon total 2014",
    "bholi ktm ma pani parchha ki?",
]


@st.cache_resource
def gold():
    return load(Settings.from_env().gold)


g = gold()
with st.sidebar:
    st.header("Try a question")
    picked = None
    for q in EXAMPLES:
        if st.button(q, width="stretch"):
            picked = q
    st.divider()
    st.caption(
        f"Answers come only from Barsha's rainfall tables (data through {g.latest_day.isoformat()}). "
        "Runs on the offline rules backend: the same five tools and number checker as the Bedrock path. "
        "It refuses to forecast."
    )


st.session_state.setdefault("history", [])
for role, text in st.session_state.history:
    with st.chat_message(role, avatar=brand.avatar(role, "sodhnus")):
        st.markdown(text)

question = st.chat_input("Ask how much it rained, where, and how unusual it was") or picked
if question:
    st.chat_message("user", avatar=brand.avatar("user", "sodhnus")).markdown(question)
    a = assistant.ask(question, g, backend="rules")
    with st.chat_message("assistant", avatar=brand.avatar("assistant", "sodhnus")):
        st.markdown(a.text)
    st.session_state.history += [("user", question), ("assistant", a.text)]

brand.footer()
