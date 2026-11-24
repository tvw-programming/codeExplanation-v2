/** Resolved video.phaseStyle from pipeline config → Remotion manifest. */

export type PhaseStyleMode = "classic" | "fancy";

export type ResolvedPhaseStyle = {
  fileCard: PhaseStyleMode;
  componentTree: PhaseStyleMode;
  lifecycle: PhaseStyleMode;
  chunkView: PhaseStyleMode;
  visualBreakdown: PhaseStyleMode;
  architectureDocs: PhaseStyleMode;
};

/** All FullVideo clip phases default to fancy (structure, motion, L3 breakdown). */
export const DEFAULT_PHASE_STYLE: ResolvedPhaseStyle = {
  fileCard: "fancy",
  componentTree: "fancy",
  lifecycle: "fancy",
  chunkView: "fancy",
  visualBreakdown: "fancy",
  architectureDocs: "fancy",
};

/** Merge manifest phaseStyle with defaults; only explicit ``classic`` opts out. */
export function resolvePhaseStyleFromManifest(
  partial: Partial<ResolvedPhaseStyle> | null | undefined,
): ResolvedPhaseStyle {
  const base = { ...DEFAULT_PHASE_STYLE };
  if (!partial) {
    return base;
  }
  const pick = (key: keyof ResolvedPhaseStyle): PhaseStyleMode =>
    partial[key] === "classic" ? "classic" : "fancy";
  return {
    fileCard: pick("fileCard"),
    componentTree: pick("componentTree"),
    lifecycle: pick("lifecycle"),
    chunkView: pick("chunkView"),
    visualBreakdown: pick("visualBreakdown"),
    architectureDocs: pick("architectureDocs"),
  };
}