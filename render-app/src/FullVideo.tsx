import { CalculateMetadataFunction, Composition, Series, staticFile } from "remotion";
import { ThemeProvider } from "@mui/material/styles";
import { theme } from "../shared/theme";
import { ChunkView, bundleDurationInFrames, fetchBundle } from "./ChunkView";
import {
  FILE_CARD_TAIL_SECONDS,
  FileCard,
  MIN_FILE_CARD_SECONDS,
  type CardNarration,
  type FileOverview,
} from "./FileCard";
import {
  ComponentTreeClip,
  treeFramesFor,
  type ClipNarration,
  type SecurityFlag,
  type VisualGraph,
} from "./ComponentTreeClip";
import { LifecycleFlowClip, lifecycleFramesFor, type LifecycleFlow } from "./LifecycleFlowClip";
import { VisualBreakdownStill, breakdownFramesFor } from "./VisualBreakdownStill";
import type { VisualTheme } from "./visualTheme";

// Per-stack video isolation: the backend pipeline now stages chunks
// under public/chunks/<stack>/<chunkId>/ and writes a per-stack
// manifest at public/chunks/<stack>/manifest.json. Each stack gets
// its own Remotion composition ("StackVideo-<stack>") that renders
// only that stack's chunks into output/video-<stack>.mp4.
//
// The combined FullVideo composition is kept for backward compat —
// it reads the combined manifest at public/chunks/manifest.json
// and renders every chunk from every stack back-to-back.
//
// Segment order (Q1 A): FileCard → ComponentTreeClip → LifecycleFlowClip
// → ChunkView → VisualBreakdownStill. Q5 A: omit unavailable segments.

const FPS = 30;

/** A card stays up for as long as its narration takes to read, plus a
 *  short tail, and never less than the minimum — so the viewer is
 *  neither read a summary that has left the screen nor left waiting on
 *  a card after the audio has finished. */
function cardFramesFor(narration: CardNarration | null): number {
  const spoken = narration ? (narration.durationMs / 1000) + FILE_CARD_TAIL_SECONDS : 0;
  return Math.ceil(Math.max(MIN_FILE_CARD_SECONDS, spoken) * FPS);
}

// ---------- manifest types ----------

type StackManifest = { stack: string; chunkIds: string[] };

type CombinedManifest = {
  chunkIds: string[];
  stacks?: Record<string, string[]>;
};

type ChunkVisuals = {
  treeNarration: ClipNarration | null;
  treeFrames: number;
  lifecycleNarration: ClipNarration | null;
  lifecycleFrames: number;
  lifecycleFlows: LifecycleFlow[];
  breakdownNarration: ClipNarration | null;
  breakdownFrames: number;
  visualGraph: VisualGraph | null;
  visualTheme: VisualTheme | null;
  securityFlags: SecurityFlag[];
};

// ---------- shared loader ----------

async function loadChunks(chunkIds: string[], chunkDirPrefix: string) {
  const loaded = await Promise.all(
    chunkIds.map(async (id) => {
      const bundle = await fetchBundle(`${chunkDirPrefix}/${id}`) as typeof bundle & {
        fileOverview?: FileOverview;
        cardNarration?: CardNarration;
        treeNarration?: ClipNarration;
        lifecycleNarration?: ClipNarration;
        breakdownNarration?: ClipNarration;
        visualGraph?: VisualGraph;
        visualTheme?: VisualTheme;
        securityFlags?: SecurityFlag[];
        lifecycleFlows?: LifecycleFlow[];
      };
      const treeNarration = bundle.treeNarration ?? null;
      const lifecycleNarration = bundle.lifecycleNarration ?? null;
      const breakdownNarration = bundle.breakdownNarration ?? null;
      // Q5: only count frames when the narration artifact is present.
      const visuals: ChunkVisuals = {
        treeNarration,
        treeFrames: treeNarration && bundle.visualGraph ? treeFramesFor(treeNarration) : 0,
        lifecycleNarration,
        lifecycleFrames:
          lifecycleNarration && (bundle.lifecycleFlows?.length ?? 0) > 0
            ? lifecycleFramesFor(lifecycleNarration)
            : 0,
        lifecycleFlows: bundle.lifecycleFlows ?? [],
        breakdownNarration,
        breakdownFrames:
          breakdownNarration && bundle.visualGraph ? breakdownFramesFor(breakdownNarration) : 0,
        visualGraph: bundle.visualGraph ?? null,
        visualTheme: bundle.visualTheme ?? null,
        securityFlags: bundle.securityFlags ?? [],
      };
      return {
        duration: bundleDurationInFrames(bundle, FPS),
        overview: bundle.fileOverview ?? null,
        narration: bundle.cardNarration ?? null,
        visuals,
      };
    }),
  );
  return {
    durations: loaded.map((e) => e.duration),
    overviews: loaded.map((e) => e.overview),
    cardNarrations: loaded.map((e) => e.narration),
    cardDurations: loaded.map((e) => cardFramesFor(e.narration)),
    visuals: loaded.map((e) => e.visuals),
  };
}

