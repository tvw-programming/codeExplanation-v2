/**
 * §2.4 tech×part layout matrix — consulted only when phaseStyle=fancy.
 */
import type { PhaseStyleMode } from "../phaseStyle";
import type { EnterDirection } from "./layoutMath";

export type PhasePart =
  | "fileCard"
  | "componentTree"
  | "lifecycle"
  | "chunkView"
  | "visualBreakdown";

export type LayoutPatternId = "L1" | "L2" | "L3" | "L4";

type PatternMark = "D" | "A" | "-";

type MatrixCell = {
  L1: PatternMark;
  L2: PatternMark;
  L3: PatternMark;
  L4: PatternMark;
  L2Direction?: EnterDirection;
};

export type FancyPatternFlags = {
  l1: boolean;
  l2: boolean;
  l2Direction: EnterDirection;
  l3: boolean;
  l4: boolean;
};

export type HonestyHints = {
  hasAssumed?: boolean;
  hasAllMethod?: boolean;
  showSkip?: boolean;
  pathUnresolved?: boolean;
  treeSitter?: boolean;
};

/** Map manifest / theme stack ids onto matrix row keys. */
export function normalizeMatrixStack(stack: string | undefined | null): string {
  const raw = (stack || "unknown").toLowerCase().replace(/-/g, "_");
  if (raw === "spring_boot" || raw === "java") return "spring";
  if (raw === "go_fiber") return "go";
  if (raw === "angular") return "react";
  if (raw === "solid" || raw === "qwik" || raw === "javascript") return "vue";
  if (raw in MATRIX) return raw;
  return "react";
}

/** Pick matrix row for special teaching concerns layered on stack. */
export function matrixStackKey(
  stack: string | undefined | null,
  opts?: { prefixGraphTeach?: boolean; treeSitterTeach?: boolean },
): string {
  if (opts?.treeSitterTeach) return "tree_sitter";
  if (opts?.prefixGraphTeach) return "prefix_graph";
  return normalizeMatrixStack(stack);
}

const DEFAULT_L2: Record<PhasePart, EnterDirection> = {
  fileCard: "top",
  componentTree: "left",
  lifecycle: "right",
  chunkView: "left",
  visualBreakdown: "top",
};

function cell(
  L1: PatternMark,
  L2: PatternMark,
  L3: PatternMark,
  L4: PatternMark,
  L2Direction?: EnterDirection,
): MatrixCell {
  return {
    L1,
    L2,
    L3,
    L4,
    L2Direction: L2Direction ?? undefined,
  };
}

const PHASES: PhasePart[] = [
  "fileCard",
  "componentTree",
  "lifecycle",
  "chunkView",
  "visualBreakdown",
];

type StackRow = Record<PhasePart, MatrixCell>;

