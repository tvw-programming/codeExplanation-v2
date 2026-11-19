/**
 * Publishes, for every staged stack, where each source file's
 * explanation sits inside that stack's video.
 *
 *   run: npx --yes tsx scripts/build-segment-index.ts
 *   (run-local.sh does this for you, right after the pipeline stages
 *   its chunks and before the videos are rendered)
 *
 * Reads  render-app/public/chunks/<stack>/manifest.json
 *        render-app/public/chunks/<stack>/<chunkId>/bundle.json
 * Writes render-app/public/chunks/<stack>/segments.json
 *
 * The viewer frontend uses segments.json to jump straight to a clicked
 * file: `video.currentTime = startSeconds`, stop at `endSeconds`. The
 * offsets are computed by segmentTiming.ts — the same module
 * FullVideo.tsx lays the real <Series> out with — so they describe the
 * rendered mp4 rather than approximating it.
 *
 * Manifest order is authoritative: run_backend_pilot.py puts
 * visual-bearing chunks first (_prioritize_visual_chunks), and that is
 * the order the video plays them in.
 */
import fs from "node:fs";
import path from "node:path";
import {
  CHAPTER_LABELS,
  FPS,
  framesToSeconds,
  segmentsForStack,
  type ChapterKind,
  type TimingBundle,
} from "../src/segmentTiming";

const CHUNKS_DIR = path.resolve(__dirname, "..", "public", "chunks");

type Bundle = TimingBundle & {
  fileOverview?: {
    fileName?: string;
    filePath?: string;
    purpose?: string;
    layer?: string;
    language?: string;
    feature?: string;
    lineCount?: number;
  } | null;
  visualTheme?: StackTheme | null;
};

/** Brand tokens for the stack, lifted off the first bundle that has
 *  them so the viewer can colour a stack's section without opening a
 *  bundle of its own (see src/visual/theme.py for the source values). */
export type StackTheme = {
  stack?: string;
  primary?: string;
  secondary?: string;
  onDark?: string;
  logoPath?: string | null;
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
  chapters: { kind: ChapterKind; label: string; startSeconds: number; endSeconds: number }[];
};

export type SegmentIndex = {
  stack: string;
  fps: number;
  /** Composition this index describes, so a consumer can tell which
   *  render produced the video it is seeking into. */
  composition: string;
  video: string;
  previewVideo: string;
  totalSeconds: number;
  generatedAt: string;
  theme: StackTheme | null;
  files: SegmentFile[];
};

function readJson<T>(file: string): T | null {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8")) as T;
  } catch {
    return null;
  }
}

/** Every stack directory that carries a manifest (i.e. was staged). */
export function stackDirs(chunksDir: string = CHUNKS_DIR): string[] {
  if (!fs.existsSync(chunksDir)) return [];
  return fs
    .readdirSync(chunksDir, { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => e.name)
    .filter((name) => fs.existsSync(path.join(chunksDir, name, "manifest.json")))
    .sort();
}

export function buildIndexForStack(
  stack: string,
  chunksDir: string = CHUNKS_DIR,
): SegmentIndex | null {
  const stackDir = path.join(chunksDir, stack);
  const manifest = readJson<{ chunkIds?: string[] }>(path.join(stackDir, "manifest.json"));
  if (!manifest?.chunkIds?.length) return null;

  const bundles = new Map<string, Bundle>();
  for (const chunkId of manifest.chunkIds) {
    const bundle = readJson<Bundle>(path.join(stackDir, chunkId, "bundle.json"));
    if (bundle) bundles.set(chunkId, bundle);
  }

  const { segments, totalFrames } = segmentsForStack(
    manifest.chunkIds,
    (id) => bundles.get(id) ?? null,
  );

  const files: SegmentFile[] = segments.map((segment) => {
    const bundle = bundles.get(segment.chunkId)!;
    const overview = bundle.fileOverview ?? null;
    const filePath = overview?.filePath ?? bundle.filePath ?? segment.chunkId;
    return {
      chunkId: segment.chunkId,
      filePath,
      fileName: overview?.fileName ?? path.basename(filePath),
      featureName: bundle.featureName ?? overview?.feature ?? null,
      language: overview?.language ?? null,
      layer: overview?.layer ?? null,
      purpose: overview?.purpose ?? null,
      lineCount: overview?.lineCount ?? null,
      startSeconds: framesToSeconds(segment.startFrame),
      endSeconds: framesToSeconds(segment.endFrame),
      chapters: segment.chapters.map((chapter) => ({
        kind: chapter.kind,
        label: CHAPTER_LABELS[chapter.kind],
        startSeconds: framesToSeconds(chapter.startFrame),
        endSeconds: framesToSeconds(chapter.endFrame),
      })),
    };
  });

  return {
    stack,
    fps: FPS,
    composition: `StackVideo-${stack}`,
    video: `video-${stack}.mp4`,
    previewVideo: `video-${stack}-preview.mp4`,
    totalSeconds: framesToSeconds(totalFrames),
    generatedAt: new Date().toISOString(),
    theme:
      [...bundles.values()].map((b) => b.visualTheme).find((t) => t?.primary) ?? null,
    files,
  };
}

function main(): number {
  const stacks = stackDirs();
  if (stacks.length === 0) {
    console.error(
      "[segment-index] No staged stacks under render-app/public/chunks/ — " +
        "run the backend pipeline first (./run-local.sh --backend-only).",
    );
    return 1;
  }

  for (const stack of stacks) {
    const index = buildIndexForStack(stack);
    if (!index) {
      console.error(`[segment-index] ${stack}: manifest empty or unreadable — skipped.`);
      continue;
    }
    const out = path.join(CHUNKS_DIR, stack, "segments.json");
    fs.writeFileSync(out, JSON.stringify(index, null, 2) + "\n", "utf8");
    console.log(
      `[segment-index] ${stack}: ${index.files.length} file(s), ` +
        `${index.totalSeconds.toFixed(1)}s -> ${path.relative(process.cwd(), out)}`,
    );
  }
  return 0;
}

if (require.main === module) {
  process.exit(main());
}
