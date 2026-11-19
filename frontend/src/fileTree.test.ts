import { describe, expect, it } from "vitest";

import { allFolderIds, buildFileTree, collapseChains, type TreeNode } from "./fileTree";
import type { SegmentFile } from "./types";

function file(filePath: string): SegmentFile {
  const fileName = filePath.split("/").pop() ?? filePath;
  return {
    chunkId: filePath,
    filePath,
    fileName,
    featureName: null,
    language: null,
    layer: null,
    purpose: null,
    lineCount: null,
    startSeconds: 0,
    endSeconds: 1,
    chapters: [{ kind: "card", label: "File card", startSeconds: 0, endSeconds: 1 }],
  };
}

/** path -> label, for readable assertions. */
function shape(nodes: TreeNode[]): unknown {
  return nodes.map((node) =>
    node.children ? { [node.label]: shape(node.children) } : node.label,
  );
}

describe("buildFileTree", () => {
  it("folds paths into nested folders", () => {
    const tree = buildFileTree([
      file("api/internal/handler/alumni_handler.go"),
      file("api/internal/handler/media_handler.go"),
      file("api/cmd/server/main.go"),
    ]);

    expect(shape(tree)).toEqual([
      {
        api: [
          { cmd: [{ server: ["main.go"] }] },
          { internal: [{ handler: ["alumni_handler.go", "media_handler.go"] }] },
        ],
      },
    ]);
  });

  it("puts folders before files and sorts each level alphabetically", () => {
    const tree = buildFileTree([
      file("src/index.ts"),
      file("src/components/Button.tsx"),
      file("src/App.tsx"),
    ]);

    expect(shape(tree)).toEqual([
      { src: [{ components: ["Button.tsx"] }, "App.tsx", "index.ts"] },
    ]);
  });

  it("keeps a file at the repo root", () => {
    const tree = buildFileTree([file("main.go")]);

    expect(shape(tree)).toEqual(["main.go"]);
  });

  it("attaches the segment to its leaf, so a click knows what to play", () => {
    const target = file("api/cmd/server/main.go");
    target.startSeconds = 217.87;

    const tree = buildFileTree([target]);
    const leaf = tree[0].children![0].children![0].children![0];

    expect(leaf.file?.startSeconds).toBe(217.87);
  });

  it("ignores a second segment claiming the same path", () => {
    const first = file("a/b.go");
    first.chunkId = "first";
    const second = file("a/b.go");
    second.chunkId = "second";

    const tree = buildFileTree([first, second]);

    expect(tree[0].children).toHaveLength(1);
    expect(tree[0].children![0].file?.chunkId).toBe("first");
  });

  it("survives an empty index and a blank path", () => {
    expect(buildFileTree([])).toEqual([]);
    expect(buildFileTree([file("")])).toEqual([]);
  });
});

describe("collapseChains", () => {
  it("joins single-child folder chains into one row", () => {
    const tree = collapseChains(buildFileTree([file("api/internal/handler/alumni.go")]));

    expect(shape(tree)).toEqual([{ "api/internal/handler": ["alumni.go"] }]);
  });

  it("stops collapsing where a folder branches", () => {
    const tree = collapseChains(
      buildFileTree([file("api/cmd/server/main.go"), file("api/internal/x/y.go")]),
    );

    expect(shape(tree)).toEqual([
      { api: [{ "cmd/server": ["main.go"] }, { "internal/x": ["y.go"] }] },
    ]);
  });

  it("does not collapse a folder whose only child is a file", () => {
    const tree = collapseChains(buildFileTree([file("src/App.tsx")]));

    expect(shape(tree)).toEqual([{ src: ["App.tsx"] }]);
  });
});

describe("allFolderIds", () => {
  it("lists every folder so the sidebar can open the whole repo", () => {
    const tree = buildFileTree([file("a/b/c.go"), file("a/d.go")]);

    expect(allFolderIds(tree).sort()).toEqual(["a", "a/b"]);
  });

  it("returns nothing for a flat tree", () => {
    expect(allFolderIds(buildFileTree([file("main.go")]))).toEqual([]);
  });
});
