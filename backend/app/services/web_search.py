"""联网搜索：博查 / Tavily，配置存 app_settings['web_search'] = {provider, api_key}。"""
import httpx

from .actions import get_setting


class SearchError(Exception):
    pass


def _bocha(api_key: str, query: str, count: int) -> list[dict]:
    """博查搜索 API：https://bochaai.feishu.cn/wiki/RxPOwdB7HiPLDOkrCzhcUeTjnag"""
    try:
        resp = httpx.post(
            "https://api.bochaai.com/v1/web-search",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"query": query, "summary": True, "count": count},
            timeout=15,
        )
    except httpx.HTTPError as e:
        raise SearchError(f"搜索请求失败：{e}")
    if resp.status_code >= 400:
        raise SearchError(f"搜索服务返回 {resp.status_code}：{resp.text[:100]}")
    pages = ((resp.json().get("data") or {}).get("webPages") or {}).get("value") or []
    return [{"title": p.get("name") or "", "url": p.get("url") or "",
             "snippet": p.get("summary") or p.get("snippet") or ""} for p in pages]


def _tavily(api_key: str, query: str, count: int) -> list[dict]:
    """Tavily 搜索 API：https://docs.tavily.com"""
    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": count},
            timeout=15,
        )
    except httpx.HTTPError as e:
        raise SearchError(f"搜索请求失败：{e}")
    if resp.status_code >= 400:
        raise SearchError(f"搜索服务返回 {resp.status_code}：{resp.text[:100]}")
    return [{"title": r.get("title") or "", "url": r.get("url") or "",
             "snippet": r.get("content") or ""} for r in (resp.json().get("results") or [])]


def web_search(db, query: str, count: int = 8) -> list[dict]:
    """按设置里的搜索服务执行搜索，返回 [{title, url, snippet}]。未配置/失败抛 SearchError。"""
    cfg = get_setting(db, "web_search")
    provider = cfg.get("provider") or "bocha"
    api_key = (cfg.get("api_key") or "").strip()
    if not api_key:
        raise SearchError("尚未配置联网搜索服务，请到「模型设置 → 联网搜索」中填写 API Key")
    if provider == "tavily":
        return _tavily(api_key, query, count)
    return _bocha(api_key, query, count)
