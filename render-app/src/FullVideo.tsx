import { CalculateMetadataFunction, Composition, Series, staticFile } from "remotion";
import { ThemeProvider } from "@mui/material/styles";
import { theme } from "../shared/theme";
import { ChunkView, bundleDurationInFrames, fetchBundle } from "./ChunkView";

// The complete video for a repository: every chunk the backend pipeline
// successfully rendered (run_backend_pilot.py stages all of them under
// public/chunks/, one subfolder per chunkId, listed in
// public/chunks/manifest.json), played back-to-back in one continuous
// video via <Series> — not just a single sample chunk.

const FPS = 30;

type Manifest = { chunkIds: string[] };

async function fetchManifest(): Promise<Manifest> {
  const res = await fetch(staticFile("chunks/manifest.json"));
  return res.json();
}

const calculateMetadata: CalculateMetadataFunction<Record<string, never>> = async () => {
  const manifest = await fetchManifest();
  const durations = await Promise.all(
    manifest.chunkIds.map(async (id) => {
      const bundle = await fetchBundle(`chunks/${id}`);
      return bundleDurationInFrames(bundle, FPS);
    }),
  );
  const total = durations.reduce((sum, d) => sum + d, 0);
  return {
    durationInFrames: Math.max(1, total),
    props: { chunkIds: manifest.chunkIds, durations },
  };
};

type FullVideoProps = { chunkIds?: string[]; durations?: number[] };

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
      defaultProps={{ chunkIds: [], durations: [] } as FullVideoProps}
    />
  );
};

const FullVideo: React.FC<FullVideoProps> = ({ chunkIds = [], durations = [] }) => {
  if (chunkIds.length === 0) {
    return null;
  }

  return (
    <ThemeProvider theme={theme}>
      <Series>
        {chunkIds.map((id, i) => (
          <Series.Sequence key={id} durationInFrames={Math.max(1, durations[i] ?? FPS)}>
            <ChunkView chunkDir={`chunks/${id}`} />
          </Series.Sequence>
        ))}
      </Series>
    </ThemeProvider>
  );
};
