"""Prompt Library — 성공한 프롬프트를 검색/복사."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Prompt Library", page_icon="📚", layout="wide")
st.title("📚 Prompt Library")
st.caption("성공 프롬프트를 CLAP 임베딩으로 검색합니다. 비슷한 사운드를 찾고 싶을 때.")

try:
    from shared.prompt_library import PromptLibrary
    lib = PromptLibrary()
except Exception as e:
    st.error(f"프롬프트 라이브러리를 열 수 없습니다: {e}")
    st.caption("첫 성공 생성 후 자동으로 생성됩니다.")
    st.stop()

top = st.columns([4, 1])
q = top[0].text_input("검색어", placeholder="예: 8-bit coin pickup")
cat = top[1].selectbox("카테고리", [
    "", "sfx_ui", "sfx_reward", "sfx_impact", "sfx_ambient",
    "sfx_character", "sfx_notification", "bgm_loop", "bgm_stinger", "bgm_adaptive",
])

if q:
    results = lib.recommend(q, category=cat or None, k=10)
    if not results:
        st.info("일치하는 프롬프트가 없습니다.")
    for r in results:
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f"**{r['prompt']}**")
                st.caption(f"{r.get('category', '?')} · {r.get('model', '?')} · sim={r['similarity']:.2f} · score={r.get('score', 0):.2f}")
                ap = r.get("audio_path")
                if ap and Path(ap).exists():
                    st.audio(str(ap))
            with c2:
                if st.button("📋 Copy", key=f"copy_{r['id']}"):
                    st.code(r["prompt"])
                    st.caption("↑ 복사하세요")
else:
    st.caption("검색어를 입력하세요.")