const MATRIX: Record<string, StackRow> = {
  react: {
    fileCard: cell("A", "D", "-", "A", "top"),
    componentTree: cell("A", "D", "-", "-", "left"),
    lifecycle: cell("A", "D", "-", "-", "right"),
    chunkView: cell("A", "-", "D", "-"),
    visualBreakdown: cell("A", "-", "A", "A"),
  },
  vue: {
    fileCard: cell("A", "D", "-", "A", "top"),
    componentTree: cell("A", "D", "-", "-", "left"),
    lifecycle: cell("A", "A", "-", "-", "right"),
    chunkView: cell("A", "-", "A", "-"),
    visualBreakdown: cell("A", "-", "-", "-"),
  },
  express: {
    fileCard: cell("-", "D", "-", "-", "top"),
    componentTree: cell("A", "D", "-", "-", "left"),
    lifecycle: cell("D", "D", "-", "-", "right"),
    chunkView: cell("A", "-", "A", "-"),
    visualBreakdown: cell("A", "-", "-", "-"),
  },
  go: {
    fileCard: cell("-", "D", "-", "-", "top"),
    componentTree: cell("A", "D", "-", "-", "left"),
    lifecycle: cell("A", "D", "-", "-", "right"),
    chunkView: cell("A", "-", "A", "-"),
    visualBreakdown: cell("A", "-", "-", "-"),
  },
  spring: {
    fileCard: cell("-", "D", "-", "-", "top"),
    componentTree: cell("D", "D", "-", "-", "left"),
    lifecycle: cell("D", "A", "-", "-", "right"),
    chunkView: cell("D", "-", "D", "-"),
    visualBreakdown: cell("D", "-", "-", "A"),
  },
  python: {
    fileCard: cell("-", "D", "-", "-", "top"),
    componentTree: cell("A", "D", "-", "-", "left"),
    lifecycle: cell("A", "A", "-", "-", "right"),
    chunkView: cell("A", "-", "A", "-"),
    visualBreakdown: cell("A", "-", "-", "-"),
  },
  rust: {
    fileCard: cell("-", "D", "-", "-", "top"),
    componentTree: cell("A", "D", "-", "-", "left"),
    lifecycle: cell("A", "A", "-", "-", "right"),
    chunkView: cell("A", "-", "A", "-"),
    visualBreakdown: cell("A", "-", "-", "-"),
  },
  prefix_graph: {
    fileCard: cell("-", "D", "-", "-", "top"),
    componentTree: cell("D", "D", "-", "-", "left"),
    lifecycle: cell("D", "D", "-", "-", "right"),
    chunkView: cell("D", "-", "D", "-"),
    visualBreakdown: cell("A", "-", "-", "-"),
  },
  tree_sitter: {
    fileCard: cell("A", "A", "-", "-", "top"),
    componentTree: cell("-", "-", "-", "-"),
    lifecycle: cell("-", "-", "-", "-"),
    chunkView: cell("D", "-", "D", "-"),
    visualBreakdown: cell("A", "-", "-", "-"),
  },
};

function markOn(cellValue: PatternMark, hints: HonestyHints | undefined, part: PhasePart): boolean {
  if (cellValue === "D") return true;
  if (cellValue !== "A" || !hints) return false;
  switch (part) {
    case "fileCard":
    case "visualBreakdown":
      return Boolean(hints.hasAssumed || hints.showSkip);
    case "componentTree":
    case "lifecycle":
      return Boolean(hints.hasAssumed || hints.pathUnresolved || hints.hasAllMethod);
    case "chunkView":
      return Boolean(
        hints.hasAssumed || hints.treeSitter || hints.showSkip || hints.pathUnresolved,
      );
    default:
      return Boolean(hints.hasAssumed);
  }
}

export function resolveFancyPatterns(
  phaseStyle: PhaseStyleMode,
  part: PhasePart,
  stackKey: string,
  hints?: HonestyHints,
): FancyPatternFlags {
  const off: FancyPatternFlags = {
    l1: false,
    l2: false,
    l2Direction: DEFAULT_L2[part],
    l3: false,
    l4: false,
  };
  if (phaseStyle !== "fancy") {
    return off;
  }
  const row = MATRIX[stackKey] ?? MATRIX.react;
  const c = row[part];
  // D = default on in fancy mode; A = optional pattern also on in fancy
  // (honesty-gated L1 still uses markOn so we never invent callout text).
  return {
    l1: markOn(c.L1, hints, part),
    l2: c.L2 === "D" || c.L2 === "A",
    l2Direction: c.L2Direction ?? DEFAULT_L2[part],
    l3: c.L3 === "D" || c.L3 === "A",
    l4: c.L4 === "D" || c.L4 === "A",
  };
}

export function honestyTickerLabel(hints: HonestyHints): string | null {
  if (hints.showSkip) return "SKIP";
  if (hints.pathUnresolved) return "pathResolved: false";
  if (hints.treeSitter) return "CEV_TREE_SITTER";
  if (hints.hasAllMethod) return "ALL";
  if (hints.hasAssumed) return "assumed";
  return null;
}

/** Test helper: every matrix row defines all phase parts. */
export function matrixRowKeys(): string[] {
  return Object.keys(MATRIX);
}

export function matrixPhaseParts(): PhasePart[] {
  return [...PHASES];
}