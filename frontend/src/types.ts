/** Shapes the pipeline publishes under /data. Each one has a producer
 *  in this repo — keep them in step with it:
 *
 *   project.json  <- src/pilot/project_manifest.py
 *   status.json   <- src/pilot/status.py
 *   segments.json <- render-app/scripts/build-segment-index.ts
 */

export type StackRole = "frontend" | "backend" | "other";

export type ProjectStack = {
  name: string;
  role: StackRole;
  chunkCount: number;
  video: string;
  previewVideo: string;
  composition: string;
};

export type ProjectManifest = {
  schemaVersion: number;
  repoName: string;
  repoRoot: string;
  projectType: {
    frontend?: string | null;
    backend?: string[];
    architecture?: string;
    dockerized?: boolean;
  };
  stacks: ProjectStack[];
  generatedAt: string;
};

export type PipelineStatus = {
  schemaVersion: number;
  phase: string;
  phaseLabel: string;
  startedAt: string;
  updatedAt: string;
  source: string | null;
  renderEnabled: boolean;
  chunksTotal: number;
  chunksRendered: number;
  stacks: string[];
  videos: Record<string, { composition: string; file: string; ready: boolean }>;
  done: boolean;
  error: string | null;
};

export type ChapterKind = "card" | "tree" | "lifecycle" | "code" | "breakdown";

export type Chapter = {
  kind: ChapterKind;
  label: string;
  startSeconds: number;
  endSeconds: number;
};

export type SegmentFile = {
  chunkId: string;
  filePath: string;
  fileName: string;
  featureName: string | null;
  language: string | null;
  layer: string | null;
  purpose: string | null;
  lineCount: number | null;
  startSeconds: number;
  endSeconds: number;
  chapters: Chapter[];
};

export type StackTheme = {
  stack?: string;
  primary?: string;
  secondary?: string;
  onDark?: string;
  logoPath?: string | null;
};

export type SegmentIndex = {
  stack: string;
  fps: number;
  composition: string;
  video: string;
  previewVideo: string;
  totalSeconds: number;
  generatedAt: string;
  theme: StackTheme | null;
  files: SegmentFile[];
};

/** The full picture for one stack: what the pipeline said about it,
 *  plus which video file is actually playable right now. */
export type StackView = {
  stack: ProjectStack;
  index: SegmentIndex | null;
  /** Resolved video URL under /data/videos, or null while none exists. */
  videoUrl: string | null;
  /** True when only the --preview render is available. */
  isPreview: boolean;
  /** Seconds the preview covers, when `isPreview`. */
  previewSeconds: number | null;
};

/** What the file overview panel reads out of a staged bundle.json. */
export type FileOverview = {
  fileName?: string;
  filePath?: string;
  purpose?: string;
  purposeFull?: string;
  fileType?: string;
  layer?: string;
  feature?: string;
  language?: string;
  frameworks?: string[];
  libraries?: string[];
  exports?: string[];
  contains?: { name?: string; kind?: string; lineRange?: number[] }[];
  routes?: { method?: string; path?: string }[];
  callers?: string[];
  callees?: string[];
  sideEffects?: string[];
  risks?: string[];
  tests?: string[];
  lineCount?: number;
  unavailable?: Record<string, string>;
};
