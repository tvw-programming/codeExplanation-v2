/** Folding flat `filePath` strings into the folder tree the sidebar
 *  shows. Pure, so it is tested directly (fileTree.test.ts). */

import type { SegmentFile } from "./types";

export type TreeNode = {
  /** Unique within its stack: the full path from the repo root. */
  id: string;
  label: string;
  /** Folders have children; files carry the segment instead. */
  children?: TreeNode[];
  file?: SegmentFile;
};

function insert(roots: TreeNode[], file: SegmentFile): void {
  const parts = file.filePath.split("/").filter(Boolean);
  if (parts.length === 0) return;

  let level = roots;
  let prefix = "";

  for (let i = 0; i < parts.length - 1; i += 1) {
    prefix = prefix ? `${prefix}/${parts[i]}` : parts[i];
    let folder = level.find((node) => node.id === prefix && node.children);
    if (!folder) {
      folder = { id: prefix, label: parts[i], children: [] };
      level.push(folder);
    }
    level = folder.children!;
  }

  const leafPath = parts.join("/");
  // A chunk is one file, so a duplicate path would mean two segments
  // claiming the same file — keep the first and drop the rest rather
  // than showing a leaf that plays an arbitrary one of them.
  if (level.some((node) => node.id === leafPath && node.file)) return;
  level.push({ id: leafPath, label: parts[parts.length - 1], file });
}

function sortLevel(nodes: TreeNode[]): TreeNode[] {
  nodes.sort((a, b) => {
    const aIsFolder = Boolean(a.children);
    const bIsFolder = Boolean(b.children);
    if (aIsFolder !== bIsFolder) return aIsFolder ? -1 : 1;
    return a.label.localeCompare(b.label);
  });
  for (const node of nodes) {
    if (node.children) sortLevel(node.children);
  }
  return nodes;
}

/** Folders first, then files, alphabetical within each — the ordering a
 *  file explorer uses, rather than the video's play order, because the
 *  sidebar is for finding a file, not for following the narration. */
export function buildFileTree(files: SegmentFile[]): TreeNode[] {
  const roots: TreeNode[] = [];
  for (const file of files) insert(roots, file);
  return sortLevel(roots);
}

/** Collapses single-child folder chains (`api/internal/handler` as one
 *  row) so a deep repo does not need five clicks to reach a file. */
export function collapseChains(nodes: TreeNode[]): TreeNode[] {
  return nodes.map((node) => {
    if (!node.children) return node;
    let current = node;
    let label = node.label;
    while (current.children && current.children.length === 1 && current.children[0].children) {
      current = current.children[0];
      label = `${label}/${current.label}`;
    }
    return { ...current, label, children: collapseChains(current.children ?? []) };
  });
}

/** Every folder id in the tree — what the sidebar expands by default,
 *  since the point is to see the whole repo at a glance. */
export function allFolderIds(nodes: TreeNode[]): string[] {
  const ids: string[] = [];
  const walk = (level: TreeNode[]) => {
    for (const node of level) {
      if (node.children) {
        ids.push(node.id);
        walk(node.children);
      }
    }
  };
  walk(nodes);
  return ids;
}
