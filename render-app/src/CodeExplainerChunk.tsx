import { Composition } from "remotion";
import { ThemeProvider } from "@mui/material/styles";
import { theme } from "../shared/theme";
import { ChunkView, bundleDurationInFrames, fetchBundle } from "./ChunkView";
import type { CalculateMetadataFunction } from "remotion";

// Single-chunk demo/proof composition — renders exactly one chunk from
// the fixed public/sample-chunk/ path. Useful for a quick render or for
// checking one chunk's narration/highlighting in isolation. For a full
// repo's worth of chunks concatenated into one video, see FullVideo.tsx,
// which reuses the same ChunkView component per chunk.

const FPS = 30;

const calculateMetadata: CalculateMetadataFunction<Record<string, never>> = async () => {
  const bundle = await fetchBundle("sample-chunk");
  return {
    durationInFrames: bundleDurationInFrames(bundle, FPS),
  };
};

export const CodeExplainerChunkComposition: React.FC = () => {
  return (
    <Composition
      id="CodeExplainerChunk"
      component={CodeExplainerChunkRoot}
      durationInFrames={30}
      fps={FPS}
      width={1280}
      height={720}
      calculateMetadata={calculateMetadata}
    />
  );
};

const CodeExplainerChunkRoot: React.FC = () => (
  <ThemeProvider theme={theme}>
    <ChunkView chunkDir="sample-chunk" />
  </ThemeProvider>
);
