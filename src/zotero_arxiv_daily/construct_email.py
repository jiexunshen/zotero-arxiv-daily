from .protocol import Paper
import math
from html import escape


framework = """
<!DOCTYPE HTML>
<html>
<head>
  <style>
    .star-wrapper {
      font-size: 1.3em; /* 调整星星大小 */
      line-height: 1; /* 确保垂直对齐 */
      display: inline-flex;
      align-items: center; /* 保持对齐 */
    }
    .half-star {
      display: inline-block;
      width: 0.5em; /* 半颗星的宽度 */
      overflow: hidden;
      white-space: nowrap;
      vertical-align: middle;
    }
    .full-star {
      vertical-align: middle;
    }
  </style>
</head>
<body>

<div>
    __CONTENT__
</div>

<br><br>
<div>
To unsubscribe, remove your email in your Github Action setting.
</div>

</body>
</html>
"""

def get_empty_html():
  block_template = """
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-family: Arial, sans-serif; border: 1px solid #ddd; border-radius: 8px; padding: 16px; background-color: #f9f9f9;">
  <tr>
    <td style="font-size: 20px; font-weight: bold; color: #333;">
        No Papers Today. Take a Rest!
    </td>
  </tr>
  </table>
  """
  return block_template

def _format_text(value) -> str:
    return escape(str(value)).replace("\n", "<br>")


def get_title_translation_html(analysis: dict | None) -> str:
    if not analysis:
        return ""

    translation = analysis.get("translation", {})
    title_zh = translation.get("title_zh") if isinstance(translation, dict) else None
    if not title_zh:
        return ""

    return f"""
            <div style="font-size: 15px; font-weight: normal; color: #444; padding-top: 4px;">
                {_format_text(title_zh)}
            </div>
    """


def get_analysis_html(analysis: dict | None, abstract: str | None = None) -> str:
    if not analysis:
        return ""

    translation = analysis.get("translation", {})
    category = analysis.get("category", {})
    detail = analysis.get("analysis", {})
    publication = analysis.get("publication", {})
    open_source = analysis.get("open_source", {})
    abstract_zh = translation.get("abstract_zh", "") if isinstance(translation, dict) else ""
    recommended_path = category.get("recommended_path") or "分类推荐生成失败"
    category_reason = category.get("reason", "")
    is_new = category.get("is_new", False)
    new_label = "（建议新增分类）" if is_new else ""
    repository_url = open_source.get("repository_url") if isinstance(open_source, dict) else None
    open_source_status = ""
    if isinstance(open_source, dict):
        if open_source.get("is_open_source") is True:
            open_source_status = f"已开源：{repository_url}" if repository_url else "已开源，但未提供仓库地址"
        elif open_source.get("is_open_source") is False:
            open_source_status = "未发现开源仓库"
        elif open_source.get("evidence"):
            open_source_status = str(open_source.get("evidence"))

    rows = [
        ("英文摘要", abstract),
        ("中文摘要", abstract_zh),
        ("发表信息", publication.get("venue", "") if isinstance(publication, dict) else ""),
        ("首次发表时间", publication.get("first_publication_time", "") if isinstance(publication, dict) else ""),
        ("录用时间", publication.get("acceptance_time", "") if isinstance(publication, dict) else ""),
        ("见刊时间", publication.get("publication_time", "") if isinstance(publication, dict) else ""),
        ("发表信息依据", publication.get("evidence", "") if isinstance(publication, dict) else ""),
        ("开源情况", open_source_status),
        ("推荐分类", f"{recommended_path} {new_label}".strip()),
        ("分类理由", category_reason),
        ("它想解决的问题", detail.get("problem", "")),
        ("它是如何解决的", detail.get("method", "")),
        ("科研启发", detail.get("inspiration", "")),
        ("阅读建议", detail.get("reading_suggestion", "")),
    ]
    rows_html = "\n".join(
        f"""
        <tr>
            <td style="font-size: 14px; color: #333; padding: 4px 0;">
                <strong>{escape(label)}:</strong> {_format_text(value)}
            </td>
        </tr>
        """
        for label, value in rows
        if value
    )
    if not rows_html:
        return ""
    return f"""
    <tr>
        <td style="font-size: 14px; color: #333; padding: 8px 0;">
            <strong>深度解读</strong>
        </td>
    </tr>
    {rows_html}
    """


