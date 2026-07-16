from dataclasses import dataclass, field
from typing import Any, Optional, TypeVar
from datetime import datetime
import re
import tiktoken
from openai import OpenAI
from loguru import logger
import json
RawPaperItem = TypeVar('RawPaperItem')


def _parse_json_object(content: str) -> dict[str, Any]:
    """Extract and parse the first JSON object from an LLM response."""
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', content, flags=re.DOTALL)
        if match is None:
            raise
        return json.loads(match.group(0))


def _as_plain_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    return dict(value)


def _analysis_generation_kwargs(llm_params: dict, *, prefer_json: bool = True) -> dict[str, Any]:
    kwargs = _as_plain_dict(llm_params.get('generation_kwargs', {}))
    kwargs.update(_as_plain_dict(llm_params.get('analysis_generation_kwargs', {})))
    if prefer_json and "response_format" not in kwargs:
        kwargs["response_format"] = {"type": "json_object"}
    return kwargs


def _validate_analysis_payload(analysis: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(analysis.get("category"), dict) or not isinstance(analysis.get("analysis"), dict):
        raise ValueError("LLM analysis response must contain category and analysis objects")
    return analysis

@dataclass
class Paper:
    source: str
    title: str
    authors: list[str]
    abstract: str
    url: str
    pdf_url: Optional[str] = None
    full_text: Optional[str] = None
    tldr: Optional[str] = None
    affiliations: Optional[list[str]] = None
    analysis: Optional[dict[str, Any]] = None
    similar_corpus: list[dict[str, Any]] = field(default_factory=list)
    score: Optional[float] = None

    def _generate_tldr_with_llm(self, openai_client:OpenAI,llm_params:dict) -> str:
        lang = llm_params.get('language', 'English')
        prompt = f"Given the following information of a paper, generate a one-sentence TLDR summary in {lang}:\n\n"
        if self.title:
            prompt += f"Title:\n {self.title}\n\n"

        if self.abstract:
            prompt += f"Abstract: {self.abstract}\n\n"

        if self.full_text:
            prompt += f"Preview of main content:\n {self.full_text}\n\n"

        if not self.full_text and not self.abstract:
            logger.warning(f"Neither full text nor abstract is provided for {self.url}")
            return "Failed to generate TLDR. Neither full text nor abstract is provided"
        
        # use gpt-4o tokenizer for estimation
        enc = tiktoken.encoding_for_model("gpt-4o")
        prompt_tokens = enc.encode(prompt)
        prompt_tokens = prompt_tokens[:4000]  # truncate to 4000 tokens
        prompt = enc.decode(prompt_tokens)
        
        response = openai_client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": f"You are an assistant who perfectly summarizes scientific paper, and gives the core idea of the paper to the user. Your answer should be in {lang}.",
                },
                {"role": "user", "content": prompt},
            ],
            **llm_params.get('generation_kwargs', {})
        )
        tldr = response.choices[0].message.content
        return tldr
    
    def generate_tldr(self, openai_client:OpenAI,llm_params:dict) -> str:
        try:
            tldr = self._generate_tldr_with_llm(openai_client,llm_params)
            self.tldr = tldr
            return tldr
        except Exception as e:
            logger.warning(f"Failed to generate tldr of {self.url}: {e}")
            tldr = self.abstract
            self.tldr = tldr
            return tldr

    def _generate_affiliations_with_llm(self, openai_client:OpenAI,llm_params:dict) -> Optional[list[str]]:
        if self.full_text is not None:
            prompt = f"Given the beginning of a paper, extract the affiliations of the authors in a python list format, which is sorted by the author order. If there is no affiliation found, return an empty list '[]':\n\n{self.full_text}"
            # use gpt-4o tokenizer for estimation
            enc = tiktoken.encoding_for_model("gpt-4o")
            prompt_tokens = enc.encode(prompt)
            prompt_tokens = prompt_tokens[:2000]  # truncate to 2000 tokens
            prompt = enc.decode(prompt_tokens)
            affiliations = openai_client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an assistant who perfectly extracts affiliations of authors from a paper. You should return a python list of affiliations sorted by the author order, like [\"TsingHua University\",\"Peking University\"]. If an affiliation is consisted of multi-level affiliations, like 'Department of Computer Science, TsingHua University', you should return the top-level affiliation 'TsingHua University' only. Do not contain duplicated affiliations. If there is no affiliation found, you should return an empty list [ ]. You should only return the final list of affiliations, and do not return any intermediate results.",
                    },
                    {"role": "user", "content": prompt},
                ],
                **llm_params.get('generation_kwargs', {})
            )
            affiliations = affiliations.choices[0].message.content

            affiliations = re.search(r'\[.*?\]', affiliations, flags=re.DOTALL).group(0)
            affiliations = json.loads(affiliations)
            affiliations = list(set(affiliations))
            affiliations = [str(a) for a in affiliations]

            return affiliations
    
    def generate_affiliations(self, openai_client:OpenAI,llm_params:dict) -> Optional[list[str]]:
        try:
            affiliations = self._generate_affiliations_with_llm(openai_client,llm_params)
            self.affiliations = affiliations
            return affiliations
        except Exception as e:
            logger.warning(f"Failed to generate affiliations of {self.url}: {e}")
            self.affiliations = None
            return None

    def _generate_analysis_with_llm(
        self,
        openai_client: OpenAI,
        llm_params: dict,
        zotero_taxonomy: list[dict[str, Any]],
        similar_corpus: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        lang = llm_params.get('language', 'English')
        similar_corpus = similar_corpus if similar_corpus is not None else self.similar_corpus
        prompt = f"""
You need to recommend the best Zotero collection for a newly recommended paper and briefly interpret the paper for a researcher.

Use the user's existing Zotero collection taxonomy first. Only propose a new collection when no existing collection accurately summarizes the paper. If you propose a new collection:
1. Put it under the most appropriate existing parent path.
2. Follow the existing naming style, such as "中文 English".
3. Explain briefly why the new collection is needed.
4. Do not create a new collection for minor wording differences.

Answer in {lang}. Return only one JSON object with this exact shape:
{{
  "category": {{
    "recommended_path": "existing or new Zotero path",
    "is_new": false,
    "parent_path": "parent path when is_new is true, otherwise null",
    "confidence": "high|medium|low",
    "reason": "brief reason"
  }},
  "analysis": {{
    "problem": "What problem does the paper try to solve?",
    "method": "How does it solve the problem?",
    "inspiration": "What research inspiration can it bring?",
    "reading_suggestion": "精读，适合学习框架并进一步实验 | 精读，适合复现实验 | 粗读即可 | 收藏观察"
  }}
}}

Existing Zotero taxonomy with paper counts:
{json.dumps(zotero_taxonomy, ensure_ascii=False, indent=2)}

Most similar papers from the user's Zotero library:
{json.dumps(similar_corpus, ensure_ascii=False, indent=2)}

Recommended paper:
Title: {self.title}
Authors: {', '.join(self.authors)}
Abstract: {self.abstract}
Preview of main content: {self.full_text or ''}
"""

        enc = tiktoken.encoding_for_model("gpt-4o")
        prompt_tokens = enc.encode(prompt)
        prompt = enc.decode(prompt_tokens[:6000])

        messages = [
            {
                "role": "system",
                "content": (
                    "You classify scientific papers into the user's Zotero taxonomy and "
                    "write concise, researcher-facing analysis. Return valid JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        kwargs = _analysis_generation_kwargs(llm_params, prefer_json=True)
        try:
            response = openai_client.chat.completions.create(
                messages=messages,
                **kwargs
            )
        except Exception as exc:
            if "response_format" not in kwargs:
                raise
            logger.warning(f"Analysis JSON mode failed for {self.url}: {exc}. Retrying without response_format.")
            kwargs.pop("response_format", None)
            response = openai_client.chat.completions.create(
                messages=messages,
                **kwargs
            )
        content = response.choices[0].message.content
        try:
            return _validate_analysis_payload(_parse_json_object(content))
        except Exception as parse_exc:
            logger.warning(f"Failed to parse analysis JSON for {self.url}: {parse_exc}. Asking LLM to repair JSON.")
            repair_messages = [
                {
                    "role": "system",
                    "content": (
                        "Convert the user's text into one valid JSON object. "
                        "Return only JSON with top-level keys category and analysis."
                    ),
                },
                {"role": "user", "content": content},
            ]
            repair_kwargs = _analysis_generation_kwargs(llm_params, prefer_json=True)
            try:
                repair_response = openai_client.chat.completions.create(
                    messages=repair_messages,
                    **repair_kwargs
                )
            except Exception as exc:
                if "response_format" not in repair_kwargs:
                    raise
                logger.warning(f"Analysis JSON repair mode failed for {self.url}: {exc}. Retrying repair without response_format.")
                repair_kwargs.pop("response_format", None)
                repair_response = openai_client.chat.completions.create(
                    messages=repair_messages,
                    **repair_kwargs
                )
            repair_content = repair_response.choices[0].message.content
            return _validate_analysis_payload(_parse_json_object(repair_content))

    def generate_analysis(
        self,
        openai_client: OpenAI,
        llm_params: dict,
        zotero_taxonomy: list[dict[str, Any]],
        similar_corpus: list[dict[str, Any]] | None = None,
    ) -> Optional[dict[str, Any]]:
        try:
            analysis = self._generate_analysis_with_llm(
                openai_client,
                llm_params,
                zotero_taxonomy,
                similar_corpus,
            )
            self.analysis = analysis
            return analysis
        except Exception as e:
            logger.warning(f"Failed to generate analysis of {self.url}: {e}")
            self.analysis = None
            return None


@dataclass
class CorpusPaper:
    title: str
    abstract: str
    added_date: datetime
    paths: list[str]
