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

export const DEFAULT_PHASE_STYLE: ResolvedPhaseStyle = {
  fileCard: "classic",
  componentTree: "classic",
  lifecycle: "classic",
  chunkView: "classic",
  visualBreakdown: "classic",
  architectureDocs: "classic",
};

/** Merge manifest phaseStyle with defaults; only explicit ``fancy`` opts in. */
export function resolvePhaseStyleFromManifest(
  partial: Partial<ResolvedPhaseStyle> | null | undefined,
): ResolvedPhaseStyle {
  if (!partial) {
    return { ...DEFAULT_PHASE_STYLE };
  }
  const pick = (key: keyof ResolvedPhaseStyle): PhaseStyleMode =>
    partial[key] === "fancy" ? "fancy" : "classic";
  return {
    fileCard: pick("fileCard"),
    componentTree: pick("componentTree"),
    lifecycle: pick("lifecycle"),
    chunkView: pick("chunkView"),
    visualBreakdown: pick("visualBreakdown"),
    architectureDocs: pick("architectureDocs"),
  };
}