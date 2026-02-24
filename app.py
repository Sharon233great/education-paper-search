# app.py
# 教育科技 & 高等教育 — 专业期刊搜索（含：近5年过滤 / Q1 近似 / 按引用排序 / 高频作者排行）
# 数据源：OpenAlex
import streamlit as st
import requests
from datetime import datetime
from collections import Counter

st.set_page_config(page_title="教育科技 & 高等教育 · 期刊搜索", layout="wide")
st.title("🎓 教育科技 & 高等教育 — 期刊搜索（专业版）")
st.markdown(
    "数据来源：OpenAlex（开放学术索引）。\n\n"
    "- 默认只看近 5 年（可修改）。\n"
    "- “只看 Q1（近似）”使用论文的 `citation_normalized_percentile >= 阈值` 作为近似标准。\n"
    "- 可按引用次数排序以看到影响力更高的论文。\n\n"
    "（建议注册 OpenAlex API Key 并填写以获得更稳定配额，参见 https://docs.openalex.org/ ）"
)

# ---------------- UI 控件 ----------------
keyword = st.text_input("请输入关键词（例如：AI in higher education）", value="educational technology")
max_results = st.slider("每次最多显示多少篇？", 5, 50, 15)
only_recent = st.checkbox("只看近 5 年论文（默认）", value=True)
recent_years = st.number_input("近 N 年（当勾选“只看近 5 年”时有效）", min_value=1, max_value=10, value=5)
only_q1 = st.checkbox("只看 Q1（近似：高被引论文）", value=False)
q1_threshold = st.slider("Q1 近似阈值（归一化引用百分位，越高越严格）", 50, 99, 75)
sort_by_citations = st.checkbox("按引用次数排序（从高到低）", value=True)
openalex_api_key = st.text_input("（可选）OpenAlex API Key（没有可留空）", type="password")

st.markdown("---")
st.caption("提示：OpenAlex 非必需 API Key，但有 key 会更稳定。")

# ---------------- helper functions ----------------
def openalex_search(query, per_page=15, api_key=None):
    """调用 OpenAlex /works API，返回 results 列表"""
    base = "https://api.openalex.org/works"
    params = {
        "search": query,
        "filter": "type:journal-article",
        "per-page": per_page,
        "sort": "publication_date:desc"
    }
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    resp = requests.get(base, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("results", [])

def looks_recent(publication_date_str, years):
    """判断 publication_date_str（YYYY-MM-DD 或 YYYY）是否在最近 years 年内"""
    if not publication_date_str:
        return False
    try:
        year = int(publication_date_str.split("-")[0])
    except Exception:
        return False
    this_year = datetime.utcnow().year
    return year >= (this_year - years + 1)

def reconstruct_abstract(inv_index):
    """尝试把 OpenAlex 的 inverted index 摘要重建成文本（若存在）"""
    try:
        toks = {}
        for token, positions in inv_index.items():
            for p in positions:
                toks[p] = token
        text = " ".join([toks[i] for i in sorted(toks.keys())])
        return text
    except Exception:
        return None

# ---------------- 搜索与展示 ----------------
if st.button("🔎 搜索"):
    if not keyword.strip():
        st.warning("请先输入关键词。")
    else:
        with st.spinner("正在从 OpenAlex 抓取并应用筛选（请稍候）..."):
            try:
                results = openalex_search(keyword, per_page=max_results, api_key=openalex_api_key or None)
            except Exception as e:
                st.error(f"调用 OpenAlex 出错：{e}")
                results = []

            if not results:
                st.info("未找到结果（或 API 限制导致未返回）。")
            else:
                # 过滤与去重
                filtered = []
                seen = set()
                for r in results:
                    doi = (r.get("ids") or {}).get("doi")
                    title = (r.get("title") or "").strip()
                    key = (doi or title)[:300]
                    if key in seen:
                        continue
                    seen.add(key)

                    # 近年过滤
                    pub_date = r.get("publication_date") or ""
                    if only_recent:
                        if not looks_recent(pub_date, recent_years):
                            continue

                    # Q1 近似过滤：使用 citation_normalized_percentile（若无则排除）
                    if only_q1:
                        cnp = r.get("citation_normalized_percentile")
                        try:
                            cnp_val = float(cnp) if cnp is not None else None
                        except Exception:
                            cnp_val = None
                        if cnp_val is None or cnp_val < q1_threshold:
                            continue

                    filtered.append(r)

                # 排序
                if sort_by_citations:
                    filtered.sort(key=lambda x: x.get("cited_by_count", 0), reverse=True)
                else:
                    filtered.sort(key=lambda x: x.get("publication_date") or "", reverse=True)

                st.success(f"抓取完成 — 原始返回 {len(results)} 条，筛选后 {len(filtered)} 条（去重后）")

                # 显示论文详情
                for r in filtered:
                    title = r.get("title") or "无标题"
                    pub_date = r.get("publication_date") or "未知"
                    journal = (r.get("primary_location") or {}).get("source", {}).get("display_name") \
                              or r.get("host_venue", {}).get("display_name") or "未知期刊"
                    citation = r.get("cited_by_count", 0)
                    cnp = r.get("citation_normalized_percentile", "N/A")
                    doi = (r.get("ids") or {}).get("doi")
                    url = (r.get("primary_location") or {}).get("landing_page_url") or r.get("id") or ""
                    authors_list = []
                    for a in r.get("authorships", [])[:10]:
                        # OpenAlex authorship object 有 "author" 或直接 display_name
                        if isinstance(a, dict):
                            au = a.get("author") or {}
                            name = au.get("display_name") or a.get("display_name")
                        else:
                            name = None
                        if name:
                            authors_list.append(name)
                    authors = ", ".join(authors_list) if authors_list else "未知作者"

                    st.markdown(f"### {title}")
                    st.markdown(f"📘 期刊：{journal}    📅 发表时间：{pub_date}")
                    st.markdown(f"👥 作者：{authors}")
                    st.markdown(f"📈 引用次数：{citation}    |    归一化引用百分位 (近似 Q1)：{cnp}")
                    if doi:
                        st.markdown(f"🔗 DOI: https://doi.org/{doi}")
                    if url:
                        st.markdown(f"[🔎 打开论文页面]({url})")
                    # 摘要（若存在 inverted index）
                    abstract_inv = r.get("abstract_inverted_index")
                    if abstract_inv:
                        text = reconstruct_abstract(abstract_inv)
                        if text:
                            st.write(text[:1000] + ("…" if len(text) > 1000 else ""))
                    # 横线分隔
                    st.markdown("---")

                # ===== 统计作者出现次数并显示排行榜 =====
                author_counter = Counter()
                for r in filtered:
                    for a in r.get("authorships", []):
                        if isinstance(a, dict):
                            au = a.get("author") or {}
                            name = au.get("display_name") or a.get("display_name")
                        else:
                            name = None
                        if name:
                            author_counter[name] += 1

                if author_counter:
                    st.markdown("## 📊 本次搜索 · 高频作者排行")
                    st.markdown("（按本次搜索结果中作者出现次数统计）")
                    for name, count in author_counter.most_common(20):
                        st.write(f"{name} — 出现 {count} 次")
                    st.markdown("---")

                # 可选：显示总体统计（比如总引用数等）
                total_citations = sum([r.get("cited_by_count", 0) for r in filtered])
                st.caption(f"筛选后论文数：{len(filtered)}，总引用次数：{total_citations}")

