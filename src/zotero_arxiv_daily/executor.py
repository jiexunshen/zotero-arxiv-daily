from loguru import logger
from pyzotero import zotero
from omegaconf import DictConfig, ListConfig
from .utils import glob_match
from .retriever import get_retriever_cls
from .protocol import CorpusPaper
import random
from datetime import datetime
from .reranker import get_reranker_cls
from .construct_email import render_email
from .utils import send_email
from openai import OpenAI
from tqdm import tqdm
from collections import Counter
from pathlib import Path


LOG_FETCHING_ZOTERO_CORPUS = "正在获取 Zotero 文献库 | Fetching zotero corpus"


def normalize_path_patterns(patterns: list[str] | ListConfig | None, config_key: str) -> list[str] | None:
    if patterns is None:
        return None

    if not isinstance(patterns, (list, ListConfig)):
        raise TypeError(
            f"config.zotero.{config_key} must be a list of glob patterns or null, "
            'for example ["2026/survey/**"]. Single strings are not supported.'
        )

    if any(not isinstance(pattern, str) for pattern in patterns):
        raise TypeError(f"config.zotero.{config_key} must contain only glob pattern strings.")

    return list(patterns)


def build_zotero_taxonomy(corpus: list[CorpusPaper]) -> list[dict]:
    path_counts = Counter(path for paper in corpus for path in paper.paths)
    return [
        {"path": path, "count": count}
        for path, count in sorted(path_counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def write_email_preview(config: DictConfig, html: str) -> Path | None:
    preview_path = config.executor.get("preview_email_path", None)
    if not preview_path:
        return None

    path = Path(preview_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    logger.info(f"邮件预览已写入 {path} | Email preview written to {path}")
    return path


class Executor:
    def __init__(self, config:DictConfig):
        self.config = config
        self.include_path_patterns = normalize_path_patterns(config.zotero.include_path, "include_path")
        self.ignore_path_patterns = normalize_path_patterns(config.zotero.ignore_path, "ignore_path")
        self.retrievers = {
            source: get_retriever_cls(source)(config) for source in config.executor.source
        }
        self.reranker = get_reranker_cls(config.executor.reranker)(config)
        self.openai_client = OpenAI(api_key=config.llm.api.key, base_url=config.llm.api.base_url)
    def fetch_zotero_corpus(self) -> list[CorpusPaper]:
        logger.info(LOG_FETCHING_ZOTERO_CORPUS)
        zot = zotero.Zotero(self.config.zotero.user_id, 'user', self.config.zotero.api_key)
        collections = zot.everything(zot.collections())
        collections = {c['key']:c for c in collections}
        corpus = zot.everything(zot.items(itemType='conferencePaper || journalArticle || preprint'))
        corpus = [c for c in corpus if c['data']['abstractNote'] != '']
        def get_collection_path(col_key:str) -> str:
            if p := collections[col_key]['data']['parentCollection']:
                return get_collection_path(p) + '/' + collections[col_key]['data']['name']
            else:
                return collections[col_key]['data']['name']
        for c in corpus:
            paths = [get_collection_path(col) for col in c['data']['collections']]
            c['paths'] = paths
        logger.info(f"已获取 {len(corpus)} 篇 Zotero 文献 | Fetched {len(corpus)} zotero papers")
        return [CorpusPaper(
            title=c['data']['title'],
            abstract=c['data']['abstractNote'],
            added_date=datetime.strptime(c['data']['dateAdded'], '%Y-%m-%dT%H:%M:%SZ'),
            paths=c['paths']
        ) for c in corpus]
    
    def filter_corpus(self, corpus:list[CorpusPaper]) -> list[CorpusPaper]:
        if self.include_path_patterns:
            logger.info(f"正在按 include_path 选择 Zotero 文献: {self.include_path_patterns} | Selecting zotero papers matching include_path: {self.include_path_patterns}")
            corpus = [
                c for c in corpus
                if any(
                    glob_match(path, pattern)
                    for path in c.paths
                    for pattern in self.include_path_patterns
                )
            ]
        if self.ignore_path_patterns:
            logger.info(f"正在按 ignore_path 排除 Zotero 文献: {self.ignore_path_patterns} | Excluding zotero papers matching ignore_path: {self.ignore_path_patterns}")
            corpus = [
                c for c in corpus
                if not any(
                    glob_match(path, pattern)
                    for path in c.paths
                    for pattern in self.ignore_path_patterns
                )
            ]
        if self.include_path_patterns or self.ignore_path_patterns:
            samples = random.sample(corpus, min(5, len(corpus)))
            samples = '\n'.join([c.title + ' - ' + '\n'.join(c.paths) for c in samples])
            logger.info(f"已选中 {len(corpus)} 篇 Zotero 文献 | Selected {len(corpus)} zotero papers:\n{samples}\n...")
        return corpus

    
    def run(self):
        corpus = self.fetch_zotero_corpus()
        corpus = self.filter_corpus(corpus)
        if len(corpus) == 0:
            logger.error(
                "未找到 Zotero 文献，请检查 Zotero 设置 | "
                "No zotero papers found. Please check your zotero settings: "
                f"user_id={self.config.zotero.user_id}, "
                f"include_path={self.config.zotero.include_path}, "
                f"ignore_path={self.config.zotero.ignore_path}"
            )
            return
        zotero_taxonomy = build_zotero_taxonomy(corpus)
        all_papers = []
        for source, retriever in self.retrievers.items():
            logger.info(f"正在检索 {source} 论文 | Retrieving {source} papers...")
            papers = retriever.retrieve_papers()
            if len(papers) == 0:
                logger.info(f"未找到 {source} 论文 | No {source} papers found")
                continue
            logger.info(f"已检索到 {len(papers)} 篇 {source} 论文 | Retrieved {len(papers)} {source} papers")
            all_papers.extend(papers)
        logger.info(f"全部来源共检索到 {len(all_papers)} 篇论文 | Total {len(all_papers)} papers retrieved from all sources")
        reranked_papers = []
        if len(all_papers) > 0:
            logger.info("正在重排序论文 | Reranking papers...")
            reranked_papers = self.reranker.rerank(all_papers, corpus)
            reranked_papers = reranked_papers[:self.config.executor.max_paper_num]
            logger.info("正在生成 TLDR 和作者机构 | Generating TLDR and affiliations...")
            for p in tqdm(reranked_papers):
                p.generate_tldr(self.openai_client, self.config.llm)
                p.generate_affiliations(self.openai_client, self.config.llm)
                if self.config.llm.get("enable_deep_analysis", True):
                    logger.info(f"正在生成深度解读: {p.title} | Generating deep analysis for {p.title}")
                    analysis = p.generate_analysis(self.openai_client, self.config.llm, zotero_taxonomy)
                    if analysis is None:
                        logger.warning(f"未能生成深度解读: {p.title} | Deep analysis was not generated for {p.title}")
                    else:
                        logger.info(
                            f"深度解读已生成: {p.title} | Deep analysis generated for {p.title}: "
                            f"{analysis.get('category', {}).get('recommended_path', 'Unknown')}"
                        )
        elif not self.config.executor.send_empty:
            logger.info("未找到新论文，不发送邮件 | No new papers found. No email will be sent.")
            return
        email_content = render_email(reranked_papers)
        write_email_preview(self.config, email_content)
        if self.config.executor.get("dry_run", False):
            logger.info("已启用 dry run，跳过邮件发送 | Dry run is enabled. Email sending skipped.")
            return
        logger.info("正在发送邮件 | Sending email...")
        send_email(self.config, email_content)
        logger.info("邮件发送成功 | Email sent successfully")