function chunkTotalFrames(
  cardFrames: number,
  treeFrames: number,
  lifecycleFrames: number,
  chunkFrames: number,
  breakdownFrames: number,
): number {
  return cardFrames + treeFrames + lifecycleFrames + chunkFrames + breakdownFrames;
}

// ---------- shared props & component ----------

type VideoProps = {
  chunkIds?: string[];
  durations?: number[];
  overviews?: (FileOverview | null)[];
  cardNarrations?: (CardNarration | null)[];
  cardDurations?: number[];
  visuals?: ChunkVisuals[];
  /** Directory prefix where chunk subdirs live (e.g. "chunks" or
   *  "chunks/react"). Used to build the staticFile path for each chunk. */
  chunkDirPrefix?: string;
};

const VideoBody: React.FC<VideoProps> = ({
  chunkIds = [],
  durations = [],
  overviews = [],
  cardNarrations = [],
  cardDurations = [],
  visuals = [],
  chunkDirPrefix = "chunks",
}) => {
  if (chunkIds.length === 0) {
    return null;
  }

  return (
    <ThemeProvider theme={theme}>
      <Series>
        {chunkIds.flatMap((id, i) => {
          const overview = overviews[i];
          const narration = cardNarrations[i] ?? null;
          const cardFrames = cardDurations[i] ?? cardFramesFor(narration);
          const chunkFrames = Math.max(1, durations[i] ?? FPS);
          const v = visuals[i];
          const dir = `${chunkDirPrefix}/${id}`;
          const sequences = [
            <Series.Sequence key={`${id}-card`} durationInFrames={cardFrames}>
              {overview ? (
                <FileCard
                  overview={overview}
                  narration={narration}
                  chunkDir={dir}
                  position={{ index: i + 1, total: chunkIds.length }}
                  sectionSeconds={chunkFrames / FPS}
                  visualTheme={v?.visualTheme}
                />
              ) : null}
            </Series.Sequence>,
          ];

          // Q5 A: skip unavailable visual segments entirely (no placeholders).
          if (v?.treeFrames && v.visualGraph && v.treeNarration) {
            sequences.push(
              <Series.Sequence key={`${id}-tree`} durationInFrames={v.treeFrames}>
                <ComponentTreeClip
                  chunkDir={dir}
                  visualGraph={v.visualGraph}
                  visualTheme={v.visualTheme}
                  securityFlags={v.securityFlags}
                  narration={v.treeNarration}
                  filePath={overview?.filePath}
                />
              </Series.Sequence>,
            );
          }

          if (v?.lifecycleFrames && v.lifecycleFlows?.length && v.lifecycleNarration) {
            sequences.push(
              <Series.Sequence key={`${id}-lifecycle`} durationInFrames={v.lifecycleFrames}>
                <LifecycleFlowClip
                  chunkDir={dir}
                  flows={v.lifecycleFlows}
                  visualTheme={v.visualTheme}
                  securityFlags={v.securityFlags}
                  narration={v.lifecycleNarration}
                  filePath={overview?.filePath}
                />
              </Series.Sequence>,
            );
          }

          sequences.push(
            <Series.Sequence key={id} durationInFrames={chunkFrames}>
              <ChunkView
                chunkDir={dir}
                visualTheme={v?.visualTheme}
                filePath={overview?.filePath}
              />
            </Series.Sequence>,
          );

          if (v?.breakdownFrames && v.visualGraph && v.breakdownNarration) {
            sequences.push(
              <Series.Sequence key={`${id}-breakdown`} durationInFrames={v.breakdownFrames}>
                <VisualBreakdownStill
                  chunkDir={dir}
                  visualGraph={v.visualGraph}
                  visualTheme={v.visualTheme}
                  narration={v.breakdownNarration}
                  filePath={overview?.filePath}
                  securityFlags={v.securityFlags}
                />
              </Series.Sequence>,
            );
          }

          return sequences;
        })}
      </Series>
    </ThemeProvider>
  );
};

// ===================================================================
// Per-stack compositions: StackVideo-<stack>
// ===================================================================

/** Fetches the per-stack manifest from chunks/<stack>/manifest.json */
async function fetchStackManifest(stack: string): Promise<StackManifest> {
  const res = await fetch(staticFile(`chunks/${stack}/manifest.json`));
  return res.json();
}

