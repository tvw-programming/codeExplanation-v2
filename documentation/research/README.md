# Research notes

Raw research backing the decisions recorded in `documentation/`. These
are working notes, not polished documentation: they are kept in the
repository so the evidence behind a decision travels with the code and
can be re-read (or disputed) later, rather than living only in a chat
transcript.

Each subfolder is one research question. The synthesised conclusions
are written up as a numbered document in `documentation/`; the notes
here are what that write-up draws on.

| Folder | Question | Write-up |
|---|---|---|
| `pipeline-support-across-six-stacks/` | Will this pipeline work for React, Angular, Python, Express/Node, Java Spring Boot and Go Fiber projects, and what does each stack actually demand? | `documentation/14-stack-support-validation.md` |

## How to read these

- Notes carry inline source URLs. Claims without one are the
  researcher's own inference and are labelled as such in a `Gaps` or
  `Inferences` section — treat those as leads to verify, not as facts.
- `codebase_audit.md` is different in kind from the others: it is an
  audit of this repository's own source, with file paths and line
  numbers, and was produced by running the real pipeline modules
  against synthetic fixtures for each stack. Its findings are
  reproducible here rather than cited from the web. **It predates later
  fixes** (Angular confidence 0.3, nested Fiber prefix composition,
  flat organizing-folder files, side-effect `type` key, `.java` layer
  label) — do not treat its recorded Angular confidence 0.95 or
  uncomposed Fiber paths as current. See the "Current vs snapshot" box
  on `documentation/14-stack-support-validation.md`.
- Where a researcher could not reach a source, it says so. Several
  pages were blocked or rate-limited during this research and the
  affected claims are flagged in each file's caveats.
