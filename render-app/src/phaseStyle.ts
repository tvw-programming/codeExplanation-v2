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

/** Structure clips default to fancy so diagram gate + L3 bullets work without config. */
export const DEFAULT_PHASE_STYLE: ResolvedPhaseStyle = {
  fileCard: "classic",
  componentTree: "fancy",
  lifecycle: "classic",
  chunkView: "classic",
  visualBreakdown: "fancy",
  architectureDocs: "classic",
};

/** Merge manifest phaseStyle with defaults; only explicit ``classic`` opts structure out. */
export function resolvePhaseStyleFromManifest(
  partial: Partial<ResolvedPhaseStyle> | null | undefined,
): ResolvedPhaseStyle {
  const base = { ...DEFAULT_PHASE_STYLE };
  if (!partial) {
    return base;
  }
  const pick = (key: keyof ResolvedPhaseStyle): PhaseStyleMode =>
    partial[key] === "classic" ? "classic" : partial[key] === "fancy" ? "fancy" : base[key];
  return {
    fileCard: pick("fileCard"),
    componentTree: pick("componentTree"),
    lifecycle: pick("lifecycle"),
    chunkView: pick("chunkView"),
    visualBreakdown: pick("visualBreakdown"),
    architectureDocs: pick("architectureDocs"),
  };
}