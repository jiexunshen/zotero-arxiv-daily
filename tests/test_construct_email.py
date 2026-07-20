"""Tests for zotero_arxiv_daily.construct_email: render_email, get_stars, get_block_html."""

from zotero_arxiv_daily.construct_email import render_email, get_stars, get_block_html, get_empty_html
from tests.canned_responses import make_sample_paper


def test_render_email_with_papers():
    papers = [make_sample_paper(score=7.5, tldr="A great paper.", affiliations=["MIT"])]
    html = render_email(papers)
    assert "Sample Paper Title" in html
    assert "A great paper." in html
    assert "MIT" in html


def test_render_email_empty_list():
    html = render_email([])
    assert "No Papers Today" in html


def test_render_email_author_truncation():
    authors = [f"Author {i}" for i in range(10)]
    paper = make_sample_paper(authors=authors, score=7.0, tldr="ok")
    html = render_email([paper])
    assert "Author 0" in html
    assert "Author 1" in html
    assert "Author 2" in html
    assert "..." in html
    assert "Author 8" in html
    assert "Author 9" in html
    # Middle authors should be truncated
    assert "Author 5" not in html


def test_render_email_affiliation_truncation():
    affiliations = [f"Uni {i}" for i in range(8)]
    paper = make_sample_paper(affiliations=affiliations, score=7.0, tldr="ok")
    html = render_email([paper])
    assert "Uni 0" in html
    assert "Uni 4" in html
    assert "..." in html
    assert "Uni 7" not in html


def test_render_email_no_affiliations():
    paper = make_sample_paper(affiliations=None, score=7.0, tldr="ok")
    html = render_email([paper])
    assert "Unknown Affiliation" in html


def test_render_email_includes_deep_analysis():
    paper = make_sample_paper(
        score=8.2,
        tldr="ok",
        analysis={
            "translation": {
                "title_zh": "样例论文标题",
                "abstract_zh": "这篇论文探索了小组件工程的一种新方法。",
            },
            "category": {
                "recommended_path": "Agent/效率 Efficiency/规划 Planning",
                "is_new": False,
                "reason": "Closest to existing planning papers.",
            },
            "analysis": {
                "problem": "How can agents plan over long horizons?",
                "method": "It adds a planning loop with feedback.",
                "inspiration": "Try separating planning evaluation from tool-use evaluation.",
                "reading_suggestion": "精读，适合学习框架并进一步实验",
            },
            "publication": {
                "venue": "暂未发表；预印本最后调整时间：2026-01-03；疑似投稿：NeurIPS 2026（根据模板推断）",
                "first_publication_time": "2026-01-01",
                "acceptance_time": None,
                "publication_time": None,
                "evidence": "No journal_ref in arXiv metadata.",
            },
            "open_source": {
                "is_open_source": True,
                "repository_url": "https://github.com/example/planning-paper",
                "evidence": "GitHub URL found in paper.",
            },
        },
    )

    html = render_email([paper])

    assert "推荐分类" in html
    assert "Sample Paper Title" in html
    assert "样例论文标题" in html
    assert "英文摘要" in html
    assert "This paper explores a novel approach to widget engineering." in html
    assert "中文摘要" in html
    assert "这篇论文探索了小组件工程的一种新方法。" in html
    assert "Agent/效率 Efficiency/规划 Planning" in html
    assert "它想解决的问题" in html
    assert "How can agents plan over long horizons?" in html
    assert "科研启发" in html
    assert "精读" in html
    assert "发表信息" in html
    assert "NeurIPS 2026" in html
    assert "首次发表时间" in html
    assert "2026-01-01" in html
    assert "Github" in html
    assert "https://github.com/example/planning-paper" in html


def test_render_email_uses_clear_label_when_category_path_missing():
    paper = make_sample_paper(
        score=8.2,
        tldr="ok",
        analysis={
            "category": {},
            "analysis": {
                "problem": "problem",
            },
        },
    )

    html = render_email([paper])

    assert "分类推荐生成失败" in html
    assert "<strong>推荐分类:</strong> Unknown" not in html


def test_get_stars_low_score():
    assert get_stars(5.0) == ""
    assert get_stars(6.0) == ""


def test_get_stars_high_score():
    stars = get_stars(8.0)
    assert stars.count("full-star") == 5


def test_get_stars_mid_score():
    stars = get_stars(7.0)
    assert "star" in stars
    assert stars.count("full-star") + stars.count("half-star") > 0


def test_get_block_html_contains_all_fields():
    html = get_block_html("Title", "Auth", "3.5", "Summary", "http://pdf.url", "MIT")
    assert "Title" in html
    assert "Auth" in html
    assert "3.5" in html
    assert "Summary" in html
    assert "http://pdf.url" in html
    assert "MIT" in html


def test_get_empty_html():
    html = get_empty_html()
    assert "No Papers Today" in html
