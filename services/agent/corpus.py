from __future__ import annotations

from .models import Citation


_CORPUS: list[Citation] = [
    Citation(
        source_id="shiji-xia-benji",
        title="《史记 · 夏本纪》",
        excerpt="禹乃遂与益、后稷奉帝命，命诸侯百姓兴人徒以傅土，行山表木，定高山大川。",
        relevance=0.0,
    ),
    Citation(
        source_id="shangshu-yu-gong",
        title="《尚书 · 禹贡》",
        excerpt="禹敷土，随山刊木，奠高山大川。",
        relevance=0.0,
    ),
    Citation(
        source_id="mengzi-tengwengong",
        title="《孟子 · 滕文公》",
        excerpt="禹疏九河，瀹济、漯而注诸海，决汝、汉，排淮、泗，而注之江。",
        relevance=0.0,
    ),
    Citation(
        source_id="shangjun-shu",
        title="《商君书 · 更法》",
        excerpt="疑行无成，疑事无功。圣人苟可以强国，不法其故；苟可以利民，不循其礼。",
        relevance=0.0,
    ),
    Citation(
        source_id="shiji-shang-jun-liezhuan",
        title="《史记 · 商君列传》",
        excerpt="於是太子犯法。卫鞅曰：法之不行，自上犯之。",
        relevance=0.0,
    ),
    Citation(
        source_id="shiji-zheng-he",
        title="《明史 · 郑和传》",
        excerpt="和经事三朝，先后七奉使，所历凡三十余国。",
        relevance=0.0,
    ),
    Citation(
        source_id="shiji-qin-shi-huang",
        title="《史记 · 秦始皇本纪》",
        excerpt="一法度衡石丈尺。车同轨，书同文字。",
        relevance=0.0,
    ),
]


_KEYWORDS: dict[str, list[str]] = {
    "shiji-xia-benji": ["禹", "治水", "夏", "鲧"],
    "shangshu-yu-gong": ["禹", "九州", "山川", "贡赋"],
    "mengzi-tengwengong": ["禹", "九河", "疏导", "江"],
    "shangjun-shu": ["商鞅", "变法", "更法", "强国"],
    "shiji-shang-jun-liezhuan": ["商鞅", "太子", "法", "卫鞅"],
    "shiji-zheng-he": ["郑和", "下西洋", "明", "三宝"],
    "shiji-qin-shi-huang": ["秦", "始皇", "统一", "度量衡", "车同轨"],
}


def list_corpus() -> list[Citation]:
    return [c.model_copy() for c in _CORPUS]


def search_corpus(query: str, top_k: int = 3) -> list[Citation]:
    out: list[tuple[float, Citation]] = []
    for c in _CORPUS:
        kws = _KEYWORDS.get(c.source_id, [])
        hit = sum(1 for k in kws if k in query)
        if hit == 0:
            continue
        score = min(1.0, 0.4 + 0.2 * hit)
        cite = c.model_copy(update={"relevance": round(score, 2)})
        out.append((score, cite))
    out.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in out[:top_k]]
