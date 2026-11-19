/** Reads what the pipeline has published so far.
 *
 *  Every one of these files may be absent: the viewer starts before the
 *  pipeline (that is the point — a render takes many minutes), so
 *  "not there yet" is the normal first state, not an error. Each
 *  loader returns null rather than throwing, and the UI renders a
 *  waiting state from that.
 */

import type { FileOverview, PipelineStatus, ProjectManifest, SegmentIndex } from "./types";

const DATA = "/data";

async function getJson<T>(url: string): Promise<T | null> {
  try {
    // cache: "no-store" because these files are rewritten in place as
    // the run progresses; a cached copy would freeze the UI mid-run.
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export const loadProject = () => getJson<ProjectManifest>(`${DATA}/chunks/project.json`);

export const loadStatus = () => getJson<PipelineStatus>(`${DATA}/state/status.json`);

export const loadSegments = (stack: string) =>
  getJson<SegmentIndex>(`${DATA}/chunks/${stack}/segments.json`);

export const loadOverview = async (stack: string, chunkId: string) => {
  const bundle = await getJson<{ fileOverview?: FileOverview }>(
    `${DATA}/chunks/${stack}/${chunkId}/bundle.json`,
  );
  return bundle?.fileOverview ?? null;
};

export const videoUrl = (fileName: string) => `${DATA}/videos/${fileName}`;

export const logoUrl = (logoPath: string) =>
  `${DATA}/${logoPath.replace(/^visuals\//, "visuals/")}`;

/** Does this video file exist yet? A HEAD avoids pulling a 300MB mp4
 *  just to find out. */
export async function videoExists(fileName: string): Promise<boolean> {
  try {
    const res = await fetch(videoUrl(fileName), { method: "HEAD", cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}
