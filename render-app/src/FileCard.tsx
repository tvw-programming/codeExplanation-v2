import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

// The card that introduces each file before its walkthrough starts:
// what the file is, where it sits, what calls it and what it calls.
//
// Fields the repository genuinely cannot answer are not shown as empty
// rows — the overview carries a reason for each one (see
// src/narrate/file_overview.py) and the card prints that instead, so a
// gap reads as a known gap rather than as missing data.

export type FileOverview = {
  fileName: string;
  filePath: string;
  purpose: string | null;
  fileType: string;
  callers: string[];
  callees: string[];
  language: string | null;
  frameworks: string[];
  exports: string[];
  lineCount: number;
  lastModified: string | null;
  tests: string[];
  risks: string[];
  unavailable: Record<string, string>;
};

const ACCENT = "#60a5fa";
const DIM_TEXT = "#8b9099";
const PANEL_BG = "#1b1e25";

export const FILE_CARD_SECONDS = 3;

const shortPath = (path: string): string => {
  const parts = path.split("/");
  return parts.length > 3 ? ".../" + parts.slice(-3).join("/") : path;
};

const Card: React.FC<{
  label: string;
  children: React.ReactNode;
  grow?: number;
}> = ({ label, children, grow = 1 }) => (
  <Box
    sx={{
      flex: grow,
      minWidth: 0,
      bgcolor: PANEL_BG,
      border: "1px solid rgba(255,255,255,0.07)",
      borderRadius: "10px",
      p: "16px 18px",
    }}
  >
    <Typography
      sx={{
        fontFamily: "Helvetica, Arial, sans-serif",
        fontSize: 12,
        letterSpacing: "0.12em",
        textTransform: "uppercase",
        color: ACCENT,
        fontWeight: 700,
        mb: "8px",
      }}
    >
      {label}
    </Typography>
    {children}
  </Box>
);

const Body: React.FC<{ children: React.ReactNode; dim?: boolean }> = ({
  children,
  dim = false,
}) => (
  <Typography
    component="div"
    sx={{
      fontFamily: "Helvetica, Arial, sans-serif",
      fontSize: 16,
      lineHeight: "23px",
      color: dim ? DIM_TEXT : "#e8eaed",
    }}
  >
    {children}
  </Typography>
);

const Mono: React.FC<{ items: string[] }> = ({ items }) => (
  <Box sx={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
    {items.map((item) => (
      <Box
        key={item}
        sx={{
          fontFamily: "Menlo, monospace",
          fontSize: 14,
          color: "#dbeafe",
          bgcolor: "rgba(96,165,250,0.14)",
          borderRadius: "5px",
          px: "8px",
          py: "3px",
        }}
      >
        {item}
      </Box>
    ))}
  </Box>
);

export const FileCard: React.FC<{ overview: FileOverview }> = ({ overview }) => {
  const frame = useCurrentFrame();
  const fade = interpolate(frame, [0, 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const rise = interpolate(frame, [0, 12], [12, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const otherBits: string[] = [];
  if (overview.language) otherBits.push(overview.language);
  if (overview.frameworks.length > 0) otherBits.push(overview.frameworks.join(", "));
  otherBits.push(`${overview.lineCount} lines`);
  if (overview.lastModified) {
    otherBits.push(`last modified ${overview.lastModified.slice(0, 10)}`);
  }

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#15171c",
        padding: "46px 54px",
        opacity: fade,
      }}
    >
      <Box sx={{ transform: `translateY(${rise}px)`, height: "100%", display: "flex", flexDirection: "column" }}>
        <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 3 }}>
          <Typography
            sx={{
              fontFamily: "Menlo, monospace",
              fontSize: 46,
              fontWeight: 700,
              color: "#ffffff",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {overview.fileName}
          </Typography>
          <Box
            sx={{
              flexShrink: 0,
              bgcolor: ACCENT,
              color: "#0b1020",
              fontFamily: "Helvetica, Arial, sans-serif",
              fontSize: 15,
              fontWeight: 700,
              borderRadius: "6px",
              px: "12px",
              py: "5px",
            }}
          >
            {overview.fileType}
          </Box>
        </Box>

        <Typography
          sx={{
            fontFamily: "Menlo, monospace",
            fontSize: 18,
            color: DIM_TEXT,
            mt: "6px",
            mb: "22px",
          }}
        >
          {overview.filePath}
        </Typography>

        <Box sx={{ display: "flex", flexDirection: "column", gap: "14px", flex: 1, minHeight: 0 }}>
          <Card label="Purpose">
            {overview.purpose ? (
              <Body>
                {overview.purpose.length > 320
                  ? overview.purpose.slice(0, 320).replace(/\s+\S*$/, "") + "..."
                  : overview.purpose}
              </Body>
            ) : (
              <Body dim>Not stated: {overview.unavailable.purpose}.</Body>
            )}
          </Card>

          <Box sx={{ display: "flex", gap: "14px" }}>
            <Card label="Called by">
              {overview.callers.length > 0 ? (
                <Mono items={overview.callers.slice(0, 4).map(shortPath)} />
              ) : (
                <Body dim>No importers of this file in this repository.</Body>
              )}
            </Card>
            <Card label="Calls">
              {overview.callees.length > 0 ? (
                <Mono items={overview.callees.slice(0, 4).map(shortPath)} />
              ) : (
                <Body dim>No internal imports.</Body>
              )}
            </Card>
          </Box>

          <Box sx={{ display: "flex", gap: "14px" }}>
            <Card label="Exports" grow={1}>
              {overview.exports.length > 0 ? (
                <Mono items={overview.exports.slice(0, 6)} />
              ) : (
                <Body dim>Nothing exported under a name.</Body>
              )}
            </Card>
            <Card label="Other" grow={1}>
              <Body>{otherBits.join(" · ")}</Body>
              {overview.unavailable.lastModified ? (
                <Body dim>Last modified unknown: {overview.unavailable.lastModified}.</Body>
              ) : null}
              {overview.tests.length > 0 ? (
                <Body>Covered by {overview.tests.length} test file(s).</Body>
              ) : overview.unavailable.tests ? (
                <Body dim>Tests: {overview.unavailable.tests}.</Body>
              ) : null}
            </Card>
          </Box>

          {overview.risks.length > 0 ? (
            <Card label="Worth knowing">
              <Body dim>{overview.risks.join("; ")}.</Body>
            </Card>
          ) : null}
        </Box>
      </Box>
    </AbsoluteFill>
  );
};