/** Factory: returns a calculateMetadata function bound to a specific
 *  stack name, so each StackVideo composition loads only its own
 *  manifest and resolves bundles from its own subdirectory. */
function makeStackCalculateMetadata(
  stack: string,
): CalculateMetadataFunction<VideoProps> {
  return async () => {
    try {
      const manifest = await fetchStackManifest(stack);
      const chunkDirPrefix = `chunks/${stack}`;
      const { durations, overviews, cardNarrations, cardDurations, visuals } =
        await loadChunks(manifest.chunkIds, chunkDirPrefix);

      const total = durations.reduce(
        (sum, d, i) =>
          sum +
          chunkTotalFrames(
            cardDurations[i],
            visuals[i]?.treeFrames ?? 0,
            visuals[i]?.lifecycleFrames ?? 0,
            d,
            visuals[i]?.breakdownFrames ?? 0,
          ),
        0,
      );
      return {
        durationInFrames: Math.max(1, total),
        props: {
          chunkIds: manifest.chunkIds,
          durations,
          overviews,
          cardNarrations,
          cardDurations,
          visuals,
          chunkDirPrefix,
        },
      };
    } catch {
      // Missing stack manifest → 1-frame empty composition.
      return {
        durationInFrames: 1,
        props: {
          chunkIds: [],
          durations: [],
          overviews: [],
          cardNarrations: [],
          cardDurations: [],
          visuals: [],
          chunkDirPrefix: `chunks/${stack}`,
        },
      };
    }
  };
}

/** Registers one <Composition> per stack listed in the combined
 *  manifest's `stacks` field. run-local.sh reads these composition
 *  IDs to render each stack to its own video file. */
export const StackVideoCompositions: React.FC = () => {
  // Remotion evaluates <Composition> at bundle time — we can't do
  // async here. Instead we register compositions for every stack the
  // combined manifest lists. The combined manifest is written at build
  // time by run_backend_pilot.py, so the stacks are known statically
  // relative to the bundle.
  //
  // Because calculateMetadata is async and runs per-composition, each
  // StackVideo loads only its own stack's manifest at render time.
  //
  // We read the combined manifest synchronously via a <Still>-less
  // approach: register a fixed set of well-known stacks. Any stack
  // that doesn't have a manifest simply produces a 1-frame empty
  // video (calculateMetadata catches the fetch error).
  const KNOWN_STACKS = ["react", "angular", "vue", "solid", "qwik", "javascript", "go", "python", "spring-boot", "express", "rust", "unknown"];

  return (
    <>
      {KNOWN_STACKS.map((stack) => (
        <Composition
          key={`StackVideo-${stack}`}
          id={`StackVideo-${stack}`}
          component={VideoBody}
          durationInFrames={30}
          fps={FPS}
          width={1280}
          height={720}
          calculateMetadata={makeStackCalculateMetadata(stack)}
          defaultProps={{
            chunkIds: [],
            durations: [],
            overviews: [],
            cardNarrations: [],
            cardDurations: [],
            visuals: [],
            chunkDirPrefix: `chunks/${stack}`,
          } as VideoProps}
        />
      ))}
    </>
  );
};

// ===================================================================
// Combined FullVideo composition (backward compat)
// ===================================================================

async function fetchCombinedManifest(): Promise<CombinedManifest> {
  const res = await fetch(staticFile("chunks/manifest.json"));
  return res.json();
}

const calculateMetadata: CalculateMetadataFunction<VideoProps> = async () => {
  const manifest = await fetchCombinedManifest();
  const { durations, overviews, cardNarrations, cardDurations, visuals } =
    await loadChunks(manifest.chunkIds, "chunks");

  const total = durations.reduce(
    (sum, d, i) =>
      sum +
      chunkTotalFrames(
        cardDurations[i],
        visuals[i]?.treeFrames ?? 0,
        visuals[i]?.lifecycleFrames ?? 0,
        d,
        visuals[i]?.breakdownFrames ?? 0,
      ),
    0,
  );
  return {
    durationInFrames: Math.max(1, total),
    props: {
      chunkIds: manifest.chunkIds,
      durations,
      overviews,
      cardNarrations,
      cardDurations,
      visuals,
      chunkDirPrefix: "chunks",
    },
  };
};

export const FullVideoComposition: React.FC = () => {
  return (
    <Composition
      id="FullVideo"
      component={VideoBody}
      durationInFrames={30}
      fps={FPS}
      width={1280}
      height={720}
      calculateMetadata={calculateMetadata}
      defaultProps={{
        chunkIds: [],
        durations: [],
        overviews: [],
        cardNarrations: [],
        cardDurations: [],
        visuals: [],
        chunkDirPrefix: "chunks",
      } as VideoProps}
    />
  );
};
