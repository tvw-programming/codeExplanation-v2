import type { FileOverview } from "../FileCard";
import type { VisualTheme } from "../visualTheme";
import { resolveVisualTheme } from "../visualTheme";
import { matrixStackKey } from "./phaseLayoutMatrix";

export function resolveChunkStackId(
  bundleStack: string | null | undefined,
  visualTheme: VisualTheme | null | undefined,
  overview: FileOverview | null | undefined,
): string {
  if (bundleStack) return bundleStack;
  if (visualTheme?.stack && visualTheme.stack !== "unknown") {
    return visualTheme.stack;
  }
  return resolveVisualTheme(null, overview?.frameworks, overview?.language).stack;
}

export function resolveMatrixStackKey(
  stackId: string,
  opts?: { prefixGraphTeach?: boolean; treeSitterTeach?: boolean },
): string {
  return matrixStackKey(stackId, opts);
}