# app.py — 学术快搜（教育领域优先）
import streamlit as st
import requests
import feedparser
from urllib.parse import quote_plus
from dateutil import parser as dateparser
from datetime import datetime

st.set_page_config(page_title="教育领域学术快搜", layout="wide")
st.title("📚 教育领域学术快搜")
st.markdown("输入关键词，点“搜索”即可抓取最新教育领域论文（来自 arXiv + Crossref；可选 Semantic Scholar）。无需发送邮件，只在页面展示。")

# --- UI 设置 ---
keyword = st.text_input("关键词（示例：education, STEM education, pedagogy, teacher professional development）", value="education")
education_only = st.checkbox("只显示教育相关（自动过滤）", value=True)
sources = st.multiselect("来源（默认两项）", ["arXiv", "Crossref", "SemanticScholar"], default=["arXiv", "Crossref"])
max_results = st.slider("每个来源最多显示多少条？", min_value=5, max_value=50, value=10)
semanticscholar_api_key = st.text_input("（可选）Semantic Scholar API Key（没有可以留空）", value="", type="password")

# 简单 session 缓存避免短时间内重复请求
if 'cache' not in st.session_state:
    st.session_state.cache = {}

def cached_get(key, ttl_seconds=300):
    now = datetime.utcnow()
    entry = st.session_state.cache.get(key)
    if entry and (now - entry['time']).total_seconds() < ttl_seconds:
        return entry['value']
    return None

def cached_set(key, value):
    st.session_state.cache[key] = {'time': datetime.utcnow(), 'value': value}

# 教育相关词表，用于简单过滤（可根据需要扩充）
EDU_KEYWORDS = [
    "education","educational","learning","pedagogy","teaching","teacher","curriculum",
    "k-12","primary school","secondary school","higher education","university",
    " STEM education", "STEM", "instruction","professional development","classroom",
    "school", "students", "student learning", "MOOC", "online learning", "blended learning"
]

def looks_education_like(title, summary, venue=None):
    """简单规则：若标题/摘要/刊物名包含教育关键字，则认为与教育相关"""
    text = " ".join(filter(None, [title or "", summary or "", venue or ""])).lower()
    for kw in EDU_KEYWORDS:
        if kw.strip() and kw.lower() in text:
            return True
    return False

# ------- arXiv 查询 -------
def query_arxiv(q, max_results=10):
    q_enc = quote_plus(q)
    url = f"http://export.arxiv.org/api/query?search_query=all:{q_enc}&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
    cache_key = f"arxiv:{q}:{max_results}"
    cached = cached_get(cache_key, ttl_seconds=300)
    if cached:
        return cached
    resp = requests.get(url, timeout=20)
    feed = feedparser.parse(resp.text)
    results = []
    for entry in feed.entries:
        authors = [a.name for a in entry.get('authors', [])] if 'authors' in entry else []
        summary = entry.get('summary', '').replace('\n', ' ').strip()
        results.append({
            'source': 'arXiv',
            'id': entry.get('id'),
            'title': entry.get('title', '').replace('\n', ' ').strip(),
            'authors': authors,
            'summary': summary,
            'published': entry.get('published'),
            'link': entry.get('id'),
            'venue': entry.get('arxiv_primary_category', {}).get('term') if isinstance(entry.get('arxiv_primary_category'), dict) else None
        })
    cached_set(cache_key, results)
    return results

# ------- Crossref 查询 -------
def query_crossref(q, max_results=10, mailto="your-email@example.com"):
    cache_key = f"crossref:{q}:{max_results}"
    cached = cached_get(cache_key, ttl_seconds=300)
    if cached:
        return cached
    params = {
        "query.bibliographic": q,
        "rows": max_results,
        "mailto": mailto
    }
    url = "https://api.crossref.org/works"
    resp = requests.get(url, params=params, timeout=20)
    results = []
    if resp.status_code == 200:
        data = resp.json().get("message", {}).get("items", [])
        for item in data:
            title = item.get('title', [''])[0]
            authors = []
            for a in item.get('author', [])[:10]:
                name = " ".join(filter(None, [a.get('given'), a.get('family')]))
                authors.append(name)
            published = None
            if item.get('issued'):
                dp = item['issued'].get('date-parts', [[None]])[0]
                published = "-".join(str(x) for x in dp if x is not None)
            abstract = item.get('abstract') or ""
            doi = item.get('DOI')
            venue = item.get('container-title', [''])[0] if item.get('container-title') else None
            link = f"https://doi.org/{doi}" if doi else item.get('URL')
            results.append({
                'source': 'Crossref',
                'title': title,
                'authors': authors,
                'summary': abstract,
                'published': published,
                'link': link,
                'doi': doi,
                'venue': venue
            })
    cached_set(cache_key, results)
    return results

