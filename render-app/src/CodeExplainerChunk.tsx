import { useCallback, useEffect, useState } from "react";
import {
  AbsoluteFill,
  Audio,
  CalculateMetadataFunction,
  Composition,
  interpolate,
  staticFile,
  useCurrentFrame,
  useDelayRender,
} from "remotion";

// Phase 6 — real end-to-end proof: narration.wav is genuine espeak-ng
// audio of the actual Phase 5 narration script for chunk alumni-06f407dc
// (ProfilePage.tsx from the real alumni-web repo). bundle.json's
// highlightConfig frames are computed by src/render/render_pipeline.py.
// alignmentSource in that bundle is "estimated" rather than "whisper-cpp"
// because this sandbox's network allowlist blocks the whisper.cpp model
// download host (huggingface.co) — see the Phase 6 plan writeup. The
// highlight below is driven by real frame numbers either way; it is the
// numbers themselves that are an honest estimate, not a simulation of
// the rendering mechanism.

type HighlightCue = {
  id: string;
  lineRange: [number, number];
  fromFrame: number;
  toFrame: number;
  assumed: boolean;
  note: string | null;
};

type Bundle = {
  chunkId: string;
  durationMs: number;
  alignmentSource: string;
  cleanText: string;
  highlightConfig: HighlightCue[];
};

const FPS = 30;

const calculateMetadata: CalculateMetadataFunction<Record<string, never>> = async () => {
  const res = await fetch(staticFile("sample-chunk/bundle.json"));
  const bundle: Bundle = await res.json();
  return {
    durationInFrames: Math.max(1, Math.ceil((bundle.durationMs / 1000) * FPS)),
  };
};

export const CodeExplainerChunkComposition: React.FC = () => {
  return (
    <Composition
      id="CodeExplainerChunk"
      component={CodeExplainerChunk}
      durationInFrames={30}
      fps={FPS}
      width={1280}
      height={720}
      calculateMetadata={calculateMetadata}
    />
  );
};

const CodeExplainerChunk: React.FC = () => {
  const frame = useCurrentFrame();
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [sourceLines, setSourceLines] = useState<string[] | null>(null);
  const { delayRender, continueRender, cancelRender } = useDelayRender();
  const [handle] = useState(() => delayRender());

  const load = useCallback(async () => {
    try {
      const [bundleRes, sourceRes] = await Promise.all([
        fetch(staticFile("sample-chunk/bundle.json")),
        fetch(staticFile("sample-chunk/source.tsx")),
      ]);
      setBundle(await bundleRes.json());
      setSourceLines((await sourceRes.text()).split("\n"));
      continueRender(handle);
    } catch (e) {
      cancelRender(e);
    }
  }, [continueRender, cancelRender, handle]);

  useEffect(() => {
    load();
  }, [load]);

  if (!bundle || !sourceLines) {
    return null;
  }

  return (
    <AbsoluteFill style={{ backgroundColor: "#1e1e1e", flexDirection: "row" }}>
      <Audio src={staticFile("sample-chunk/narration.wav")} />
      <div
        style={{
          flex: 1,
          fontFamily: "Menlo, monospace",
          fontSize: 16,
          color: "#d4d4d4",
          padding: 24,
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
            <div
              key={lineNumber}
              style={{
                backgroundColor: `rgba(100, 180, 255, ${highlightOpacity})`,
              }}
            >
              {String(lineNumber).padStart(3, " ")}  {line}
            </div>
          );
        })}
      </div>
      <div
        style={{
          width: 420,
          padding: 24,
          color: "white",
          fontFamily: "Helvetica, Arial, sans-serif",
          fontSize: 18,
          lineHeight: 1.5,
          backgroundColor: "#111",
        }}
      >
        <div style={{ opacity: 0.6, fontSize: 13, marginBottom: 12 }}>
          chunk: {bundle.chunkId} · alignment: {bundle.alignmentSource}
        </div>
        {bundle.cleanText}
      </div>
    </AbsoluteFill>
  );
};