def get_github_button_html(analysis: dict | None) -> str:
    if not analysis:
        return ""
    open_source = analysis.get("open_source", {})
    if not isinstance(open_source, dict):
        return ""
    repository_url = open_source.get("repository_url")
    if not repository_url:
        return ""
    return f"""
            <a href="{escape(str(repository_url), quote=True)}" style="display: inline-block; text-decoration: none; font-size: 14px; font-weight: bold; color: #fff; background-color: #111; padding: 8px 16px; border-radius: 4px; margin-left: 8px;">Github</a>
    """


def get_block_html(title:str, authors:str, rate:str, tldr:str, pdf_url:str, affiliations:str=None, analysis:dict=None, abstract:str=None):
    block_template = """
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-family: Arial, sans-serif; border: 1px solid #ddd; border-radius: 8px; padding: 16px; background-color: #f9f9f9;">
    <tr>
        <td style="font-size: 20px; font-weight: bold; color: #333;">
            {title}
            {title_translation_html}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #666; padding: 8px 0;">
            {authors}
            <br>
            <i>{affiliations}</i>
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #333; padding: 8px 0;">
            <strong>Relevance:</strong> {rate}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #333; padding: 8px 0;">
            <strong>TLDR:</strong> {tldr}
        </td>
    </tr>
    {analysis_html}

    <tr>
        <td style="padding: 8px 0;">
            <a href="{pdf_url}" style="display: inline-block; text-decoration: none; font-size: 14px; font-weight: bold; color: #fff; background-color: #d9534f; padding: 8px 16px; border-radius: 4px;">PDF</a>
            {github_button_html}
        </td>
    </tr>
</table>
"""
    return block_template.format(
        title=title,
        authors=authors,
        rate=rate,
        tldr=tldr,
        pdf_url=pdf_url,
        affiliations=affiliations,
        title_translation_html=get_title_translation_html(analysis),
        analysis_html=get_analysis_html(analysis, abstract),
        github_button_html=get_github_button_html(analysis),
    )

def get_stars(score:float):
    full_star = '<span class="full-star">⭐</span>'
    half_star = '<span class="half-star">⭐</span>'
    low = 6
    high = 8
    if score <= low:
        return ''
    elif score >= high:
        return full_star * 5
    else:
        interval = (high-low) / 10
        star_num = math.ceil((score-low) / interval)
        full_star_num = int(star_num/2)
        half_star_num = star_num - full_star_num * 2
        return '<div class="star-wrapper">'+full_star * full_star_num + half_star * half_star_num + '</div>'


def render_email(papers:list[Paper]) -> str:
    parts = []
    if len(papers) == 0 :
        return framework.replace('__CONTENT__', get_empty_html())
    
    for p in papers:
        #rate = get_stars(p.score)
        rate = round(p.score, 1) if p.score is not None else 'Unknown'
        author_list = [a for a in p.authors]
        num_authors = len(author_list)
        if num_authors <= 5:
            authors = ', '.join(author_list)
        else:
            authors = ', '.join(author_list[:3] + ['...'] + author_list[-2:])
        if p.affiliations is not None:
            affiliations = p.affiliations[:5]
            affiliations = ', '.join(affiliations)
            if len(p.affiliations) > 5:
                affiliations += ', ...'
        else:
            affiliations = 'Unknown Affiliation'
        parts.append(get_block_html(p.title, authors, rate, p.tldr, p.pdf_url, affiliations, p.analysis, p.abstract))

    content = '<br>' + '</br><br>'.join(parts) + '</br>'
    return framework.replace('__CONTENT__', content)
