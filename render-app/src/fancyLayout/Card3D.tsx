import { useCurrentFrame } from "remotion";
import { card3dTransform } from "./layoutMath";

export type Card3DProps = {
  children: React.ReactNode;
  /** Tilt settle length in frames. */
  durationInFrames?: number;
  startFrame?: number;
  reducedMotion?: boolean;
  style?: React.CSSProperties;
  className?: string;
  /** When set, applies a panel chrome tuned for FileCard / breakdown emphasis. */
  variant?: "panel" | "bare";
};

/**
 * L4 — clarity-first CSS 3D card (no Three.js). Wrap FileCard panels or
 * breakdown emphasis only when phaseStyle=fancy and matrix allows L4.
 */
export const Card3D: React.FC<Card3DProps> = ({
  children,
  durationInFrames = 28,
  startFrame = 0,
  reducedMotion = false,
  style,
  className,
  variant = "panel",
}) => {
  const frame = useCurrentFrame();
  const { rotateXDeg, rotateYDeg, translateZPx, opacity } = card3dTransform(
    frame,
    durationInFrames,
    startFrame,
    reducedMotion,
  );

  const panelChrome =
    variant === "panel"
      ? {
          backgroundColor: "rgba(27, 30, 37, 0.92)",
          border: "1px solid rgba(255,255,255,0.09)",
          borderRadius: 12,
          boxShadow: reducedMotion
            ? "0 8px 28px rgba(0,0,0,0.35)"
            : `0 ${12 + translateZPx * 0.4}px ${32 + translateZPx}px rgba(0,0,0,0.45)`,
        }
      : {
          boxShadow: reducedMotion
            ? undefined
            : `0 ${8 + translateZPx * 0.3}px ${24 + translateZPx}px rgba(0,0,0,0.32)`,
        };

  return (
    <div
      className={className}
      style={{
        perspective: reducedMotion ? undefined : 1100,
        perspectiveOrigin: "50% 40%",
        height: style?.height ?? "100%",
        ...style,
      }}
    >
      <div
        style={{
          transformStyle: reducedMotion ? undefined : "preserve-3d",
          transform: reducedMotion
            ? undefined
            : `rotateX(${rotateXDeg}deg) rotateY(${rotateYDeg}deg) translateZ(${translateZPx}px)`,
          opacity,
          willChange: reducedMotion ? undefined : "transform, opacity",
          height: "100%",
          backfaceVisibility: "hidden",
          ...panelChrome,
        }}
      >
        {children}
      </div>
    </div>
  );
};