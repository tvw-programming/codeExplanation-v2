import { describe, expect, it } from "vitest";

import {
  BOUNDARY_EPSILON,
  chapterAt,
  findFile,
  formatDuration,
  formatTime,
  isPlayable,
  isReachable,
  looksLikePreview,
  progressWithin,
  seekTarget,
  shouldPause,
  stopAt,
} from "./segments";
import type { SegmentFile, SegmentIndex } from "./types";

/** Modelled on the real go index: main.go then middleware.go. */
const mainGo: SegmentFile = {
  chunkId: "server-91d1514b",
  filePath: "api/cmd/server/main.go",
  fileName: "main.go",
  featureName: "server",
  language: "go",
  layer: "server",
  purpose: "Boots the Fiber app",
  lineCount: 120,
  startSeconds: 0,
  endSeconds: 217.867,
  chapters: [
    { kind: "card", label: "File card", startSeconds: 0, endSeconds: 17.4 },
    { kind: "tree", label: "Structure", startSeconds: 17.4, endSeconds: 25.4 },
    { kind: "lifecycle", label: "Lifecycle", startSeconds: 25.4, endSeconds: 37.4 },
    { kind: "code", label: "Code walkthrough", startSeconds: 37.4, endSeconds: 212.867 },
    { kind: "breakdown", label: "Breakdown", startSeconds: 212.867, endSeconds: 217.867 },
  ],
};

const middlewareGo: SegmentFile = {
  ...mainGo,
  chunkId: "firebaseauth-abb3598a",
  filePath: "api/internal/firebaseauth/middleware.go",
  fileName: "middleware.go",
  startSeconds: 217.867,
  endSeconds: 392.667,
  chapters: [
    { kind: "card", label: "File card", startSeconds: 217.867, endSeconds: 230.0 },
    { kind: "code", label: "Code walkthrough", startSeconds: 230.0, endSeconds: 392.667 },
  ],
};

const index: SegmentIndex = {
  stack: "go",
  fps: 30,
  composition: "StackVideo-go",
  video: "video-go.mp4",
  previewVideo: "video-go-preview.mp4",
  totalSeconds: 1591.3,
  generatedAt: "2026-11-19T00:00:00Z",
  theme: null,
  files: [mainGo, middlewareGo],
};

describe("findFile", () => {
  it("finds the clicked file by path", () => {
    expect(findFile(index, "api/internal/firebaseauth/middleware.go")?.startSeconds).toBe(
      217.867,
    );
  });

  it("returns null for an unknown path or a missing index", () => {
    expect(findFile(index, "nope.go")).toBeNull();
    expect(findFile(null, "api/cmd/server/main.go")).toBeNull();
    expect(findFile(index, null)).toBeNull();
  });
});

describe("chapterAt", () => {
  it("reports the chapter playing at a moment", () => {
    expect(chapterAt(mainGo, 30)?.kind).toBe("lifecycle");
    expect(chapterAt(mainGo, 0)?.kind).toBe("card");
  });

  it("treats a boundary as belonging to the later chapter", () => {
    expect(chapterAt(mainGo, 17.4)?.kind).toBe("tree");
  });

  it("returns null outside the file", () => {
    expect(chapterAt(mainGo, 400)).toBeNull();
    expect(chapterAt(null, 10)).toBeNull();
  });
});

describe("progressWithin", () => {
  it("measures progress through the selected file, not the whole video", () => {
    expect(progressWithin(middlewareGo, 217.867)).toBe(0);
    expect(progressWithin(middlewareGo, 392.667)).toBe(1);
    expect(progressWithin(middlewareGo, 305.267)).toBeCloseTo(0.5, 2);
  });

  it("clamps outside the file instead of going negative or past one", () => {
    expect(progressWithin(middlewareGo, 0)).toBe(0);
    expect(progressWithin(middlewareGo, 10_000)).toBe(1);
  });
});

