const fs = require("fs");
const path = require("path");

const root = process.cwd();
const ua = path.join(root, ".ua");
const inter = path.join(ua, "intermediate");
const batches = JSON.parse(fs.readFileSync(path.join(inter, "batches.json"), "utf8")).batches;

function posixPath(p) {
  return p.replace(/\\/g, "/");
}

function fileType(file) {
  if (file.fileCategory === "docs") return "document";
  if (file.fileCategory === "config") return "config";
  if (file.fileCategory === "infra") {
    return file.path.includes(".github/workflows/") ? "pipeline" : "service";
  }
  return "file";
}

function idForFile(file) {
  return `${fileType(file)}:${posixPath(file.path)}`;
}

function complexity(lines) {
  if (lines >= 220) return "complex";
  if (lines >= 80) return "moderate";
  return "simple";
}

function nameFromPath(p) {
  return posixPath(p).split("/").pop();
}

function tagsForFile(file, result) {
  const tags = [file.language, file.fileCategory].filter(Boolean);
  const p = posixPath(file.path);
  if (p.startsWith("src/zotero_arxiv_daily/retriever/")) tags.push("retriever");
  if (p.startsWith("src/zotero_arxiv_daily/reranker/")) tags.push("reranker");
  if (p.includes("executor")) tags.push("pipeline");
  if (p.includes("protocol")) tags.push("data-model");
  if (p.startsWith("tests/")) tags.push("test");
  if (p.startsWith("config/")) tags.push("configuration");
  if (p.startsWith(".github/workflows/")) tags.push("github-actions");
  if ((result.classes || []).length) tags.push("classes");
  if ((result.functions || []).length) tags.push("functions");
  return [...new Set(tags.filter(Boolean))];
}

function summaryForFile(file, result) {
  const p = posixPath(file.path);
  const cls = (result.classes || []).map(c => c.name);
  const fns = (result.functions || []).map(f => f.name);
  if (p === "src/zotero_arxiv_daily/main.py") return "Hydra entry point that loads configuration and starts the daily recommendation executor.";
  if (p.endsWith("executor.py")) return "Coordinates the Zotero fetch, source retrieval, reranking, TLDR generation, email rendering, and SMTP delivery pipeline.";
  if (p.endsWith("protocol.py")) return "Defines Paper and CorpusPaper models, including LLM-backed TLDR and affiliation generation methods.";
  if (p.includes("/retriever/")) return "Implements paper retrieval abstractions and source-specific retrievers for arXiv, bioRxiv, and medRxiv.";
  if (p.includes("/reranker/")) return "Implements embedding-based reranking over candidate papers using local models or OpenAI-compatible APIs.";
  if (p.endsWith("construct_email.py")) return "Renders selected paper recommendations into the HTML email body.";
  if (p.endsWith("utils.py")) return "Provides shared helpers for paths, glob matching, GitHub URL discovery, caching, and subprocess timeouts.";
  if (p.startsWith("tests/")) return "Test support or pytest coverage for the recommendation pipeline and its utility modules.";
  if (file.fileCategory === "docs") return "Documentation asset describing usage, setup, project behavior, or repository guidance.";
  if (file.fileCategory === "infra") return "GitHub Actions or deployment automation used to run tests or the daily paper digest workflow.";
  if (file.fileCategory === "config") return "Project configuration consumed by runtime, packaging, tests, or automation.";
  const parts = [];
  if (cls.length) parts.push(`classes: ${cls.slice(0, 4).join(", ")}`);
  if (fns.length) parts.push(`functions: ${fns.slice(0, 4).join(", ")}`);
  return parts.length ? `Python module containing ${parts.join("; ")}.` : `Project file ${p}.`;
}

function nodeBase(id, type, name, filePath, summary, tags, extra = {}) {
  return {
    id,
    type,
    name,
    filePath: posixPath(filePath),
    summary,
    tags: [...new Set(tags.filter(Boolean))],
    complexity: extra.complexity || "simple",
    ...extra,
  };
}

function edge(source, target, type, weight, description) {
  return { source, target, type, weight, description };
}

