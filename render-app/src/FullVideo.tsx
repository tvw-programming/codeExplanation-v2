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

// The complete video for a repository: every chunk the backend pipeline
// successfully rendered (run_backend_pilot.py stages all of them under
// public/chunks/, one subfolder per chunkId, listed in
// public/chunks/manifest.json), played back-to-back in one continuous
// video via <Series> — not just a single sample chunk.
//
// Each file's walkthrough is introduced by a short, silent card naming
// the file and summarising it, so one file visibly ends before the next
// begins rather than the video cutting straight from the last line of
// one into the first line of another.

const FPS = 30;

/** A card stays up for as long as its narration takes to read, plus a
 *  short tail, and never less than the minimum — so the viewer is
 *  neither read a summary that has left the screen nor left waiting on
 *  a card after the audio has finished. */
function cardFramesFor(narration: CardNarration | null): number {
  const spoken = narration ? (narration.durationMs / 1000) + FILE_CARD_TAIL_SECONDS : 0;
  return Math.ceil(Math.max(MIN_FILE_CARD_SECONDS, spoken) * FPS);
}

type Manifest = { chunkIds: string[] };

async function fetchManifest(): Promise<Manifest> {
  const res = await fetch(staticFile("chunks/manifest.json"));
  return res.json();
}

const calculateMetadata: CalculateMetadataFunction<FullVideoProps> = async () => {
  const manifest = await fetchManifest();
  const loaded = await Promise.all(
    manifest.chunkIds.map(async (id) => {
      const bundle = await fetchBundle(`chunks/${id}`) as typeof bundle & {
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
  const durations = loaded.map((entry) => entry.duration);
  const overviews = loaded.map((entry) => entry.overview);
  const cardNarrations = loaded.map((entry) => entry.narration);
  const cardDurations = cardNarrations.map(cardFramesFor);
  // Every chunk is preceded by its card, so both count toward the total.
  const total = durations.reduce((sum, d, i) => sum + d + cardDurations[i], 0);
  return {
    durationInFrames: Math.max(1, total),
    props: {
      chunkIds: manifest.chunkIds,
      durations,
      overviews,
      cardNarrations,
      cardDurations,
    },
  };
};

type FullVideoProps = {
  chunkIds?: string[];
  durations?: number[];
  overviews?: (FileOverview | null)[];
  cardNarrations?: (CardNarration | null)[];
  cardDurations?: number[];
};

export const FullVideoComposition: React.FC = () => {
  return (
    <Composition
      id="FullVideo"
      component={FullVideo}
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
      } as FullVideoProps}
    />
  );
};

const FullVideo: React.FC<FullVideoProps> = ({
  chunkIds = [],
  durations = [],
  overviews = [],
  cardNarrations = [],
  cardDurations = [],
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
                  chunkDir={`chunks/${id}`}
                  position={{ index: i + 1, total: chunkIds.length }}
                  sectionSeconds={chunkFrames / FPS}
                />
              ) : null}
            </Series.Sequence>,
            <Series.Sequence key={id} durationInFrames={chunkFrames}>
              <ChunkView chunkDir={`chunks/${id}`} />
            </Series.Sequence>,
          ];
        })}
      </Series>
    </ThemeProvider>
  );
};
