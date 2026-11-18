import { useCallback, useEffect, useState } from "react";
import {
  AbsoluteFill,
  Audio,
  interpolate,
  staticFile,
  useCurrentFrame,
  useDelayRender,
} from "remotion";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

// Shared per-chunk view, used by both the single-chunk demo composition
// (CodeExplainerChunk, reading from public/sample-chunk/) and the
// full-repo video (FullVideo, reading from public/chunks/<chunkId>/ —
// one sequence per chunk, laid out back-to-back by <Series> in
// FullVideo.tsx). `useCurrentFrame()` here is relative to whichever
// <Series.Sequence> this instance is mounted inside, so the same
// highlight-timing logic works unchanged in both places.

export type HighlightCue = {
  id: string;
  lineRange: [number, number];
  fromFrame: number;
  toFrame: number;
  assumed: boolean;
  note: string | null;
};

export type Bundle = {
  chunkId: string;
  durationMs: number;
  alignmentSource: string;
  cleanText: string;
  highlightConfig: HighlightCue[];
};

const FPS = 30;

export function bundleDurationInFrames(bundle: Bundle, fps: number = FPS): number {
  return Math.max(1, Math.ceil((bundle.durationMs / 1000) * fps));
}

export async function fetchBundle(chunkDir: string): Promise<Bundle> {
  const res = await fetch(staticFile(`${chunkDir}/bundle.json`));
  return res.json();
}

export const ChunkView: React.FC<{ chunkDir: string }> = ({ chunkDir }) => {
  const frame = useCurrentFrame();
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [sourceLines, setSourceLines] = useState<string[] | null>(null);
  const { delayRender, continueRender, cancelRender } = useDelayRender();
  const [handle] = useState(() => delayRender(`ChunkView(${chunkDir})`));

  const load = useCallback(async () => {
    try {
      const [bundleRes, sourceRes] = await Promise.all([
        fetch(staticFile(`${chunkDir}/bundle.json`)),
        fetch(staticFile(`${chunkDir}/source.tsx`)),
      ]);
      setBundle(await bundleRes.json());
      setSourceLines((await sourceRes.text()).split("\n"));
      continueRender(handle);
    } catch (e) {
      cancelRender(e);
    }
  }, [chunkDir, continueRender, cancelRender, handle]);

  useEffect(() => {
    load();
  }, [load]);

  if (!bundle || !sourceLines) {
    return null;
  }

  return (
    <AbsoluteFill style={{ backgroundColor: "#1e1e1e", flexDirection: "row" }}>
      <Audio src={staticFile(`${chunkDir}/narration.wav`)} />
      <Box
        sx={{
          flex: 1,
          fontFamily: "Menlo, monospace",
          fontSize: 16,
          color: "#d4d4d4",
          p: 3,
          overflow: "hidden",
          whiteSpace: "pre",
        }}
      >
        {sourceLines.map((line, idx) => {
          const lineNumber = idx + 1;
          const cue = bundle.highlightConfig.find(
            (c) => lineNumber >= c.lineRange[0] && lineNumber <= c.lineRange[1],
          );
          const highlightOpacity = cue
            ? interpolate(
                frame,
                [cue.fromFrame - 5, cue.fromFrame, cue.toFrame, cue.toFrame + 5],
                [0, 0.35, 0.35, 0],
                { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
              )
            : 0;
          return (
            <Box
              key={lineNumber}
              sx={{ bgcolor: `rgba(110, 168, 254, ${highlightOpacity})` }}
            >
              {String(lineNumber).padStart(3, " ")}  {line}
            </Box>
          );
        })}
      </Box>
      <Box
        sx={{
          width: 420,
          p: 3,
          color: "text.primary",
          fontFamily: "Helvetica, Arial, sans-serif",
          fontSize: 18,
          lineHeight: 1.5,
          bgcolor: "background.paper",
        }}
      >
        <Typography variant="caption" sx={{ opacity: 0.7, display: "block", mb: 1.5 }}>
          chunk: {bundle.chunkId} · alignment: {bundle.alignmentSource}
        </Typography>
        <Typography component="div" sx={{ fontSize: "inherit", lineHeight: "inherit" }}>
          {bundle.cleanText}
        </Typography>
      </Box>
    </AbsoluteFill>
  );
};
