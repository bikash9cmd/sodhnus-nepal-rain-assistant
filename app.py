"""Streamlit chat UI for Sodhnus, on the offline rules backend and the committed data snapshot.

streamlit run app.py
"""

import streamlit as st

from sodhnus import assistant
from sodhnus.config import Settings
from sodhnus.data import load

st.set_page_config(page_title="Sodhnus", page_icon="🌧️", layout="centered")

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
    show_trace = st.toggle("Show tool calls and number checks", value=False)
    st.caption(
        f"Answers come only from Barsha's rainfall tables (data through {g.latest_day.isoformat()}). "
        "Runs on the offline rules backend: the same five tools and number checker as the Bedrock path. "
        "It refuses to forecast."
    )

st.title("Sodhnus (सोध्नुस्)")
st.caption("Rainfall questions about Nepal, answered only from verified data. English, Nepali or romanised Nepali.")

st.session_state.setdefault("history", [])
for role, text, extra in st.session_state.history:
    with st.chat_message(role):
        st.markdown(text)
        if extra and show_trace:
            with st.expander("How it answered"):
                st.json(extra)

question = st.chat_input("Ask how much it rained, where, and how unusual it was") or picked
if question:
    st.chat_message("user").markdown(question)
    a = assistant.ask(question, g, backend="rules")
    trace = {
        k: v for k, v in a.record().items() if k in ("tool_calls", "tool_results", "checked", "problems", "refusal")
    }
    with st.chat_message("assistant"):
        st.markdown(a.text)
        if show_trace:
            with st.expander("How it answered", expanded=True):
                st.json(trace)
    st.session_state.history += [("user", question, None), ("assistant", a.text, trace)]
