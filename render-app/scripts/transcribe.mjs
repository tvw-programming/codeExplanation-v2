// Phase 6 — transcribes a narration WAV file (produced by espeak-ng,
// see src/render/tts.py) with whisper.cpp, and writes word-level
// timestamps as JSON. This is the real alignment step the Python side
// (src/render/timing.py) consumes: no timestamps are fabricated here,
// they come from an actual local speech-to-text run.
//
// Usage: node scripts/transcribe.mjs <input.wav> <output.json>

import path from "path";
import fs from "fs";
import {
  downloadWhisperModel,
  installWhisperCpp,
  transcribe,
  toCaptions,
} from "@remotion/install-whisper-cpp";

const [, , inputPath, outputPath] = process.argv;

if (!inputPath || !outputPath) {
  console.error("Usage: node scripts/transcribe.mjs <input.wav> <output.json>");
  process.exit(1);
}

const whisperDir = path.join(process.cwd(), ".whisper-cpp");
const WHISPER_VERSION = "1.5.5";
const MODEL = "tiny.en"; // smallest model: this is a proof-of-mechanism
                          // pipeline running on CPU with no GPU, not a
                          // production-accuracy transcription setup.

async function main() {
  await installWhisperCpp({ to: whisperDir, version: WHISPER_VERSION });
  await downloadWhisperModel({ model: MODEL, folder: whisperDir });

  const whisperCppOutput = await transcribe({
    model: MODEL,
    whisperPath: whisperDir,
    whisperCppVersion: WHISPER_VERSION,
    inputPath: path.resolve(inputPath),
    tokenLevelTimestamps: true,
  });

  // Flatten whisper.cpp's token-level output into a simple
  // (word, startMs, endMs) list for the Python alignment step. `offsets`
  // are numeric milliseconds; `timestamps` are SRT-style display strings
  // (not used here).
  const words = [];
  for (const segment of whisperCppOutput.transcription) {
    for (const token of segment.tokens ?? []) {
      const text = (token.text ?? "").trim();
      // whisper.cpp emits special non-speech tokens (e.g. "[_BEG_]") with
      // bracket-wrapped text; skip those, they are not spoken words.
      if (!text || text.startsWith("[_")) continue;
      words.push({
        word: text,
        startMs: Math.round(token.offsets.from),
        endMs: Math.round(token.offsets.to),
      });
    }
  }

  const { captions } = toCaptions({ whisperCppOutput });

  fs.writeFileSync(outputPath, JSON.stringify({ words, captions }, null, 2));
  console.log(`Wrote ${words.length} timed words and ${captions.length} captions to ${outputPath}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
