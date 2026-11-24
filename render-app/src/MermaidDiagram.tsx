import Box from "@mui/material/Box";
import { useEffect, useId, useState } from "react";
import { continueRender, delayRender } from "remotion";
import { HEADER_HEIGHT } from "./treeLayout";

let mermaidReady: Promise<typeof import("mermaid")> | null = null;

function loadMermaid(): Promise<typeof import("mermaid")> {
  if (!mermaidReady) {
    mermaidReady = import("mermaid").then((mod) => {
      mod.default.initialize({
        startOnLoad: false,
        securityLevel: "strict",
        theme: "dark",
        fontFamily: "system-ui, sans-serif",
      });
      return mod;
    });
  }
  return mermaidReady;
}

/** Renders pre-exported Mermaid text (from interactive.json / bundle.json) to SVG for mp4 frames. */
export const MermaidDiagram: React.FC<{
  source: string;
  skipReason?: string | null;
}> = ({ source, skipReason }) => {
  const reactId = useId();
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!source?.trim()) {
      return;
    }
    const handle = delayRender(`mermaid-diagram-${reactId}`);
    let cancelled = false;

    (async () => {
      try {
        const { default: mermaid } = await loadMermaid();
        const renderId = `cev-mermaid-${reactId.replace(/:/g, "")}`;
        const { svg: rendered } = await mermaid.render(renderId, source.trim());
        if (!cancelled) {
          setSvg(rendered);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        continueRender(handle);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [source, reactId]);

  if (!source?.trim()) {
    return skipReason ? (
      <Box
        sx={{
          color: "#8b9099",
          fontSize: 14,
          textAlign: "center",
          px: 3,
        }}
      >
        Mermaid skipped: {skipReason}
      </Box>
    ) : null;
  }

  if (error) {
    return (
      <Box
        sx={{
          color: "#f87171",
          fontSize: 13,
          textAlign: "left",
          px: 3,
          whiteSpace: "pre-wrap",
          fontFamily: "monospace",
        }}
      >
        Mermaid render error — showing source only.
        {"\n"}
        {error}
      </Box>
    );
  }

  if (!svg) {
    return null;
  }

  return (
    <Box
      sx={{
        position: "absolute",
        top: HEADER_HEIGHT,
        left: 0,
        right: 0,
        bottom: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        px: 2,
        py: 1,
        boxSizing: "border-box",
        "& svg": {
          maxWidth: "100%",
          maxHeight: "100%",
          width: "auto",
          height: "auto",
        },
      }}
      // Mermaid output is trusted parser SVG from our own export strings.
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
};