/** What the pipeline found in the selected file.
 *
 *  This is what makes a not-yet-rendered file still worth clicking: the
 *  extraction finishes long before the video does, so the analysis is
 *  readable while the mp4 is still encoding.
 *
 *  Fields the extractor could not establish arrive in `unavailable`
 *  with a reason, and are shown as such rather than guessed at.
 */

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { FileOverview, SegmentFile } from "./types";

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({
  title,
  children,
}) => (
  <Box sx={{ mb: 2 }}>
    <Typography
      variant="overline"
      sx={{ color: "text.secondary", letterSpacing: 1, fontSize: 10 }}
    >
      {title}
    </Typography>
    <Box sx={{ mt: 0.5 }}>{children}</Box>
  </Box>
);

const Chips: React.FC<{ values: string[] }> = ({ values }) => (
  <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap", rowGap: 0.5 }}>
    {values.map((value) => (
      <Chip
        key={value}
        size="small"
        label={value}
        sx={{ bgcolor: "rgba(255,255,255,0.06)", fontSize: 11, height: 20 }}
      />
    ))}
  </Stack>
);

export const FileMeta: React.FC<{
  file: SegmentFile | null;
  overview: FileOverview | null;
}> = ({ file, overview }) => {
  if (!file) {
    return (
      <Box sx={{ p: 2 }}>
        <Typography variant="body2" color="text.secondary">
          Select a file to see what the pipeline extracted from it.
        </Typography>
      </Box>
    );
  }

  const purpose = overview?.purposeFull || overview?.purpose || file.purpose;
  const routes = overview?.routes ?? [];
  const contains = overview?.contains ?? [];
  const risks = overview?.risks ?? [];
  const unavailable = Object.entries(overview?.unavailable ?? {});

  return (
    <Box sx={{ p: 2, overflowY: "auto", height: "100%" }}>
      <Typography sx={{ fontFamily: "ui-monospace, monospace", fontWeight: 600 }}>
        {file.fileName}
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ wordBreak: "break-all" }}>
        {file.filePath}
      </Typography>

      <Stack direction="row" spacing={0.5} sx={{ mt: 1, flexWrap: "wrap", rowGap: 0.5 }}>
        {file.layer ? <Chip size="small" label={file.layer} sx={{ height: 20 }} /> : null}
        {file.language ? (
          <Chip size="small" label={file.language} sx={{ height: 20 }} />
        ) : null}
        {file.lineCount ? (
          <Chip size="small" label={`${file.lineCount} lines`} sx={{ height: 20 }} />
        ) : null}
      </Stack>

      <Divider sx={{ my: 2 }} />

      {purpose ? (
        <Section title="Purpose">
          <Typography variant="body2">{purpose}</Typography>
        </Section>
      ) : null}

      {overview?.frameworks?.length ? (
        <Section title="Frameworks">
          <Chips values={overview.frameworks} />
        </Section>
      ) : null}

      {overview?.libraries?.length ? (
        <Section title="Libraries">
          <Chips values={overview.libraries} />
        </Section>
      ) : null}

      {routes.length ? (
        <Section title={`Routes (${routes.length})`}>
          <Stack spacing={0.25}>
            {routes.map((route, i) => (
              <Typography
                key={`${route.method}-${route.path}-${i}`}
                variant="caption"
                sx={{ fontFamily: "ui-monospace, monospace" }}
              >
                <Box component="span" sx={{ color: "primary.main", mr: 0.75 }}>
                  {route.method ?? "ANY"}
                </Box>
                {route.path}
              </Typography>
            ))}
          </Stack>
        </Section>
      ) : null}

      {contains.length ? (
        <Section title={`Defines (${contains.length})`}>
          <Stack spacing={0.25}>
            {contains.map((item, i) => (
              <Typography
                key={`${item.name}-${i}`}
                variant="caption"
                sx={{ fontFamily: "ui-monospace, monospace" }}
              >
                {item.name}
                {item.kind ? (
                  <Box component="span" sx={{ color: "text.secondary" }}>
                    {" "}
                    · {item.kind}
                  </Box>
                ) : null}
              </Typography>
            ))}
          </Stack>
        </Section>
      ) : null}

      {overview?.callees?.length ? (
        <Section title="Calls into">
          <Chips values={overview.callees} />
        </Section>
      ) : null}

      {overview?.callers?.length ? (
        <Section title="Called from">
          <Chips values={overview.callers} />
        </Section>
      ) : null}

      {overview?.sideEffects?.length ? (
        <Section title="Side effects">
          <Chips values={overview.sideEffects} />
        </Section>
      ) : null}

      {risks.length ? (
        <Section title="Risks">
          <Stack spacing={0.5}>
            {risks.map((risk, i) => (
              <Typography key={i} variant="caption" sx={{ color: "warning.light" }}>
                {risk}
              </Typography>
            ))}
          </Stack>
        </Section>
      ) : null}

      {unavailable.length ? (
        <Section title="Not established">
          <Stack spacing={0.5}>
            {unavailable.map(([field, reason]) => (
              <Typography key={field} variant="caption" color="text.secondary">
                <strong>{field}</strong> — {reason}
              </Typography>
            ))}
          </Stack>
        </Section>
      ) : null}
    </Box>
  );
};
