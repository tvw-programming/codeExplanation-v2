/**
 * Studio-only composition to preview L1–L3 in isolation (not used in FullVideo).
 */
import { AbsoluteFill, Composition } from "remotion";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { CEV_BG_VIDEO } from "../visualTheme";
import { AnimatedBulletList } from "./AnimatedBulletList";
import { EnterFrom } from "./EnterFrom";
import { Split7030 } from "./Split7030";
import { TickerBar } from "./TickerBar";

const DEMO_FPS = 30;
const DEMO_DURATION = 120;

const FancyLayoutPrimitivesScene: React.FC = () => {
  return (
    <AbsoluteFill style={{ backgroundColor: CEV_BG_VIDEO }}>
      <Split7030
        main={
          <EnterFrom direction="left">
            <Box
              sx={{
                height: "100%",
                borderRadius: 2,
                border: "1px solid rgba(255,255,255,0.12)",
                bgcolor: "#1b1e25",
                p: 2,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Typography sx={{ color: "#9CA3AF", fontSize: 14 }}>
                Main column (70%) — PR C wires real clip content here
              </Typography>
            </Box>
          </EnterFrom>
        }
        aside={
          <EnterFrom direction="right" startFrame={4}>
            <AnimatedBulletList
              items={[
                "Mounts only when extractor proves them",
                "Assumed edges stay dashed",
                "Measured-beat TTS unchanged",
              ]}
              activeIndex={1}
            />
          </EnterFrom>
        }
      />
      <TickerBar label="assumed" showFromFrame={12} hideAtFrame={100} />
    </AbsoluteFill>
  );
};

export const FancyLayoutPrimitivesDemoComposition = () => (
  <Composition
    id="FancyLayoutPrimitivesDemo"
    component={FancyLayoutPrimitivesScene}
    durationInFrames={DEMO_DURATION}
    fps={DEMO_FPS}
    width={1280}
    height={720}
  />
);