describe("isPlayable", () => {
  it("is false until the video's length is known", () => {
    expect(isPlayable(middlewareGo, null)).toBe(false);
    expect(isPlayable(middlewareGo, Number.NaN)).toBe(false);
  });

  it("is true when the file starts inside the loaded video", () => {
    expect(isPlayable(middlewareGo, 1591.3)).toBe(true);
  });

  it("is false for a file past the end of a --preview render", () => {
    // ./run-local.sh --preview renders only the opening 120s.
    expect(isPlayable(mainGo, 120)).toBe(true);
    expect(isPlayable(middlewareGo, 120)).toBe(false);
  });
});

describe("looksLikePreview", () => {
  it("spots a video shorter than the full render", () => {
    expect(looksLikePreview(index, 120)).toBe(true);
  });

  it("does not cry preview over a rounding difference", () => {
    expect(looksLikePreview(index, 1591.0)).toBe(false);
    expect(looksLikePreview(index, 1592)).toBe(false);
  });

  it("says nothing without an index or a duration", () => {
    expect(looksLikePreview(null, 120)).toBe(false);
    expect(looksLikePreview(index, null)).toBe(false);
  });
});

describe("seekTarget", () => {
  it("seeks to the file's start", () => {
    expect(seekTarget(middlewareGo, 1591.3)).toBe(217.867);
  });

  it("seeks to a chapter when one is chosen", () => {
    expect(seekTarget(mainGo, 1591.3, mainGo.chapters[3])).toBe(37.4);
  });

  it("never seeks past the end of the video that exists", () => {
    expect(seekTarget(middlewareGo, 120)).toBeCloseTo(120 - BOUNDARY_EPSILON, 5);
  });

  it("uses the published start when the duration is unknown", () => {
    expect(seekTarget(middlewareGo, null)).toBe(217.867);
  });
});

describe("stopAt / shouldPause", () => {
  it("stops at the end of the selected file", () => {
    expect(stopAt(middlewareGo, { continuous: false })).toBe(392.667);
  });

  it("stops at the end of a chosen chapter", () => {
    expect(stopAt(mainGo, { continuous: false, chapter: mainGo.chapters[1] })).toBe(25.4);
  });

  it("does not stop when playing straight through the stack video", () => {
    expect(stopAt(middlewareGo, { continuous: true })).toBeNull();
    expect(shouldPause(10_000, null)).toBe(false);
  });

  it("pauses a hair early rather than spilling into the next file", () => {
    expect(shouldPause(392.667, 392.667)).toBe(true);
    expect(shouldPause(392.64, 392.667)).toBe(true);
    expect(shouldPause(392.0, 392.667)).toBe(false);
  });

  it("has nothing to stop with no file selected", () => {
    expect(stopAt(null, { continuous: false })).toBeNull();
  });
});

describe("formatting", () => {
  it("formats a position as mm:ss", () => {
    expect(formatTime(0)).toBe("0:00");
    expect(formatTime(217.867)).toBe("3:37");
    expect(formatTime(-1)).toBe("0:00");
    expect(formatTime(Number.NaN)).toBe("0:00");
  });

  it("formats a length readably", () => {
    expect(formatDuration(174.8)).toBe("2m 55s");
    expect(formatDuration(42)).toBe("42s");
    expect(formatDuration(0)).toBe("—");
  });
});

describe("isReachable", () => {
  it("marks a stack with no rendered video as waiting", () => {
    expect(isReachable(mainGo, { hasVideo: false, videoDuration: null })).toBe(false);
  });

  it("does not grey out a stack just because it is not the one loaded", () => {
    // Only the stack in the player reports a duration; the others must
    // not read as unavailable while their videos sit on disk.
    expect(isReachable(middlewareGo, { hasVideo: true, videoDuration: null })).toBe(true);
  });

  it("still greys out a file past the end of a --preview render", () => {
    expect(isReachable(middlewareGo, { hasVideo: true, videoDuration: 120 })).toBe(false);
    expect(isReachable(mainGo, { hasVideo: true, videoDuration: 120 })).toBe(true);
  });
});
