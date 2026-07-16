const fs = require("fs");
const path = require("path");
const cp = require("child_process");

const root = process.cwd();
const ua = path.join(root, ".ua");
const inter = path.join(ua, "intermediate");
const scan = JSON.parse(fs.readFileSync(path.join(inter, "scan-result.json"), "utf8"));
const assembled = JSON.parse(fs.readFileSync(path.join(inter, "assembled-graph.json"), "utf8"));
const commit = cp.execSync("git rev-parse HEAD", { encoding: "utf8" }).trim();

function fileNodes() {
  const fileLevel = new Set(["file", "config", "document", "service", "pipeline", "table", "schema", "resource", "endpoint"]);
  return assembled.nodes.filter(n => fileLevel.has(n.type));
}

function byPath() {
  const m = new Map();
  for (const n of fileNodes()) m.set((n.filePath || "").replace(/\\/g, "/"), n);
  return m;
}

const nodesByPath = byPath();
function idsWhere(pred) {
  return fileNodes().filter(n => pred((n.filePath || "").replace(/\\/g, "/"), n)).map(n => n.id);
}
function id(p) {
  return nodesByPath.get(p)?.id;
}
function cleanIds(ids) {
  return [...new Set(ids.filter(Boolean))];
}

const layers = [
  {
    id: "layer:runtime-pipeline",
    name: "运行入口与编排",
    description: "应用入口、Executor 编排器、邮件渲染和贯穿全流程的运行时模块。",
    nodeIds: cleanIds(idsWhere(p =>
      p === "src/zotero_arxiv_daily/main.py" ||
      p === "src/zotero_arxiv_daily/executor.py" ||
      p === "src/zotero_arxiv_daily/construct_email.py" ||
      p === "src/zotero_arxiv_daily/__init__.py"
    )),
  },
  {
    id: "layer:data-models-and-utilities",
    name: "数据模型与工具",
    description: "Paper/CorpusPaper 数据结构、共享工具函数，以及项目根部的 Python 元数据。",
    nodeIds: cleanIds(idsWhere(p =>
      p === "src/zotero_arxiv_daily/protocol.py" ||
      p === "src/zotero_arxiv_daily/utils.py" ||
      p === ".python-version"
    )),
  },
  {
    id: "layer:retrievers",
    name: "论文源检索",
    description: "Retriever 插件注册机制，以及 arXiv、bioRxiv、medRxiv 的来源适配器。",
    nodeIds: cleanIds(idsWhere(p => p.startsWith("src/zotero_arxiv_daily/retriever/"))),
  },
  {
    id: "layer:rerankers",
    name: "相似度重排",
    description: "Reranker 插件注册机制，以及本地 sentence-transformers 与 OpenAI-compatible embedding API 两条实现路径。",
    nodeIds: cleanIds(idsWhere(p => p.startsWith("src/zotero_arxiv_daily/reranker/"))),
  },
  {
    id: "layer:configuration-and-automation",
    name: "配置与自动化",
    description: "Hydra 配置、项目打包配置、GitHub Actions 工作流和测试辅助服务定义。",
    nodeIds: cleanIds(idsWhere(p =>
      p.startsWith("config/") ||
      p === "pyproject.toml" ||
      p === ".github/FUNDING.yml" ||
      p.startsWith(".github/workflows/") ||
      p.startsWith("tests/utils/")
    )),
  },
  {
    id: "layer:tests",
    name: "测试套件",
    description: "pytest 单元测试、fixture、mock 响应和各子系统的回归测试。",
    nodeIds: cleanIds(idsWhere(p => p.startsWith("tests/") && !p.startsWith("tests/utils/"))),
  },
  {
    id: "layer:documentation",
    name: "文档与使用说明",
    description: "README、许可、Claude/Copilot 指南、保活说明和附加使用文档。",
    nodeIds: cleanIds(idsWhere(p =>
      p === "README.md" ||
      p === "CLAUDE.md" ||
      p === "LICENSE" ||
      p === ".github/copilot-instructions.md" ||
      p === ".github/keep-alive.txt" ||
      p.startsWith("assets/")
    )),
  },
];

