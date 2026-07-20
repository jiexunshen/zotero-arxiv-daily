# zotero-arxiv-daily fork modifications

This repository is a customized fork of the original `zotero-arxiv-daily`.

The README only documents what this fork changes on top of the upstream project. For the original project usage, architecture, and baseline setup, refer to the upstream repository.

## Main Changes

### 1. Richer Paper Analysis Email

The email no longer only contains `Relevance` and `TLDR`.

For each recommended paper, this fork adds:

- English title plus Chinese title translation.
- English abstract plus Chinese abstract translation.
- Zotero collection recommendation based on the existing Zotero collection taxonomy.
- Explanation for why the paper matches the recommended collection.
- Four reading questions:
  - What problem does the paper try to solve?
  - How does it solve the problem?
  - What research inspiration can it bring?
  - Should it be read carefully, reproduced, followed up experimentally, or only skimmed?
- Publication information:
  - Venue in the format `full venue name - abbreviation - year - CCF or widely recognized rating - status`.
  - If no venue is available, the email says the paper is not yet published, includes the latest preprint update time, and asks the LLM to infer the likely target venue from the paper template and formatting.
  - First publication time, acceptance time, and publication time when available.
- Open-source information:
  - Whether a code repository is found.
  - GitHub repository URL when detected.
  - A black `Github` button next to the red `PDF` button when a repository URL exists.

### 2. Split Deep Analysis Requests

This fork supports a second LLM request for each selected paper:

```yaml
llm:
  split_deep_analysis_requests: true
```

The first request generates the structured result. The second request expands the interpretation so the analysis is less terse.

The merge logic preserves the initial Zotero category recommendation if the expansion response omits it, preventing the email from falling back to `Unknown`.

### 3. Zotero Taxonomy-Aware Category Recommendation

The LLM prompt now receives:

- Existing Zotero collection paths.
- Paper counts under each collection.
- Most similar papers from the user's Zotero library.

It should prefer an existing Zotero category. It may suggest a new category only when no existing category fits well, and must explain why the new category is needed.

### 4. arXiv Metadata Extraction

The arXiv retriever now passes additional metadata into the LLM analysis:

- `published`
- `updated`
- `journal_ref`
- `comment`
- detected GitHub repository URLs from abstract, paper text, or arXiv comments

These fields are used to generate publication and open-source sections in the email.

### 5. Local Email Preview Mode

This fork adds local preview support:

```yaml
executor:
  dry_run: true
  preview_email_path: outputs/email_preview.html
```

When `dry_run` is enabled, the app writes the rendered HTML email to `preview_email_path` and skips SMTP sending.

For GitHub Actions production email delivery, do not enable `dry_run`.

### 6. Bilingual Runtime Logs

Runtime logs are now bilingual Chinese-English, for example:

```text
正在获取 Zotero 文献库 | Fetching zotero corpus
正在生成深度解读 | Generating deep analysis
邮件发送成功 | Email sent successfully
```

This makes GitHub Actions logs easier to inspect while preserving the original English meaning.

### 7. Safer GitHub Actions Logging

The workflows no longer print the generated `config/custom.yaml` to Actions logs.

This avoids accidentally exposing sensitive values if `CUSTOM_CONFIG` is misconfigured.

The Zotero empty-corpus error log also avoids printing `api_key`.

### 8. GitHub Actions Base URL Configuration

`OPENAI_API_BASE` can be provided from either GitHub Actions Variables or Secrets:

```yaml
OPENAI_API_BASE: ${{ vars.OPENAI_API_BASE || secrets.OPENAI_API_BASE }}
```

This means the API base URL does not need to be hardcoded in `config/custom.yaml`.

## Recommended CUSTOM_CONFIG

Set `CUSTOM_CONFIG` as an Actions variable. It can follow the same structure as `config/custom.yaml`, but do not put real keys or passwords in it.

Use environment interpolation for sensitive values:

```yaml
zotero:
  user_id: ${oc.env:ZOTERO_ID}
  api_key: ${oc.env:ZOTERO_KEY}
  include_path: null
  ignore_path: null

email:
  sender: ${oc.env:SENDER}
  receiver: ${oc.env:RECEIVER}
  smtp_server: smtp.qq.com
  smtp_port: 465
  sender_password: ${oc.env:SENDER_PASSWORD}

llm:
  api:
    key: ${oc.env:OPENAI_API_KEY}
    base_url: ${oc.env:OPENAI_API_BASE}
  language: Chinese
  enable_deep_analysis: true
  split_deep_analysis_requests: true
  analysis_top_k_similar: 5
  generation_kwargs:
    model: deepseek-v4-flash

source:
  arxiv:
    category: ["cs.AI", "cs.CV", "cs.LG", "cs.CL"]

executor:
  debug: false
  source: ["arxiv"]
  reranker: api
  max_paper_num: 1

reranker:
  api:
    key: ${oc.env:OPENAI_API_KEY}
    base_url: ${oc.env:OPENAI_API_BASE}
    model: bge-large-zh:latest
    batch_size: 64
```

For local preview only, add:

```yaml
executor:
  dry_run: true
  preview_email_path: outputs/email_preview.html
```

Do not use `dry_run: true` in GitHub Actions if you expect an email to be sent.

## Required Secrets and Variables

Repository secrets:

- `ZOTERO_ID`
- `ZOTERO_KEY`
- `SENDER`
- `RECEIVER`
- `SENDER_PASSWORD`
- `OPENAI_API_KEY`
- `OPENAI_API_BASE` if you choose to keep the base URL secret

Repository variables:

- `CUSTOM_CONFIG`
- `OPENAI_API_BASE` if you choose to store the base URL as a normal variable

## Test Workflow Note

You do not need to recreate the workflow.

If a GitHub Actions email still only shows `Relevance` and `TLDR`, check:

1. The workflow is running a commit that includes this fork's latest changes.
2. `CUSTOM_CONFIG` contains:

```yaml
llm:
  enable_deep_analysis: true
```

3. `dry_run` is not enabled if you expect an email.
4. The Actions log contains:

```text
正在生成深度解读
Generating deep analysis
```

If that log line is missing, the deep-analysis path did not run.
