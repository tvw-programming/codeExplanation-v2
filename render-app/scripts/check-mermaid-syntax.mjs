#!/usr/bin/env node
/**
 * CI gate: parse every exported Mermaid fence / interactive field.
 *
 * Sources (under repo root):
 *   - visuals/.../architecture.md  (fenced mermaid blocks)
 *   - visuals/.../interactive.json (mermaid, mermaidLifecycle)
 *   - documentation and render-app/public/docs markdown fences
 *
 * Run from render-app: node scripts/check-mermaid-syntax.mjs
 * Exit 0 when all parse; non-zero with per-fence errors otherwise.
 *
 * Mermaid 11 parse() needs a DOM (DOMPurify). We boot jsdom first.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

const __dirname = dirname(fileURLToPath(import.meta.url));
const RENDER_APP = join(__dirname, "..");
const REPO_ROOT = join(RENDER_APP, "..");

const FENCE_RE = /```mermaid\s*\n([\s\S]*?)```/gi;

function installDom() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    pretendToBeVisual: true,
    url: "https://cev.local/",
  });
  const { window } = dom;
  globalThis.window = window;
  globalThis.document = window.document;
  globalThis.DOMParser = window.DOMParser;
  globalThis.HTMLElement = window.HTMLElement;
  globalThis.SVGElement = window.SVGElement;
  globalThis.Element = window.Element;
  globalThis.Node = window.Node;
  globalThis.getComputedStyle = window.getComputedStyle.bind(window);
  try {
    globalThis.navigator = window.navigator;
  } catch {
    // Node 22+: navigator is a read-only getter on globalThis
  }
}

function walk(dir, pred, out = []) {
  let entries;
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const name of entries) {
    if (name === "node_modules" || name === ".git" || name === "dist" || name === "out") {
      continue;
    }
    const full = join(dir, name);
    let st;
    try {
      st = statSync(full);
    } catch {
      continue;
    }
    if (st.isDirectory()) walk(full, pred, out);
    else if (pred(full, name)) out.push(full);
  }
  return out;
}

function collectFromMarkdown(path) {
  const text = readFileSync(path, "utf8");
  const items = [];
  let m;
  const re = new RegExp(FENCE_RE.source, FENCE_RE.flags);
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    i += 1;
    items.push({
      source: `${relative(REPO_ROOT, path)}#fence-${i}`,
      text: m[1].trim(),
    });
  }
  return items;
}

function collectFromInteractive(path) {
  const raw = JSON.parse(readFileSync(path, "utf8"));
  const items = [];
  for (const key of ["mermaid", "mermaidLifecycle"]) {
    const val = raw[key];
    if (typeof val === "string" && val.trim()) {
      items.push({
        source: `${relative(REPO_ROOT, path)}#${key}`,
        text: val.trim(),
      });
    }
  }
  return items;
}

function gather() {
  const items = [];
  for (const path of walk(join(REPO_ROOT, "visuals"), (_, n) => n === "architecture.md")) {
    items.push(...collectFromMarkdown(path));
  }
  for (const path of walk(join(REPO_ROOT, "visuals"), (_, n) => n === "interactive.json")) {
    items.push(...collectFromInteractive(path));
  }
  for (const root of [
    join(REPO_ROOT, "documentation"),
    join(REPO_ROOT, "render-app", "public", "docs"),
  ]) {
    for (const path of walk(root, (_, n) => n.endsWith(".md"))) {
      items.push(...collectFromMarkdown(path));
    }
  }
  return items;
}

async function main() {
  installDom();
  const { default: mermaid } = await import("mermaid");
  mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });

  const items = gather();
  if (items.length === 0) {
    console.log("check-mermaid-syntax: no Mermaid fences/fields found (ok).");
    return;
  }

  const failures = [];
  for (const item of items) {
    try {
      await mermaid.parse(item.text);
    } catch (err) {
      failures.push({
        source: item.source,
        message: err?.str || err?.message || String(err),
      });
    }
  }

  if (failures.length) {
    console.error(`check-mermaid-syntax: ${failures.length}/${items.length} failed`);
    for (const f of failures) {
      console.error(`  x ${f.source}`);
      console.error(`    ${f.message}`);
    }
    process.exit(1);
  }
  console.log(`check-mermaid-syntax: ${items.length} diagram(s) parsed OK`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
