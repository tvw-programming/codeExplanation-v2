import { CalculateMetadataFunction, Composition, Series, staticFile } from "remotion";
import { ThemeProvider } from "@mui/material/styles";
import { theme } from "../shared/theme";
import { ChunkView, bundleDurationInFrames, fetchBundle } from "./ChunkView";
import { FILE_CARD_SECONDS, FileCard, type FileOverview } from "./FileCard";

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
const CARD_FRAMES = FILE_CARD_SECONDS * FPS;

type Manifest = { chunkIds: string[] };

async function fetchManifest(): Promise<Manifest> {
  const res = await fetch(staticFile("chunks/manifest.json"));
  return res.json();
}

const calculateMetadata: CalculateMetadataFunction<FullVideoProps> = async () => {
  const manifest = await fetchManifest();
  const loaded = await Promise.all(
    manifest.chunkIds.map(async (id) => {
      const bundle = await fetchBundle(`chunks/${id}`);
      return {
        duration: bundleDurationInFrames(bundle, FPS),
        overview: (bundle as { fileOverview?: FileOverview }).fileOverview ?? null,
      };
    }),
  );
  const durations = loaded.map((entry) => entry.duration);
  const overviews = loaded.map((entry) => entry.overview);
  // Every chunk is preceded by its card, so both count toward the total.
  const total = durations.reduce((sum, d) => sum + d + CARD_FRAMES, 0);
  return {
    durationInFrames: Math.max(1, total),
    props: { chunkIds: manifest.chunkIds, durations, overviews },
  };
};

type FullVideoProps = {
  chunkIds?: string[];
  durations?: number[];
  overviews?: (FileOverview | null)[];
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
      defaultProps={{ chunkIds: [], durations: [], overviews: [] } as FullVideoProps}
    />
  );
};

const FullVideo: React.FC<FullVideoProps> = ({
  chunkIds = [],
  durations = [],
  overviews = [],
}) => {
  if (chunkIds.length === 0) {
    return null;
  }

  return (
    <ThemeProvider theme={theme}>
      <Series>
        {chunkIds.flatMap((id, i) => {
          const overview = overviews[i];
          return [
            <Series.Sequence key={`${id}-card`} durationInFrames={CARD_FRAMES}>
              {overview ? <FileCard overview={overview} /> : null}
            </Series.Sequence>,
            <Series.Sequence key={id} durationInFrames={Math.max(1, durations[i] ?? FPS)}>
              <ChunkView chunkDir={`chunks/${id}`} />
            </Series.Sequence>,
          ];
        })}
      </Series>
    </ThemeProvider>
  );
};