for (const batch of batches) {
  const structure = JSON.parse(fs.readFileSync(path.join(inter, `structure-${batch.batchIndex}.json`), "utf8"));
  const byPath = new Map(structure.results.map(r => [posixPath(r.path), r]));
  const nodes = [];
  const edges = [];
  const symbolToIds = new Map();

  for (const file of batch.files) {
    const p = posixPath(file.path);
    const result = byPath.get(p) || { path: p };
    const fid = idForFile(file);
    nodes.push(nodeBase(
      fid,
      fileType(file),
      nameFromPath(p),
      p,
      summaryForFile(file, result),
      tagsForFile(file, result),
      {
        language: file.language,
        startLine: 1,
        endLine: result.totalLines || file.sizeLines || 1,
        sizeLines: result.totalLines || file.sizeLines || 0,
        complexity: complexity(result.totalLines || file.sizeLines || 0),
      },
    ));

    for (const cls of result.classes || []) {
      const cid = `class:${p}:${cls.name}`;
      symbolToIds.set(cls.name, cid);
      nodes.push(nodeBase(
        cid,
        "class",
        cls.name,
        p,
        `Class ${cls.name} in ${p}${cls.methods && cls.methods.length ? ` with methods ${cls.methods.slice(0, 5).join(", ")}` : ""}.`,
        ["class", file.language].concat(cls.methods || []),
        { startLine: cls.startLine || 1, endLine: cls.endLine || cls.startLine || 1, complexity: complexity((cls.endLine || 0) - (cls.startLine || 0)) },
      ));
      edges.push(edge(fid, cid, "contains", 1.0, `${nameFromPath(p)} defines class ${cls.name}.`));

      for (const method of cls.methods || []) {
        const mid = `function:${p}:${cls.name}.${method}`;
        symbolToIds.set(`${cls.name}.${method}`, mid);
        nodes.push(nodeBase(
          mid,
          "function",
          `${cls.name}.${method}`,
          p,
          `Method ${method} on class ${cls.name}.`,
          ["method", "function", file.language],
          { startLine: cls.startLine || 1, endLine: cls.endLine || cls.startLine || 1, complexity: "simple" },
        ));
        edges.push(edge(cid, mid, "contains", 1.0, `Class ${cls.name} contains method ${method}.`));
      }
    }

    for (const fn of result.functions || []) {
      const fnid = `function:${p}:${fn.name}`;
      symbolToIds.set(fn.name, fnid);
      nodes.push(nodeBase(
        fnid,
        "function",
        fn.name,
        p,
        `Function ${fn.name}${fn.params && fn.params.length ? ` with parameters ${fn.params.join(", ")}` : ""}.`,
        ["function", file.language],
        { startLine: fn.startLine || 1, endLine: fn.endLine || fn.startLine || 1, complexity: complexity((fn.endLine || 0) - (fn.startLine || 0)) },
      ));
      edges.push(edge(fid, fnid, "contains", 1.0, `${nameFromPath(p)} defines function ${fn.name}.`));
    }
  }

  for (const [sourcePath, targets] of Object.entries(batch.batchImportData || {})) {
    const sourceFile = batch.files.find(f => posixPath(f.path) === posixPath(sourcePath));
    if (!sourceFile) continue;
    const sid = idForFile(sourceFile);
    for (const targetPath of targets || []) {
      const targetFile = batch.files.find(f => posixPath(f.path) === posixPath(targetPath));
      const tid = targetFile ? idForFile(targetFile) : `file:${posixPath(targetPath)}`;
      edges.push(edge(sid, tid, "imports", 0.7, `${sourcePath} imports ${targetPath}.`));
      if (posixPath(sourcePath).startsWith("tests/") && !posixPath(targetPath).startsWith("tests/")) {
        edges.push(edge(sid, tid, "tested_by", 0.5, `${sourcePath} tests ${targetPath}.`));
      }
    }
  }

  for (const file of batch.files) {
    const p = posixPath(file.path);
    const result = byPath.get(p) || {};
    for (const call of result.callGraph || []) {
      const caller = symbolToIds.get(call.caller) || symbolToIds.get(call.caller?.replace("self.", ""));
      if (!caller) continue;
      const calleeName = String(call.callee || "").replace(/^self\./, "").split("(")[0];
      const callee = symbolToIds.get(calleeName) || symbolToIds.get(calleeName.split(".").pop());
      if (callee && caller !== callee) {
        edges.push(edge(caller, callee, "calls", 0.8, `${call.caller} calls ${call.callee}.`));
      }
    }
  }

  fs.writeFileSync(path.join(inter, `batch-${batch.batchIndex}.json`), JSON.stringify({ nodes, edges }, null, 2));
  console.log(`batch-${batch.batchIndex}.json nodes=${nodes.length} edges=${edges.length}`);
}