# ------- Semantic Scholar 查询（可选） -------
def query_semanticscholar(q, max_results=10, api_key=None):
    cache_key = f"semanticscholar:{q}:{max_results}"
    cached = cached_get(cache_key, ttl_seconds=300)
    if cached:
        return cached
    headers = {}
    if api_key:
        headers['x-api-key'] = api_key
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": q,
        "limit": max_results,
        "fields": "title,abstract,authors,url,year,venue,externalIds"
    }
    resp = requests.get(url, params=params, headers=headers, timeout=20)
    results = []
    if resp.status_code == 200:
        data = resp.json().get('data', [])
        for item in data:
            authors = [a.get('name') for a in item.get('authors', [])]
            results.append({
                'source': 'SemanticScholar',
                'title': item.get('title'),
                'authors': authors,
                'summary': item.get('abstract', ''),
                'published': item.get('year'),
                'link': item.get('url'),
                'venue': item.get('venue')
            })
    cached_set(cache_key, results)
    return results

# ------- 搜索按钮处理 -------
if st.button("🔎 搜索"):
    if not keyword.strip():
        st.warning("请先输入关键词。")
    else:
        with st.spinner("正在抓取并过滤教育相关论文……"):
            all_results = []
            # arXiv
            if "arXiv" in sources:
                try:
                    arxiv_res = query_arxiv(keyword, max_results=max_results)
                except Exception as e:
                    st.error(f"arXiv 查询出错: {e}")
                    arxiv_res = []
                # 过滤（如果选择教育优先）
                if education_only:
                    arxiv_res = [r for r in arxiv_res if looks_education_like(r['title'], r['summary'], r.get('venue'))]
                all_results.extend(arxiv_res)
                if arxiv_res:
                    st.subheader("arXiv（已过滤）" if education_only else "arXiv")
                    for r in arxiv_res:
                        st.markdown(f"**{r['title']}**  \n作者: {', '.join(r['authors'])}  \n发布时间: {r.get('published')}  \n[{r['link']}]({r['link']})")
                        st.write(r['summary'][:800] + ("…" if len(r['summary'])>800 else ""))
                        st.markdown("---")

            # Crossref
            if "Crossref" in sources:
                try:
                    cr_res = query_crossref(keyword, max_results=max_results, mailto="your-email@example.com")
                except Exception as e:
                    st.error(f"Crossref 查询出错: {e}")
                    cr_res = []
                if education_only:
                    cr_res = [r for r in cr_res if looks_education_like(r['title'], r.get('summary',''), r.get('venue'))]
                all_results.extend(cr_res)
                if cr_res:
                    st.subheader("Crossref（已过滤）" if education_only else "Crossref")
                    for r in cr_res:
                        st.markdown(f"**{r['title']}**  \n作者: {', '.join(r['authors'])}  \n刊物/会议: {r.get('venue')}  \n链接: {r.get('link')}")
                        if r.get('summary'):
                            # Crossref 有时候返回 HTML abstract；避免渲染过长
                            st.write(r['summary'][:800] + ("…" if len(r['summary'])>800 else ""))
                        st.markdown("---")

            # Semantic Scholar
            if "SemanticScholar" in sources:
                try:
                    ss_res = query_semanticscholar(keyword, max_results=max_results, api_key=semanticscholar_api_key or None)
                except Exception as e:
                    st.error(f"Semantic Scholar 查询出错: {e}")
                    ss_res = []
                if education_only:
                    ss_res = [r for r in ss_res if looks_education_like(r['title'], r.get('summary',''), r.get('venue'))]
                all_results.extend(ss_res)
                if ss_res:
                    st.subheader("Semantic Scholar（已过滤）" if education_only else "Semantic Scholar")
                    for r in ss_res:
                        st.markdown(f"**{r['title']}**  \n作者: {', '.join(r['authors'])}  \n刊物/年份: {r.get('venue')} {r.get('published')}  \n链接: {r.get('link')}")
                        st.write((r.get('summary') or "")[:800] + ("…" if (r.get('summary') or "")>800 else ""))
                        st.markdown("---")

        st.success(f"完成 — 共收集到 {len(all_results)} 条（可能存在重复）")
        # 简单去重（按 link 或 title）
        dedup = {}
        for r in all_results:
            key = (r.get('link') or r.get('title'))[:200]
            if key not in dedup:
                dedup[key] = r
        st.info(f"去重后结果：{len(dedup)} 条。页面顶部已按来源分组显示。")