const assigned = new Set(layers.flatMap(l => l.nodeIds));
const fallback = fileNodes().filter(n => !assigned.has(n.id)).map(n => n.id);
if (fallback.length) {
  layers.push({
    id: "layer:miscellaneous",
    name: "其他项目文件",
    description: "未落入主要运行、配置、测试或文档层的辅助文件。",
    nodeIds: fallback,
  });
}

const tour = [
  {
    order: 1,
    title: "项目目标与使用方式",
    description: "从 README 开始理解这个仓库如何根据 Zotero library 推荐每日新论文，并通过 GitHub Actions 低成本运行。",
    nodeIds: cleanIds([id("README.md"), id("config/base.yaml"), id("config/custom.yaml")]),
  },
  {
    order: 2,
    title: "应用启动路径",
    description: "查看 Hydra 入口如何加载配置，并把执行权交给 Executor。",
    nodeIds: cleanIds([id("src/zotero_arxiv_daily/main.py"), id("src/zotero_arxiv_daily/executor.py")]),
  },
  {
    order: 3,
    title: "核心数据对象",
    description: "理解 Paper 和 CorpusPaper 如何承载检索结果、Zotero 语料、评分、TLDR 和 affiliation。",
    nodeIds: cleanIds([id("src/zotero_arxiv_daily/protocol.py")]),
  },
  {
    order: 4,
    title: "候选论文检索",
    description: "沿着 retriever base 与各来源实现，了解 arXiv RSS、bioRxiv 和 medRxiv 如何转换成统一 Paper。",
    nodeIds: cleanIds([
      id("src/zotero_arxiv_daily/retriever/base.py"),
      id("src/zotero_arxiv_daily/retriever/arxiv_retriever.py"),
      id("src/zotero_arxiv_daily/retriever/biorxiv_retriever.py"),
      id("src/zotero_arxiv_daily/retriever/medrxiv_retriever.py"),
    ]),
  },
  {
    order: 5,
    title: "相关性排序",
    description: "比较本地 embedding 和 API embedding 两种 reranker 如何按 Zotero 语料相似度重排候选论文。",
    nodeIds: cleanIds([
      id("src/zotero_arxiv_daily/reranker/base.py"),
      id("src/zotero_arxiv_daily/reranker/local.py"),
      id("src/zotero_arxiv_daily/reranker/api.py"),
    ]),
  },
  {
    order: 6,
    title: "邮件输出与自动运行",
    description: "查看 HTML 邮件构造和 GitHub Actions 工作流，串起每日推荐的交付路径。",
    nodeIds: cleanIds([
      id("src/zotero_arxiv_daily/construct_email.py"),
      id(".github/workflows/main.yml"),
      id(".github/workflows/ci.yml"),
    ]),
  },
  {
    order: 7,
    title: "测试与回归保护",
    description: "通过 pytest 覆盖理解 retriever、reranker、协议对象、邮件渲染和工具函数的关键行为。",
    nodeIds: cleanIds(idsWhere(p => p.startsWith("tests/")).slice(0, 8)),
  },
];

const finalGraph = {
  version: "1.0.0",
  project: {
    name: scan.projectName || "zotero-arxiv-daily",
    languages: scan.languages || Object.keys(scan.stats?.byLanguage || {}),
    frameworks: scan.frameworks || ["Hydra", "pytest", "GitHub Actions"],
    description: scan.projectDescription || "Daily paper recommendation pipeline based on Zotero libraries.",
    analyzedAt: new Date().toISOString(),
    gitCommitHash: commit,
  },
  nodes: assembled.nodes,
  edges: assembled.edges,
  layers,
  tour,
};

fs.writeFileSync(path.join(inter, "assembled-graph.json"), JSON.stringify(finalGraph, null, 2));
fs.writeFileSync(path.join(ua, "knowledge-graph.json"), JSON.stringify(finalGraph, null, 2));
console.log(JSON.stringify({
  nodes: finalGraph.nodes.length,
  edges: finalGraph.edges.length,
  layers: finalGraph.layers.length,
  tour: finalGraph.tour.length,
}, null, 2));
