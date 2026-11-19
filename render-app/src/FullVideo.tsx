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

// Per-stack video isolation: the backend pipeline now stages chunks
// under public/chunks/<stack>/<chunkId>/ and writes a per-stack
// manifest at public/chunks/<stack>/manifest.json. Each stack gets
// its own Remotion composition ("StackVideo-<stack>") that renders
// only that stack's chunks into output/video-<stack>.mp4.
//
// The combined FullVideo composition is kept for backward compat —
// it reads the combined manifest at public/chunks/manifest.json
// and renders every chunk from every stack back-to-back.

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

// ---------- shared loader ----------

async function loadChunks(chunkIds: string[], chunkDirPrefix: string) {
  const loaded = await Promise.all(
    chunkIds.map(async (id) => {
      const bundle = await fetchBundle(`${chunkDirPrefix}/${id}`) as typeof bundle & {
        fileOverview?: FileOverview;
        cardNarration?: CardNarration;
      };
      return {
        duration: bundleDurationInFrames(bundle, FPS),
        overview: bundle.fileOverview ?? null,
        narration: bundle.cardNarration ?? null,
      };
    }),
  );
  return {
    durations: loaded.map((e) => e.duration),
    overviews: loaded.map((e) => e.overview),
    cardNarrations: loaded.map((e) => e.narration),
    cardDurations: loaded.map((e) => cardFramesFor(e.narration)),
  };
}

// ---------- shared props & component ----------

type VideoProps = {
  chunkIds?: string[];
  durations?: number[];
  overviews?: (FileOverview | null)[];
  cardNarrations?: (CardNarration | null)[];
  cardDurations?: number[];
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
          return [
            <Series.Sequence key={`${id}-card`} durationInFrames={cardFrames}>
              {overview ? (
                <FileCard
                  overview={overview}
                  narration={narration}
                  chunkDir={`${chunkDirPrefix}/${id}`}
                  position={{ index: i + 1, total: chunkIds.length }}
                  sectionSeconds={chunkFrames / FPS}
                />
              ) : null}
            </Series.Sequence>,
            <Series.Sequence key={id} durationInFrames={chunkFrames}>
              <ChunkView chunkDir={`${chunkDirPrefix}/${id}`} />
            </Series.Sequence>,
          ];
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
    let manifest: StackManifest;
    try {
      manifest = await fetchStackManifest(stack);
    } catch {
      // No manifest for this stack — produce a minimal 1-frame
      // composition so Remotion doesn't crash the whole bundle.
      return { durationInFrames: 1, props: { chunkIds: [] } };
    }
    const chunkDirPrefix = `chunks/${stack}`;
    const { durations, overviews, cardNarrations, cardDurations } =
      await loadChunks(manifest.chunkIds, chunkDirPrefix);

    const total = durations.reduce((sum, d, i) => sum + d + cardDurations[i], 0);
    return {
      durationInFrames: Math.max(1, total),
      props: {
        chunkIds: manifest.chunkIds,
        durations,
        overviews,
        cardNarrations,
        cardDurations,
        chunkDirPrefix,
      },
    };
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
  const KNOWN_STACKS = ["react", "angular", "go", "python", "spring-boot", "express", "unknown"];

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
  const { durations, overviews, cardNarrations, cardDurations } =
    await loadChunks(manifest.chunkIds, "chunks");

  const total = durations.reduce((sum, d, i) => sum + d + cardDurations[i], 0);
  return {
    durationInFrames: Math.max(1, total),
    props: {
      chunkIds: manifest.chunkIds,
      durations,
      overviews,
      cardNarrations,
      cardDurations,
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
        chunkDirPrefix: "chunks",
      } as VideoProps}
    />
  );
};
