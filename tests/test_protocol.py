"""Tests for zotero_arxiv_daily.protocol: Paper.generate_tldr, Paper.generate_affiliations."""

import pytest

from tests.canned_responses import make_sample_paper, make_stub_openai_client


@pytest.fixture()
def llm_params():
    return {
        "language": "English",
        "generation_kwargs": {"model": "gpt-4o-mini", "max_tokens": 16384},
    }


# ---------------------------------------------------------------------------
# generate_tldr
# ---------------------------------------------------------------------------


def test_tldr_returns_response(llm_params):
    client = make_stub_openai_client()
    paper = make_sample_paper()
    result = paper.generate_tldr(client, llm_params)
    assert result == "Hello! How can I assist you today?"
    assert paper.tldr == result


def test_tldr_without_abstract_or_fulltext(llm_params):
    client = make_stub_openai_client()
    paper = make_sample_paper(abstract="", full_text=None)
    result = paper.generate_tldr(client, llm_params)
    assert "Failed to generate TLDR" in result


def test_tldr_falls_back_to_abstract_on_error(llm_params):
    paper = make_sample_paper()

    # Client whose create() raises
    from types import SimpleNamespace

    broken_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(RuntimeError("API down")))
        )
    )
    result = paper.generate_tldr(broken_client, llm_params)
    assert result == paper.abstract


def test_tldr_truncates_long_prompt(llm_params):
    client = make_stub_openai_client()
    paper = make_sample_paper(full_text="word " * 10000)
    result = paper.generate_tldr(client, llm_params)
    assert result is not None


# ---------------------------------------------------------------------------
# generate_analysis
# ---------------------------------------------------------------------------


def test_analysis_returns_structured_category_and_reading_guidance(llm_params):
    client = make_stub_openai_client()
    paper = make_sample_paper(
        similar_corpus=[
            {
                "title": "Planning Corpus Paper",
                "paths": ["Agent/效率 Efficiency/规划 Planning"],
                "similarity": 0.91,
            }
        ]
    )
    taxonomy = [
        {"path": "Agent/安全 Security", "count": 3},
        {"path": "Agent/效率 Efficiency/规划 Planning", "count": 7},
    ]

    result = paper.generate_analysis(client, llm_params, taxonomy)

    assert result["category"]["recommended_path"] == "Agent/效率 Efficiency/规划 Planning"
    assert result["category"]["is_new"] is False
    assert result["translation"]["title_zh"] == "面向长程规划的样例论文标题"
    assert "结构化反馈机制" in result["translation"]["abstract_zh"]
    assert "long-horizon planning" in result["analysis"]["problem"]
    assert "精读" in result["analysis"]["reading_suggestion"]
    assert paper.analysis == result


def test_analysis_can_expand_with_split_request(llm_params):
    client = make_stub_openai_client()
    paper = make_sample_paper()
    params = {**llm_params, "split_deep_analysis_requests": True}

    result = paper.generate_analysis(client, params, [])

    assert result["translation"]["title_zh"] == "面向长程规划的样例论文标题"
    assert "模块拆分" in result["analysis"]["reading_suggestion"]
    assert paper.analysis == result


def test_split_analysis_preserves_initial_category_when_expansion_omits_it(llm_params):
    from types import SimpleNamespace

    responses = iter([
        """
        {
          "translation": {
            "title_zh": "初始中文标题",
            "abstract_zh": "初始中文摘要"
          },
          "category": {
            "recommended_path": "Agent/效率 Efficiency/规划 Planning",
            "is_new": false,
            "parent_path": null,
            "confidence": "high",
            "reason": "This is the initial category reason."
          },
          "analysis": {
            "problem": "Initial problem.",
            "method": "Initial method.",
            "inspiration": "Initial inspiration.",
            "reading_suggestion": "精读，适合学习框架并进一步实验"
          }
        }
        """,
        """
        {
          "translation": {
            "title_zh": "扩写后的中文标题",
            "abstract_zh": "扩写后的中文摘要"
          },
          "category": {},
          "analysis": {
            "problem": "Expanded problem.",
            "method": "Expanded method.",
            "inspiration": "Expanded inspiration.",
            "reading_suggestion": "精读，扩写后的阅读建议。"
          }
        }
        """,
    ])

    def create_response(**kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=next(responses)),
                )
            ]
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create_response)
        )
    )
    paper = make_sample_paper()
    params = {**llm_params, "split_deep_analysis_requests": True}

    result = paper.generate_analysis(client, params, [])

    assert result["translation"]["title_zh"] == "扩写后的中文标题"
    assert result["analysis"]["problem"] == "Expanded problem."
    assert result["category"]["recommended_path"] == "Agent/效率 Efficiency/规划 Planning"
    assert result["category"]["confidence"] == "high"


def test_analysis_falls_back_to_none_on_malformed_json(llm_params):
    from types import SimpleNamespace

    def create_bad_json(**kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="category: planning"),
                )
            ]
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create_bad_json)
        )
    )
    paper = make_sample_paper()

    result = paper.generate_analysis(client, llm_params, [])

    assert result is None
    assert paper.analysis is None


# ---------------------------------------------------------------------------
# generate_affiliations
# ---------------------------------------------------------------------------


def test_affiliations_returns_parsed_list(llm_params):
    client = make_stub_openai_client()
    paper = make_sample_paper()
    result = paper.generate_affiliations(client, llm_params)
    assert isinstance(result, list)
    assert "TsingHua University" in result
    assert "Peking University" in result


def test_affiliations_none_without_fulltext(llm_params):
    client = make_stub_openai_client()
    paper = make_sample_paper(full_text=None)
    result = paper.generate_affiliations(client, llm_params)
    assert result is None


def test_affiliations_deduplicates(llm_params):
    """The stub returns two distinct affiliations, so no dedup needed.
    But confirm the set() dedup in the code doesn't break anything.
    """
    client = make_stub_openai_client()
    paper = make_sample_paper()
    result = paper.generate_affiliations(client, llm_params)
    assert len(result) == len(set(result))


def test_affiliations_malformed_llm_output(llm_params):
    """LLM returns affiliations without JSON brackets. Should fall back gracefully."""
    from types import SimpleNamespace

    def create_no_brackets(**kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="TsingHua University, Peking University"),
                )
            ]
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create_no_brackets)
        )
    )
    paper = make_sample_paper()
    result = paper.generate_affiliations(client, llm_params)
    # re.search for [...] will fail -> AttributeError -> caught -> returns None
    assert result is None


def test_affiliations_error_returns_none(llm_params):
    from types import SimpleNamespace

    broken_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
        )
    )
    paper = make_sample_paper()
    result = paper.generate_affiliations(broken_client, llm_params)
    assert result is None
    assert paper.affiliations is None
