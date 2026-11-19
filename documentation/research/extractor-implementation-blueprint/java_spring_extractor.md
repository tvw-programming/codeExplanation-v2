# Java / Spring Boot source extractor on tree-sitter — implementation blueprint

Target file: `/home/claude/codeExplanation-v2/src/extract/java_extractor.py`, plus a
`build_backend_java_chunk_record()` in `src/extract/json_builder.py` and two wiring changes in
`src/extract/extractor.py:55-72` and `src/extract/reuse_pipeline.py:85-94` (the two places that
currently emit the `"Extraction for stack '<stack>' is not yet implemented in Phase 3."`
placeholder with `confidence: 0`).

Everything in the "Design" subsections below was written against the actual code of
`src/extract/go_extractor.py`, `src/extract/ts_extractor.py`, `src/extract/common.py`,
`src/extract/function_context.py` and `src/extract/json_builder.py` as they stand, and every
tree-sitter claim was **executed** in a venv on this machine, not recalled. Commands and outputs
are given so they can be re-run.

**Shape contract the design must match** (read off the existing code, not assumed):

- `common.CodeSnippet(text, truncated, continuation_note, secrets_redacted)`; every snippet must
  come from `common.trim_snippet(lines, start_line, end_line)` — that function is the single
  `redact_secrets()` choke point and caps at `MAX_SNIPPET_LINES = 120`, returning a
  `continuation_note` rather than silently cutting.
- Line ranges are **1-indexed, inclusive**, carried as `tuple[int, int]` on dataclasses and
  `list[int]` in JSON (`"lineRange": [start, end]`).
- `common.confidence_from_flags(total_claims, assumed_claims, base=0.95)` → `base - 0.5 *
  (assumed/total)`, and **0.3 when `total_claims == 0`** (finding nothing scores low, per its
  docstring). `common.confidence_level()` buckets at 0.85 / 0.6.
- `common.LANGUAGE_BY_EXTENSION` already maps `".java": "Java"`, so `detect_language()` needs no
  change.
- Each record is the flat dict built by `json_builder`: `chunkId, filePath, featureName,
  projectType, language, lineRange, fileDescription, frameworkOrLibrary, inputs, outputs,
  eventHandlers, apiCalls, importantFunctions, sideEffects, featureMapping, dependencies,
  dataModels, routes, confidence, confidenceLevel, notes, contentHash, extractorVersion,
  lastUpdated, pullRequest, pullRequestNote`.
- `routes` entries are `{path, method, type ("static"|"dynamic"), routingLibrary, protected,
  assumed, handler, notes}`; `dataModels` entries are `{name, fields:[{name,type}], file,
  codeSnippet, truncated, continuationNote, secretsRedacted}`; `importantFunctions` entries are
  `{name, signature, lineRange, codeSnippet, truncated, continuationNote, secretsRedacted}` then
  `.update(build_function_context(...))`.
- `function_context.build_function_context()` returns `description, descriptionSource, exported,
  calledBy, calls, params, raisesError, isAsync, reactHooks, apiCalls, sideEffects, lineCount`.
  Its `is_exported(signature, name, language)` has exactly two branches: `language == "go"` → first
  letter uppercase, else `signature.lstrip().startswith("export")`. **For Java the else-branch marks
  every declaration unexported** — see the visibility section.
- `feature_mapping.match_calls_to_routes()` consumes `(chunk_id, method, path, assumed)` route
  tuples from `record["routes"]`, so Spring routes land in the existing frontend↔backend linker for
  free provided the path is the *full* path.

---

## 1. tree-sitter in Python: exact packages, pinned versions, and working setup code

### Takeaway
Pin **`tree_sitter==0.25.2`** + **`tree_sitter_java==0.23.5`**. I installed that pair and parsed real
Spring source with it on this machine; `tree_sitter==0.26.1` + `tree_sitter_java==0.23.5` also loads
and parses, so the grammar's `tree-sitter~=0.22` marker (which is only inside its optional `core`
extra, not a hard runtime requirement) is not a blocker. Do **not** use
`tree-sitter-languages` — last released 2024-02-04 and it pins an unbounded old `tree-sitter`.

### Cited Findings
- `tree-sitter` (the runtime) latest is **0.25.2 → 0.26.1**, `requires_python >=3.10`, latest uploaded
  **2026-11-09**, 38 releases; its `requires_dist` contains only docs/test extras, no grammar
  dependency — measured from `https://pypi.org/pypi/tree-sitter/json` (`curl` + `json.load`).
- `tree-sitter-java` latest is **0.23.5**, uploaded **2024-12-21**, `requires_python >=3.9`, 7
  releases (0.23.0 … 0.23.5), wheels are `cp39-abi3` for macosx x86_64 + arm64 and manylinux
  x86_64 + aarch64; `requires_dist: ['tree-sitter~=0.22; extra == "core"']` — measured from
  `https://pypi.org/pypi/tree-sitter-java/json`. This closes the previous round's explicit gap
  ("the `tree_sitter_java` PyPI package name / version could not be verified").
- `tree-sitter-languages` latest is **1.10.2**, uploaded **2024-02-04**, `requires_dist:
  ['tree-sitter']` with no upper bound, no `requires_python` — measured from
  `https://pypi.org/pypi/tree-sitter-languages/json`. It is ~2 years stale.
- `tree-sitter-language-pack` latest **1.25.2**, uploaded **2026-11-15**, `requires_python >=3.11`,
  `requires_dist: ['tree-sitter>=0.23']`, "Pre-compiled tree-sitter grammars for 371 programming
  languages" — measured from `https://pypi.org/pypi/tree-sitter-language-pack/json`. This is the
  maintained successor to `tree-sitter-languages` if a single bundle is ever wanted.
- The py-tree-sitter README documents exactly this API: `PY_LANGUAGE = Language(tspython.language())`,
  `parser = Parser(PY_LANGUAGE)`, `Query(PY_LANGUAGE, <source>)`, then
  `query_cursor = QueryCursor(query)` / `captures = query_cursor.captures(tree.root_node)` /
  `matches = query_cursor.matches(tree.root_node)`. It states "The difference between the two methods
  is that `QueryCursor.matches()` groups captures into matches," which is "much more useful when your
  captures within a query relate to each other." Parse input "must be encoded as UTF-8 or UTF-16" —
  [py-tree-sitter README](https://github.com/tree-sitter/py-tree-sitter/blob/master/README.md).
- Measured on this machine (Python 3.13.18, Linux):
  `pip install "tree_sitter==0.25.2" "tree_sitter_java==0.23.5"` → `Language(tree_sitter_java.language())`
  reports `abi_version == 14`, `Parser(LANG).parse(src).root_node.has_error == False` on a Spring
  controller containing a text block, a regex path variable, an array-valued `@RequestMapping`, a
  record, an enum with a per-constant body, and body-less interface methods.
- Also measured: `pip install "tree_sitter==0.26.1" "tree_sitter_java==0.23.5"` → `Language(...)`
  loads (`abi 14`), parses, and `QueryCursor(Query(L,'(method_declaration) @m')).captures(...)` works.

### Inferences / Design

```python
# requirements.txt additions (pin both; the grammar's ABI must match the runtime)
# tree_sitter==0.25.2
# tree_sitter_java==0.23.5
```

```python
"""src/extract/java_extractor.py — header"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from .common import CodeSnippet, trim_snippet

# API NOTE — this module targets py-tree-sitter 0.25.x / 0.26.x. The API moved
# twice and example code found online is usually for one of the dead shapes:
#   <=0.21:  Language(path_to_so, "java"); parser.set_language(lang); lang.query(src)
#   0.22-0.24: Language(ts_java.language()); Parser(lang); lang.query(src) -> .captures()
#   >=0.25:  Language(ts_java.language()); Parser(lang); Query(lang, src) and a
#            separate QueryCursor(query).captures()/.matches()
# Query no longer carries the cursor, so Query(...).captures(...) does not exist.
TREE_SITTER_RUNTIME = "0.25.2"
TREE_SITTER_JAVA_GRAMMAR = "0.23.5"


@lru_cache(maxsize=1)
def _language():
    import tree_sitter_java
    from tree_sitter import Language
    return Language(tree_sitter_java.language())


@lru_cache(maxsize=1)
def _parser():
    from tree_sitter import Parser
    return Parser(_language())


@lru_cache(maxsize=None)
def _query(source: str):
    """Queries are compiled once per process. Compiling a Query is the
    expensive part; QueryCursor is cheap and MUST be fresh per traversal."""
    from tree_sitter import Query
    return Query(_language(), source)


def _cursor(source: str):
    from tree_sitter import QueryCursor
    return QueryCursor(_query(source))


def parse(text: str):
    """Returns (root_node, src_bytes). Byte offsets are what every helper
    slices with, so the bytes are returned alongside the tree — decoding
    per node and re-encoding is where off-by-N bugs on non-ASCII Javadoc
    come from."""
    src = text.encode("utf-8")
    tree = _parser().parse(src)
    return tree.root_node, src


def node_text(src: bytes, node) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", "replace")
```

**The single most important API trap, measured, not theorised.** `QueryCursor.captures()` returns
`dict[str, list[Node]]` whose lists are **not positionally aligned across capture names**. Running
`(modifiers (annotation name: (_) @aname arguments: (annotation_argument_list) @args))` over the
probe file and zipping `caps["aname"]` with `caps["args"]` produced this garbage:

```
ann: Qualifier      | args: (consumes = "application/json")
ann: RequestMapping | args: ("fast")
ann: GetMapping     | args: ("select o from Order o where o.total > ?1")
```

Every annotation was paired with another annotation's arguments — which is exactly the class of
silent, plausible, backwards error this project is trying to stop producing. The same query via
`matches()` was correct:

```
RequestMapping => (value = {"/api/orders", "/api/v1/orders"}, produces = ...)
Qualifier      => ("fast")
GetMapping     => ("/{id:[0-9]+}")
PostMapping    => (consumes = "application/json")
Query          => ("select o from Order o where o.total > ?1")
Scheduled      => (cron = "0 0 * * * *")
```

**Rule for this module: `captures()` only for single-capture queries; `matches()` whenever two or
more captures in one pattern relate to each other.** `matches()` yields `(pattern_index,
dict[str, list[Node]])`; optional captures are simply absent from the dict, so read with
`caps.get("body")` and never index blindly.

A second rule: the grammar's `(modifiers)` node appears on `formal_parameter` as well as on type and
member declarations, so an unscoped `(modifiers (annotation ...))` query picks up `@Qualifier` and
`@PathVariable` from parameter lists (observed in the probe). Always anchor annotation queries to the
declaration node you mean, or walk `declaration.children` looking for `type == "modifiers"` directly —
the design below does the latter, which is both cheaper and unambiguous.

### Gaps
- `tree_sitter_java` 0.23.5 is from 2024-12-21, i.e. the grammar is ~2 years behind the runtime. It
  parsed records, text blocks, sealed-adjacent syntax and enum bodies cleanly in my probe, but I did
  not test Java 23/24/25-only syntax (e.g. primitive patterns in `switch`, module import
  declarations). tree-sitter degrades to a partial tree with `has_error == True` rather than
  crashing, so the mitigation is to **surface `root.has_error` into the record's `notes` and cap
  confidence**, which the design does. I could not verify whether a newer grammar release exists
  outside PyPI.
- I did not benchmark parse throughput. No published benchmark of tree-sitter vs regex extraction
  accuracy or speed was found in the previous round either.

---

## 2. Node names and real S-expression queries

### Takeaway
Every node name and **field name** below was dumped from the live grammar with
`node.field_name_for_child(i)`, not taken from documentation. Three of them are the usual source of
broken queries: `modifiers` is an **unnamed-field child** (you cannot write `modifiers: (modifiers)`),
`interface_declaration`'s `extends_interfaces` is likewise **unnamed** (while
`class_declaration.interfaces` and `record_declaration.interfaces` *are* named fields), and
`record_declaration` uses `parameters:`, which is easy to mis-write as `components:` — a wrong field
name raises `tree_sitter.QueryError: Impossible pattern at row R, column C` at `Query()`
construction time, which is at least loud (I hit it, on `record_declaration`).

### Cited Findings — measured field tables

| Node | Named fields (measured) | Notes |
|---|---|---|
| `program` | — | root |
| `package_declaration` | — | child `scoped_identifier` |
| `import_declaration` | — | children `scoped_identifier`, optional `asterisk` |
| `class_declaration` | `name`, `superclass`, `interfaces`, `body` | `modifiers` is an unnamed child |
| `interface_declaration` | `name`, `body` | `extends_interfaces` present as an **unnamed** child |
| `record_declaration` | `name`, `parameters` (`formal_parameters`), `interfaces`, `body` | body may be `{ }` |
| `enum_declaration` | `name`, `body` (`enum_body`) | |
| `enum_constant` | `name`, `arguments` (`argument_list`), `body` (`class_body`) | per-constant body supported |
| `enum_body_declarations` | — | the members after the `;` |
| `annotation_type_declaration` | `name`, `body` | this is `public @interface Foo` |
| `annotation_type_element_declaration` | `type`, `name`, `value` | `String value() default ""` |
| `method_declaration` | `type_parameters`, `type`, `name`, `parameters`, `body` (**optional**) | `body` absent ⇒ abstract/interface/native |
| `constructor_declaration` | `name`, `parameters`, `body` | `name` is an `identifier`, equal to the simple type name |
| `field_declaration` | `type`, `declarator` (`variable_declarator`) | `modifiers` unnamed child; multiple declarators possible |
| `variable_declarator` | `name`, `value` | |
| `formal_parameters` / `formal_parameter` | `type`, `name` | `formal_parameter` also carries its own `modifiers` |
| `modifiers` | — | contains **both** access keywords (`public`/`private`/`protected`/`static`/`final`/`abstract`/`native`/`default`/`synchronized`/`transient`/`volatile`) **and** `annotation` / `marker_annotation` children |
| `marker_annotation` | `name` | `@RestController` — no arguments node at all |
| `annotation` | `name`, `arguments` (`annotation_argument_list`) | `@RequestMapping(...)` |
| `annotation_argument_list` | — | children are either `element_value_pair` (fields `key`, `value`) or a single bare value node for the shorthand form |
| `element_value_array_initializer` | — | `{"/a","/b"}` |
| `string_literal` | — | children `"`, `string_fragment`, `"`; a **text block** is the same `string_literal` with `"""` delimiters and a `multiline_string_fragment` child |
| `block` | — | a method body |
| `static_initializer` | — | `static { ... }` |
| `block_comment` / `line_comment` | — | Javadoc is a `block_comment` whose text begins `/**` |
| `type_parameters` / `type_arguments` / `generic_type` / `type_identifier` / `void_type` / `integral_type` | — | generics are nodes, so `Map<String, List<X>>` is never split on a comma |

### Inferences / Design — the query set

```python
# ---------------------------------------------------------------- queries
# Top-level and nested type declarations. One pattern per form rather than an
# alternation, because each form has a different field set and a different
# body node type; `@decl` is the span, `@name` the identifier.
Q_TYPES = """
(class_declaration      name: (identifier) @name body: (class_body) @body) @decl
(interface_declaration  name: (identifier) @name body: (interface_body) @body) @decl
(record_declaration     name: (identifier) @name body: (class_body) @body) @decl
(enum_declaration       name: (identifier) @name body: (enum_body) @body) @decl
(annotation_type_declaration name: (identifier) @name body: (annotation_type_body) @body) @decl
"""

# Members. `body:` is written as an optional capture so that body-less
# declarations still MATCH — this is the whole fix for the brace-matcher bug
# that attached the following method's body to an abstract method.
Q_METHODS = """
(method_declaration
    type_parameters: (type_parameters)? @typeparams
    type: (_) @returntype
    name: (identifier) @name
    parameters: (formal_parameters) @params
    body: (block)? @body) @decl
"""

Q_CONSTRUCTORS = """
(constructor_declaration
    name: (identifier) @name
    parameters: (formal_parameters) @params
    body: (constructor_body) @body) @decl
"""

Q_FIELDS = """
(field_declaration
    type: (_) @fieldtype
    declarator: (variable_declarator name: (identifier) @fieldname)) @decl
"""

# Parameters, with their own annotations (@PathVariable / @RequestParam /
# @RequestBody). Scoped to formal_parameter so it cannot leak into class-level
# annotation extraction.
Q_PARAMS = """
(formal_parameter
    (modifiers (_) @pann)?
    type: (_) @ptype
    name: (identifier) @pname) @param
(spread_parameter (modifiers (_) @vann)? (_) @vtype (variable_declarator name: (identifier) @vname)) @varargs
"""

Q_PACKAGE = "(package_declaration (_) @pkg) @decl"
Q_IMPORTS = "(import_declaration) @imp"
Q_BLOCK_COMMENTS = "(block_comment) @bc"

# Side effects / in-body signals. Kept as tree queries rather than regex so a
# call inside a string literal or a comment can never match.
Q_METHOD_INVOCATIONS = """
(method_invocation name: (identifier) @callee) @call
"""
Q_THROWS = "(throw_statement) @throw"
Q_TEXT_BLOCKS = "(string_literal) @s"
```

Annotations are read by **walking the declaration's children** for `type == "modifiers"` and then
reading that node's `annotation` / `marker_annotation` children, rather than by a query — the probe
showed an unscoped `(modifiers (annotation ...))` query also matching parameter modifiers, and
walking is both unambiguous and avoids a second traversal:

```python
_ACCESS = {"public", "private", "protected"}
_OTHER_MODIFIERS = {
    "static", "final", "abstract", "native", "default", "synchronized",
    "transient", "volatile", "strictfp", "sealed", "non-sealed",
}


@dataclass
class Annotation:
    name: str                       # simple name, no '@': "RequestMapping"
    args_text: str | None           # raw text of annotation_argument_list, or None for a marker
    args: dict[str, str]            # element_value_pair key -> raw value text
    positional: list[str]           # shorthand form: @GetMapping("/x") -> ['"/x"']
    line: int                       # 1-indexed start line
    is_marker: bool


def modifiers_node(decl):
    for child in decl.children:
        if child.type == "modifiers":
            return child
    return None


def read_annotations(src: bytes, decl) -> list[Annotation]:
    mods = modifiers_node(decl)
    if mods is None:
        return []
    out: list[Annotation] = []
    for child in mods.children:
        if child.type not in ("annotation", "marker_annotation"):
            continue
        name_node = child.child_by_field_name("name")
        # name may be a scoped_identifier: @org.springframework.stereotype.Service
        simple = node_text(src, name_node).rsplit(".", 1)[-1]
        if child.type == "marker_annotation":
            out.append(Annotation(simple, None, {}, [], child.start_point[0] + 1, True))
            continue
        arglist = child.child_by_field_name("arguments")
        pairs: dict[str, str] = {}
        positional: list[str] = []
        for a in arglist.named_children:
            if a.type == "element_value_pair":
                key = node_text(src, a.child_by_field_name("key"))
                pairs[key] = node_text(src, a.child_by_field_name("value"))
            else:
                positional.append(node_text(src, a))
        out.append(Annotation(simple, node_text(src, arglist), pairs, positional,
                              child.start_point[0] + 1, False))
    return out


def access_modifiers(src: bytes, decl) -> set[str]:
    mods = modifiers_node(decl)
    if mods is None:
        return set()
    return {c.type for c in mods.children if c.type in _ACCESS | _OTHER_MODIFIERS}
```

Measured output of `read_annotations`-equivalent walking on the probe file: `modifiers` text for the
`find` method was `'@GetMapping("/{id:[0-9]+}")     public'` — i.e. the annotation and the access
keyword really are siblings inside one `modifiers` node, confirming the "modifiers contains BOTH"
premise, and confirming that `@GetMapping("/{id:[0-9]+}")` survives intact with its regex and braces
(a regex extractor's worst literal) because it is a `string_literal` inside an
`annotation_argument_list`, not text being scanned.

### Gaps
- Node names are grammar-version-specific; the previous round flagged this and it is real. The
  mitigation is a **grammar self-check at import time** (see §13, `test_grammar_contract`) that
  asserts the node and field names this module depends on still exist, so a grammar bump fails a
  test instead of silently emitting empty lists.

---

## 3. Line ranges, and why brace matching disappears

### Takeaway
`node.start_point` / `node.end_point` are `(row, column)` with a **0-indexed row**, so the project's
1-indexed inclusive convention is `(n.start_point[0] + 1, n.end_point[0] + 1)` — one expression,
total. Both `go_extractor._find_matching_brace_end_line` and
`ts_extractor._find_matching_brace_end_line` can be left untouched and simply never called from the
Java path; nothing in the Java extractor counts a brace.

### Cited Findings — measured, from the probe file
- **Body-less declarations get a correct range.** `findByCustomerIdAndStatusOrderByCreatedAtDesc`
  (an interface method ending in `;`) reported `[38, 38]` with `hasBody=False`; the `@Query`-annotated
  `fat` reported `[39, 40]` with `hasBody=False` (two lines because the annotation is part of the
  declaration node); `findActive`, a `default` method *with* a body in the same interface, reported
  `[41, 41]` with `hasBody=True`. A brace matcher asked for `findByCustomerId...`'s body would have
  walked forward to `findActive`'s `{`, which is precisely the documented "every method's line range
  shifted by one method — systematically wrong, never an error" failure. With tree-sitter the
  body-less case is `child_by_field_name("body") is None`.
- **Text blocks containing braces parse cleanly.** A method whose body held
  `String sql = """ \n select * from orders where id = {id} \n """;` parsed with
  `root.has_error == False` and the method range stopped at the right line; the text block appears as
  `string_literal` → `multiline_string_fragment`.
- **Generics do not split.** `public ResponseEntity<Map<String, List<OrderDto>>> find(...)` yielded a
  single `type: (generic_type)` return node and a `formal_parameters` node with one
  `formal_parameter`; the `>>` that breaks angle-bracket counting is a grammar concern, not ours.
- **Annotations with parenthesized multi-line arguments stay attached.** A class-level
  `@RequestMapping(value = {"/api/orders", "/api/v1/orders"},\n produces = ...)` spanning two lines
  gave `class_declaration` at `[14, 35]` with `modifiers` at `[14, 17]` and the class `identifier`
  at line 17 — so the declaration node's start line is the **annotation's** first line, not the
  `class` keyword's.

### Inferences / Design
That last point matters for two things and must be handled deliberately:

1. **The reported `lineRange` should be the whole declaration including annotations** (`decl.start_point`),
   because the annotation is the thing being explained for a Spring type. Keep a separate
   `signatureLine` = the line of the `name` identifier, used for the one-line `signature` string that
   the existing schema carries and that `function_context._params_from_signature()` parses. Emitting
   `signature` from `decl` text would otherwise put a multi-line annotation into a field the rest of
   the pipeline treats as one line.
2. **The Javadoc lookup must start above the annotations, not above the declaration line.** Since
   `decl.start_point` already includes `modifiers`, "the comment block ending on the line before
   `decl.start_point[0]`" is the correct rule and the existing
   `function_context.leading_doc_comment(lines, start_line)` would work *if* passed the declaration
   start rather than the signature line. Use the tree instead (§8) — `decl.prev_named_sibling` is
   exact and needs no line arithmetic.

```python
def line_range(node) -> tuple[int, int]:
    return (node.start_point[0] + 1, node.end_point[0] + 1)


def signature_line_of(src: bytes, decl) -> int:
    """The line the declaration's own name sits on, for the one-line
    `signature` field. decl.start_point is the first ANNOTATION line, which
    is right for lineRange and wrong for signature."""
    name = decl.child_by_field_name("name")
    return (name.start_point[0] if name is not None else decl.start_point[0]) + 1


def has_body(decl) -> bool:
    return decl.child_by_field_name("body") is not None
```

Everything flows through `trim_snippet(lines, start, end)` exactly as the Go/TS extractors do, so the
120-line cap, continuation note and `redact_secrets()` pass are inherited unchanged.

### Gaps
- None material. This is the part of the design with the least residual risk: the mechanism was
  executed against each of the four listed hazards.

---

## 4. Spring role detection that degrades honestly

### Takeaway
Match the **built-in stereotype set by simple name** and treat anything else as unknown rather than
guessing. Meta-annotation means `@RestController` contains no literal `@Controller`, so a substring
matcher is structurally incomplete; a project-local composed annotation (`@MyStereotype` meta-annotated
`@Service`) is resolvable only if the annotation's own declaration is in the scanned source, which is
often true and is worth one cheap extra pass — but when it is not resolvable the role must be
`"unknown"` with `assumed=True`, never defaulted to a plausible layer.

### Cited Findings
- `@Component` "is a generic stereotype", with `@Repository`, `@Service` and `@Controller` as
  "specializations… in the persistence, service, and presentation layers, respectively", and the
  stereotypes are **meta-annotated** — Spring's own example of a stereotype declaration is
  `@Target(ElementType.TYPE) @Retention(RetentionPolicy.RUNTIME) @Documented @Component public
  @interface Service { }` —
  [Spring Framework, Classpath Scanning](https://docs.spring.io/spring-framework/reference/7.1/core/beans/classpath-scanning.html)
  (via the prior round's notes, which quote this page directly).
- `@RestController` vs `@Controller` is a semantic difference a narration must not invert: the former
  implies `@ResponseBody` on every method (JSON out), the latter implies a returned view name
  (server-rendered template) — prior round's inference from
  [Spring Framework, Mapping Requests](https://docs.spring.io/spring-framework/reference/7.0/web/webflux/controller/ann-requestmapping.html).
- Measured: `@RestController` is a `marker_annotation` and `@Service` on `OrderServiceImpl` is a
  `marker_annotation`; a composed stereotype declaration parses as
  `annotation_type_declaration` with `modifiers` holding `@Target(...)`, `@Retention(...)` and
  `@Service` — so the meta-annotation **is** visible in the tree when the declaring file is in scope.
- The project's own validation doc records that `.java` files were classified as **"Frontend"** by
  `classify_layer` (`src/narrate/file_overview.py:229`) — so the role value this extractor emits is
  load-bearing for the file card, not decorative
  (`documentation/14-stack-support-validation.md`).

### Inferences / Design

```python
# Built-in stereotypes, keyed by SIMPLE annotation name. Values are
# (role, layer, meta_stereotype). meta_stereotype records what the annotation
# is itself meta-annotated with, so narration can say "a @RestController,
# which is a @Controller specialisation" truthfully.
BUILTIN_STEREOTYPES: dict[str, tuple[str, str, str | None]] = {
    "SpringBootApplication": ("entry_point", "bootstrap", "Configuration"),
    "RestController":        ("rest_controller", "web", "Controller"),
    "Controller":            ("mvc_controller", "web", "Component"),
    "ControllerAdvice":      ("exception_advice", "web", "Component"),
    "RestControllerAdvice":  ("exception_advice", "web", "ControllerAdvice"),
    "Service":               ("service", "business", "Component"),
    "Repository":            ("repository", "persistence", "Component"),
    "Component":             ("component", "unspecified", None),
    "Configuration":         ("configuration", "config", "Component"),
    "ConfigurationProperties": ("config_properties", "config", None),
    "Entity":                ("jpa_entity", "persistence", None),       # jakarta.persistence, NOT a bean
    "Embeddable":            ("jpa_embeddable", "persistence", None),
    "MappedSuperclass":      ("jpa_mapped_superclass", "persistence", None),
    "Aspect":                ("aspect", "cross_cutting", None),         # AspectJ, usually + @Component
}

# Annotations that mark the type as a Spring-managed bean (for the DI graph).
BEAN_STEREOTYPES = {
    "SpringBootApplication", "RestController", "Controller", "ControllerAdvice",
    "RestControllerAdvice", "Service", "Repository", "Component", "Configuration",
}

ROLE_UNKNOWN_NOTE = (
    "This type carries annotation(s) {anns} that are not in the built-in Spring "
    "stereotype set and whose own declaration was not found in the scanned source, so its "
    "role in the application could not be determined. Spring stereotypes are "
    "meta-annotated, so an annotation can be a @Component without saying so in its "
    "name. Verify by opening the annotation's declaration."
)


@dataclass
class SpringRole:
    role: str                  # "rest_controller" | ... | "unknown" | "plain_type"
    layer: str
    is_bean: bool
    via: str                   # "builtin" | "composed:<AnnName>" | "none"
    annotations: list[str]
    assumed: bool
    note: str | None


def resolve_role(
    annotations: list[Annotation],
    composed_index: dict[str, str] | None = None,
) -> SpringRole:
    """`composed_index` maps a project-local annotation's simple name to the
    BUILT-IN stereotype it is (transitively) meta-annotated with, built by a
    pre-pass over every `annotation_type_declaration` in the repo. Absent that
    mapping an unrecognised annotation yields role='unknown', assumed=True —
    the one thing we must not do is pick a layer that looks right."""
    names = [a.name for a in annotations]

    for name in names:                       # built-in wins, first match in declaration order
        if name in BUILTIN_STEREOTYPES:
            role, layer, _meta = BUILTIN_STEREOTYPES[name]
            return SpringRole(role, layer, name in BEAN_STEREOTYPES, "builtin",
                              names, False, None)

    for name in names:                       # project-local composed annotation
        target = (composed_index or {}).get(name)
        if target and target in BUILTIN_STEREOTYPES:
            role, layer, _meta = BUILTIN_STEREOTYPES[target]
            return SpringRole(
                role, layer, target in BEAN_STEREOTYPES, f"composed:{name}", names, True,
                f"Role inferred from the project-local annotation @{name}, which is "
                f"meta-annotated @{target}. Verify the annotation declaration.",
            )

    if names:
        return SpringRole("unknown", "unknown", False, "none", names, True,
                          ROLE_UNKNOWN_NOTE.format(anns=", ".join("@" + n for n in names)))

    # No annotations at all: a DTO, a helper, a plain POJO. Not a guess.
    return SpringRole("plain_type", "unspecified", False, "none", [], False, None)
```

The composed-annotation pre-pass is ~20 lines and runs once per repo:

```python
def build_composed_annotation_index(files: dict[str, str]) -> dict[str, str]:
    """simple annotation name -> the built-in stereotype it resolves to,
    transitively. Only sees annotations DECLARED in the scanned source; a
    composed annotation from a dependency jar is unresolvable here and must
    stay 'unknown' (tree-sitter is syntax-only and never reads a jar)."""
    direct: dict[str, set[str]] = {}
    for text in files.values():
        root, src = parse(text)
        for _pi, caps in _cursor(
            "(annotation_type_declaration name: (identifier) @n) @decl"
        ).matches(root):
            decl, name = caps["decl"][0], node_text(src, caps["n"][0])
            direct[name] = {a.name for a in read_annotations(src, decl)}

    resolved: dict[str, str] = {}
    for name in direct:
        seen, frontier = set(), [name]
        while frontier:
            current = frontier.pop()
            if current in seen:
                break                      # cyclic meta-annotation; give up, stay unknown
            seen.add(current)
            for meta in direct.get(current, ()):
                if meta in BUILTIN_STEREOTYPES:
                    resolved[name] = meta
                    frontier = []
                    break
                frontier.append(meta)
    return resolved
```

Note `@Entity` is deliberately **not** in `BEAN_STEREOTYPES`: it is a JPA annotation, not a Spring
stereotype, and treating an entity as a bean would put every entity into the DI graph as an
injectable. The role is still reported, because "this is the persisted shape of an Order" is exactly
what a viewer needs.

### Gaps
- `@Qualifier` / `@Primary` / `@Fallback` precedence is still uncited (flagged in the prior round:
  those pages were not fetched). The design therefore does not try to pick a winner among multiple
  candidates — it emits all of them with `assumed=True`.
- A composed stereotype defined in a **dependency jar** (common in corporate shared-starter setups)
  cannot be resolved by any syntax-only tool. It lands in `role="unknown"`, `assumed=True`.

---

## 5. Route extraction and the concatenation algorithm

### Takeaway
The effective URL is `context-path` + class-level `@RequestMapping` path + method-level mapping path,
with **paths multiplying** on array values and **`consumes`/`produces` overriding rather than
extending**. The algorithm is a cross-product over (class paths × method paths), each component
normalised, with any non-literal component (`${…}`, `#{…}`, a constant reference) marked unresolved
and propagated to `assumed=True`.

### Cited Findings
- Class-level `@RequestMapping("/persons")` + method-level `@GetMapping("/{id}")` is "effectively
  /persons/{id}", and a bare `@PostMapping` with no path argument is "effectively /persons" — the
  docs state the combined paths in their own example's comments —
  [Spring Framework, Mapping Requests](https://docs.spring.io/spring-framework/reference/7.0/web/webflux/controller/ann-requestmapping.html)
- Shortcut variants are `@GetMapping`, `@PostMapping`, `@PutMapping`, `@DeleteMapping`,
  `@PatchMapping`; plain `@RequestMapping` "by default, matches to all HTTP methods"; `@GetMapping`
  "support[s] HTTP HEAD transparently for request mapping purposes" — *ibid.*
- `{name:[a-z]+}` "Matches the regexp `[a-z]+` as a path variable named 'name'"; `{*path}` captures
  trailing segments; `**` matches zero or more path segments; "only a single `**`/`{*path}` instance
  is allowed per pattern" — *ibid.*
- Paths may be non-literal: "Embedded `${…}` placeholders" are "resolved on startup via
  `PropertySourcesPlaceholderConfigurer`", and SpEL `#{…}` expressions are supported — *ibid.*
- `consumes`/`produces`: "when used at the class level, a method-level `consumes` attribute
  **overrides rather than extends** the class-level declaration", identically for `produces`;
  negation (`!text/plain`) is supported — *ibid.*
- Only one mapping annotation per element; if several are found "a warning will be logged, and only
  the first mapping will be used" — *ibid.*
- The mapping may live on an **interface** the controller implements, via
  `@HttpExchange`/`@GetExchange`/`@PostExchange` (`@HttpExchange("/persons") interface PersonService`,
  `class PersonController implements PersonService`) — *ibid.*
- `server.servlet.context-path` (and `spring.webflux.base-path`) prepend a further prefix from
  `application.properties`/`application.yml`. **The prior round flagged this as unverified against a
  source**, and I did not verify it either — it is handled here as an *optional, clearly-labelled*
  prefix, not as a silent rewrite.
- Measured: the array form survives parsing intact — `@RequestMapping` args came back as
  `value = {"/api/orders", "/api/v1/orders"}, produces = MediaType.APPLICATION_JSON_VALUE`, with
  `value`'s value node typed `element_value_array_initializer` and `produces`' value an
  `identifier`-ish expression (so a non-literal `produces` is detectable by node type, not by regex).

### Inferences / Design

```python
MAPPING_ANNOTATIONS = {
    "GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT",
    "DeleteMapping": "DELETE", "PatchMapping": "PATCH",
    "RequestMapping": None,          # verb comes from method= or is ALL
    # Spring HTTP interface forms — the mapping lives on an interface.
    "HttpExchange": None, "GetExchange": "GET", "PostExchange": "POST",
    "PutExchange": "PUT", "DeleteExchange": "DELETE", "PatchExchange": "PATCH",
}

_PLACEHOLDER_RE = re.compile(r"\$\{[^}]*\}")
_SPEL_RE = re.compile(r"#\{[^}]*\}")


def annotation_paths(ann: Annotation) -> tuple[list[str], bool, str | None]:
    """Returns (paths, unresolved, reason).

    Reads the shorthand @GetMapping("/x"), the explicit value=/path= forms, and
    the array form {"/a","/b"} (which MULTIPLIES the routes). A non-literal
    value — ${...}, #{...}, or a bare identifier such as Api.ORDERS — is
    reported as unresolved rather than emitted verbatim: a ${...} printed as a
    URL is a URL that does not exist in the running app.
    """
    raw = ann.positional[:] or []
    for key in ("value", "path"):
        if key in ann.args:
            raw.append(ann.args[key])
    if not raw:
        return [""], False, None            # bare @PostMapping -> inherits class path exactly

    paths, unresolved, reason = [], False, None
    for item in raw:
        item = item.strip()
        if item.startswith("{"):            # array initialiser text: {"/a", "/b"}
            parts = re.findall(r'"((?:[^"\\]|\\.)*)"', item)
            if not parts:
                unresolved, reason = True, "array-valued path contained no string literals"
            paths.extend(parts)
            continue
        if item.startswith('"'):
            literal = item[1:-1]
            if _PLACEHOLDER_RE.search(literal):
                unresolved = True
                reason = ("path contains a ${...} property placeholder resolved at startup "
                          "by PropertySourcesPlaceholderConfigurer; the literal text is not the URL")
            elif _SPEL_RE.search(literal):
                unresolved = True
                reason = "path contains a #{...} SpEL expression evaluated at startup"
            paths.append(literal)
            continue
        # a constant/enum reference: Api.ORDERS, PATHS.BASE + "/x"
        unresolved = True
        reason = (f"path is the non-literal expression `{item}`; resolving it needs type "
                  f"resolution (a JavaParser JVM sidecar), which tree-sitter cannot do")
        paths.append("")
    return (paths or [""]), unresolved, reason


def join_path(*segments: str) -> str:
    """Spring's own example: '/persons' + '' -> '/persons' (no trailing slash),
    '/persons' + '/{id}' -> '/persons/{id}'. Collapse duplicate slashes; keep a
    single leading slash; never emit a trailing slash except for the root."""
    parts: list[str] = []
    for seg in segments:
        for piece in (seg or "").split("/"):
            if piece:
                parts.append(piece)
    return "/" + "/".join(parts) if parts else "/"


_PATH_VAR_RE = re.compile(r"\{([^{}]+)\}")


def path_variables(path: str) -> list[dict]:
    """`{name:[a-z]+}` is legal, so split on the FIRST colon: the name is
    before it, the regex constraint after. `{*path}` captures trailing
    segments."""
    out = []
    for body in _PATH_VAR_RE.findall(path):
        if body.startswith("*"):
            out.append({"name": body[1:], "pattern": None, "capturesTrailing": True})
            continue
        name, _, pattern = body.partition(":")
        out.append({"name": name.strip(), "pattern": (pattern.strip() or None),
                    "capturesTrailing": False})
    return out
```

**The concatenation algorithm**, in order:

1. Build the class context: resolve `@RequestMapping`/`@HttpExchange` on the type →
   `class_paths: list[str]` (default `[""]`), `class_consumes`, `class_produces`,
   `class_unresolved`.
   If the type declares `implements I` and `I` carries `@HttpExchange`, record
   `inheritedMappingFrom = "I"` and use `I`'s paths **with `assumed=True`** — tree-sitter resolves
   the *name* `I`, never the type, so if `I` is not in the scanned source this is simply not
   available and must be reported as "mapping may be inherited from an implemented interface not
   found in source".
2. For each method, find the **first** mapping annotation only (per the docs: additional ones are
   ignored with a warning) → `method_paths`, `method_unresolved`.
3. `verb`: from the annotation name; for plain `@RequestMapping` from `method = RequestMethod.X`
   (or the array form, which multiplies verbs); if neither, `verb = "ALL"` with a note. For `GET`,
   emit `alsoServes: ["HEAD"]`.
4. `effective_paths = [join_path(context_path, c, m) for c in class_paths for m in method_paths]` —
   a cross-product, so a 2-path class × 2-path method correctly yields 4 routes.
5. `consumes`/`produces` = method value **if present, else** class value (override, not merge).
6. `type` = `"dynamic"` if the path contains `{`, `*` or `?`; else `"static"` — matching the
   `static_or_dynamic` vocabulary `go_extractor.ExtractedRoute` already uses.
7. `assumed = class_unresolved or method_unresolved or context_path_assumed or
   inherited_mapping or verb == "ALL"`, with the reasons concatenated into `notes`.
8. `protected`: `True` only if `@PreAuthorize`/`@Secured`/`@RolesAllowed` sits on the method or the
   class. **Always `assumed=True`**, exactly as the Go extractor does for `.Use()`, because
   `SecurityFilterChain`/`HttpSecurity` rules live in a `@Configuration` class and match by URL
   pattern — a fact that requires cross-file URL-pattern matching this extractor does not do.

The context path:

```python
def read_context_path(root: Path, resource_dirs: list[str]) -> tuple[str, bool, str | None]:
    """server.servlet.context-path (MVC) / spring.webflux.base-path (WebFlux)
    from application.properties / application.yml. Returns (path, assumed, note).

    Deliberately shallow: the real value can come from a profile-specific file,
    an environment variable, a command-line arg or a ${...} placeholder, and
    which profile is active at runtime is not a static fact. So: use it when a
    single unambiguous literal is found, and ALWAYS carry a note saying the
    prefix came from config and may be overridden per environment. The prior
    research round flagged this behaviour as unverified against a primary
    source — do not promote it to a confident claim without checking.
    """
```

Route record, mapped onto the existing shape plus Spring-only extras (additive keys; nothing
removed, so `feature_mapping.match_calls_to_routes()` keeps working):

```python
{
  "path": "/api/orders/{id}", "method": "GET", "type": "dynamic",
  "routingLibrary": "spring-web-mvc",          # or "spring-webflux"
  "protected": False, "assumed": True,
  "handler": "OrderController.find",
  "notes": "Protected status is inferred only from @PreAuthorize/@Secured on this "
           "method or class; Spring Security rules declared in a SecurityFilterChain "
           "bean match by URL pattern in another file and are not analysed here. "
           "@GetMapping also serves HTTP HEAD.",
  # additive
  "pathVariables": [{"name": "id", "pattern": "[0-9]+", "capturesTrailing": False}],
  "consumes": None, "produces": ["application/json"],
  "requestBodyType": "OrderDto", "responseType": "ResponseEntity<Page<OrderDto>>",
  "requestParams": [{"name": "size", "required": False, "defaultValue": "10", "type": "int"}],
  "alsoServes": ["HEAD"],
  "contextPathApplied": "/api", "contextPathSource": "application.yml",
}
```

`requestBodyType` is the link from the route to `dataModels` and is the highest-value field for
narration ("POST /api/orders takes an OrderDto"); it is read from the parameter carrying
`@RequestBody` via `Q_PARAMS`, which the probe confirmed resolves cleanly
(`@RequestBody OrderDto dto` → `ptype=OrderDto`, `pname=dto`).

### Gaps
- `server.servlet.context-path` remains **uncited**. Treat the implementation as "best-effort,
  always noted", not as settled behaviour.
- MVC vs WebFlux suffix matching differs (`/person` also matching `/person.*` in MVC) and the prior
  round's route citations come from the **WebFlux** mirror because the MVC page was blocked. The
  concatenation rule and annotation names are identical across the two; suffix matching is not
  modelled here at all.
- `@RequestParam` / `@RequestBody` binding details (`required`, `defaultValue`, converters) are
  documented on pages that were not fetched in either round.

---

## 6. Spring Data repositories: the method name *is* the query

### Takeaway
A repository interface has **no method bodies**, so the honest output is not "0 functions, no
implementation" but a list of *derived queries*: for each method, the parsed subject/predicate of its
name rendered as a plain-English sentence, flagged `derivedFrom: "method-name"`. When an `@Query`
annotation is present the name is **not** the query and the annotation value is — getting that
backwards would narrate a false statement about the code.

### Cited Findings
- "[P]arsing query method names is divided into subject and predicate", concatenated with
  `And`/`Or`, with `OrderBy`, `Distinct`, `Top`/`First`, and `_` for nested property traversal —
  [Spring Data JPA Reference 3.1.12](https://docs.spring.io/spring-data/jpa/docs/3.1.12/reference/html/)
- Repository methods carry **no modifier at all** in source (`User findByEmailAddress(EmailAddress
  emailAddress);`) yet are implicitly `public` — *ibid.*
- Spring Data repository implementations **do not exist as source files**: Spring "create[s] proxy
  instances for those interfaces", routing base methods to `SimpleJpaRepository` — *ibid.*
- Measured: in the probe interface, `findByCustomerIdAndStatusOrderByCreatedAtDesc` parsed as
  `method_declaration [38,38]` with `hasBody=False` and `modifiers=None`; the `@Query`-annotated
  method parsed with `modifiers='@Query("select o from Order o where o.total > ?1")'` and
  `hasBody=False`; and `default List<Order> findActive() { ... }` in the *same* interface parsed with
  `hasBody=True`, `modifiers='default'`. All three forms are distinguishable without heuristics.

### Inferences / Design

```python
_SUBJECT_RE = re.compile(
    r"^(?P<verb>find|read|get|query|search|stream|count|exists|delete|remove)"
    r"(?P<distinct>Distinct)?"
    r"(?P<limit>Top\d*|First\d*)?"
    r"(?:All)?"
    r"(?:By(?P<predicate>.*))?$"
)
_ORDER_SPLIT_RE = re.compile(r"OrderBy(?P<order>.+)$")
# Longest-first so GreaterThanEqual is not matched as GreaterThan.
_KEYWORDS = [
    ("IsNotNull", "is not null"), ("IsNull", "is null"), ("NotNull", "is not null"),
    ("GreaterThanEqual", "is >= "), ("LessThanEqual", "is <= "),
    ("GreaterThan", "is greater than"), ("LessThan", "is less than"),
    ("Between", "is between"), ("StartingWith", "starts with"),
    ("EndingWith", "ends with"), ("Containing", "contains"), ("Like", "is like"),
    ("NotIn", "is not in"), ("In", "is in"), ("True", "is true"), ("False", "is false"),
    ("IgnoreCase", "ignoring case"), ("Not", "is not"), ("Is", "equals"), ("Equals", "equals"),
]


@dataclass
class DerivedQuery:
    method_name: str
    source: str                  # "method-name" | "@Query" | "@NativeQuery" | "inherited" | "default-method"
    verb: str | None             # find | count | exists | delete ...
    distinct: bool
    limit: str | None            # "Top5" / "First"
    conditions: list[str]        # ["customerId equals", "status equals"]
    combinator: str | None       # "And" | "Or" | None
    order_by: list[str]
    sentence: str                # the narration-ready English
    query_text: str | None       # the @Query value, when that is the query
    modifying: bool              # @Modifying
    assumed: bool
    note: str | None


def parse_derived_query(name: str) -> DerivedQuery | None:
    m = _SUBJECT_RE.match(name)
    if not m:
        return None
    predicate = m.group("predicate") or ""
    order: list[str] = []
    om = _ORDER_SPLIT_RE.search(predicate)
    if om:
        predicate = predicate[: om.start()]
        order = _split_camel(om.group("order"))
    combinator = "And" if "And" in predicate else ("Or" if "Or" in predicate else None)
    raw_terms = re.split(r"And|Or", predicate) if predicate else []
    conditions = [_render_term(t) for t in raw_terms if t]
    ...
```

`_render_term()` strips the longest matching keyword suffix, converts the remaining CamelCase
property path (`_` → nested traversal) to words, and appends the keyword's English. The resulting
`sentence` is what the narrator speaks:

| Method name | Emitted sentence |
|---|---|
| `findByEmailAddress` | "finds records where email address equals the given value" |
| `findByCustomerIdAndStatusOrderByCreatedAtDesc` | "finds records where customer id equals the given value and status equals the given value, ordered by created at, descending" |
| `findDistinctTop5ByStatusIn` | "finds the first 5 distinct records where status is in the given values" |
| `countByActiveTrue` | "counts records where active is true" |
| `deleteByOrderId` | "deletes records where order id equals the given value" |

Per-method classification, in strict priority order (this ordering *is* the correctness requirement):

1. `@Query` present → `source="@Query"`, `query_text = the annotation value`, and
   `sentence = "runs the declared JPQL/SQL query shown above"`. **Do not parse the method name.**
   `nativeQuery = true` in the annotation args → `source="@NativeQuery"`. `@Modifying` → `modifying=True`
   and the narration must say it writes.
2. `has_body(decl)` is True (a `default` or `static` interface method) → `source="default-method"`,
   and it is emitted as a normal `importantFunctions` entry with a real snippet, because it has real
   logic. This is where repository-level shared logic hides.
3. Name matches `_SUBJECT_RE` → `source="method-name"`, parsed as above, `assumed=False` for the
   grammar but with the note below.
4. Name does not match → `assumed=True`, `note="This interface method's name does not match Spring
   Data's derived-query grammar, so it is either a custom implementation in a <Name>Impl fragment
   class or resolved by a @NamedQuery. Verify."`

Every derived query carries this note regardless:

> "This interface declares no body. Spring Data generates the implementation at runtime as a proxy
> over SimpleJpaRepository, so there is no source file to show. The behaviour described here was read
> from the method name using Spring Data's derived-query grammar; the property names were not checked
> against the entity's fields, which would need type resolution."

And the *interface itself* must carry, in `notes`, the inherited-surface disclosure: `extends
JpaRepository<Order, Long>` means ~20 further public methods (`save`, `findAll`, `deleteById`, …)
exist on this type and appear nowhere in the file. Emit
`inheritedRepositoryBase: "JpaRepository<Order, Long>"` with `entityType: "Order"`,
`idType: "Long"` (read from the `type_arguments` node of the `extends_interfaces` child) and a note
saying the inherited methods were not enumerated because their declarations are in a dependency jar.

Where these land in the record:

- Each derived-query method → one `importantFunctions` entry whose `codeSnippet` is the single
  declaration line (via `trim_snippet`), `description` = the generated `sentence`,
  `descriptionSource` = `"derived-query-name"` (a new value alongside the existing `"doc-comment"`),
  plus `hasBody: False`.
- `sideEffects` gets one `{"type": "database_call", "description": "..."}` per repository method —
  this is the Java analogue of the Go extractor's `.Query/.Exec` patterns, and it is more reliable
  than them because it comes from the annotation, not a method-name regex.

### Gaps
- The full Spring Data keyword table (every `IsLessThanEqual`/`AfterOrEquals`-style alias) was not
  fetched; the table above is the common subset named in the cited reference plus standard aliases.
  Unknown keyword suffixes must fall through to "equals" **with `assumed=True`**, not be dropped.
- `@NamedQuery` and `<Name>Impl` custom-fragment resolution needs cross-file type resolution and is
  out of scope for a syntax-only extractor.

---

## 7. Visibility: the decision table and the minimal schema change

### Takeaway
Java visibility is a **per-member keyword whose default depends on the enclosing declaration**, and
neither existing heuristic works: `signature.startswith("export")` marks every Java declaration
unexported, and the Go capital-letter rule is uncorrelated (`public void save()` reads as internal,
`private static final int MAX` reads as exported). The right output is a `visibility` string plus a
separate `isFrameworkEntryPoint` flag, with the existing `exported` boolean **retained** and
redefined as "reachable from outside this type" so nothing downstream breaks.

### Cited Findings
- Interface members in Spring Data repositories "carry no modifier at all in the source … yet are
  implicitly `public`" — [Spring Data JPA Reference 3.1.12](https://docs.spring.io/spring-data/jpa/docs/3.1.12/reference/html/)
- Spring notes "an annotated constructor does not have to be public" — a `private` or
  package-private constructor can be the injection point —
  [Spring Framework, Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- Record components generate `private final` fields with `public` accessors of the same name, a
  record class "is implicitly `final`", and nested records "are implicitly static" — modifiers can be
  implicit and absent from the source text — [Oracle, Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html)
- Measured: `modifiers` for `abstract void noBody();` was `'abstract'` with no access keyword;
  for `@Autowired private final OrderService svc;` it was `'@Autowired   private final'`; for an
  interface method with no modifier, `modifiers` was `None`. So "absent" is observable as either a
  missing `modifiers` node or a `modifiers` node with no member of `{public, private, protected}`.

### Inferences / Design — the decision table

| Declared in | Explicit keyword | → `visibility` | `exported` | Why |
|---|---|---|---|---|
| class / record / enum body | `public` | `public` | True | |
| class / record / enum body | `protected` | `protected` | True | visible to subclasses and the package |
| class / record / enum body | `private` | `private` | False | |
| class / record / enum body | *absent* | `package-private` | False | the Java default |
| **interface** body (method, nested type, field) | *absent* | `public` | **True** | implicitly public; interface fields are also `public static final` |
| interface body | `private` (Java 9+ private interface method) | `private` | False | legal since 9 |
| interface body | `default` / `static` only | `public` | True | `default` is not an access modifier |
| **annotation** (`@interface`) body element | *absent* | `public` | True | same rule as interface |
| **enum constant** | *absent* | `public` | True | implicitly `public static final` |
| **record component** (in the header) | — | `private` field + `public` accessor | True | one identifier, two visibilities; emit `accessorVisibility: "public"` |
| top-level type | *absent* | `package-private` | False | and it may not match the filename |
| top-level type | `public` | `public` | True | must match the filename |
| any member of a `private`/package-private nested type | anything | *as declared* | **False** | visibility is inherited downward — a `public` method of a `private static class Row` is not reachable from outside |

```python
INTERFACE_LIKE_BODIES = {"interface_body", "annotation_type_body"}


def visibility_of(src: bytes, decl) -> tuple[str, str]:
    """Returns (visibility, source) where source is 'explicit' or
    'implicit-<context>' so the record can say WHY, not just WHAT."""
    mods = access_modifiers(src, decl)
    for keyword in ("public", "protected", "private"):
        if keyword in mods:
            return keyword, "explicit"
    parent = decl.parent.type if decl.parent is not None else "program"
    if parent in INTERFACE_LIKE_BODIES:
        return "public", f"implicit-{parent}"
    if decl.type == "enum_constant":
        return "public", "implicit-enum_constant"
    return "package-private", f"implicit-{parent}"


def externally_reachable(visibility: str, enclosing_chain: list[str]) -> bool:
    """`exported`, redefined for Java as 'callable from outside this type'.
    Visibility is inherited downward: a public method of a private nested
    class is not reachable."""
    if visibility in ("private", "package-private"):
        return False
    return all(v in ("public", "protected") for v in enclosing_chain)
```

**Minimal schema change** — three additive keys and one narrow edit, nothing removed:

1. In `src/extract/function_context.py`, add a `java` branch to `is_exported()`:

```python
def is_exported(signature: str, name: str, language: str) -> bool:
    if language == "go":
        return bool(name) and name[0].isupper()
    if language == "java":
        # Java has no `export` token and the Go capital rule is uncorrelated
        # (every type name is capitalised; `public void save()` is not).
        # The real answer is computed from the declaration's modifiers in
        # java_extractor.visibility_of(), so the java path never relies on
        # this fallback — it passes `exported` in explicitly. Returning False
        # here is a deliberate "unknown", not a claim.
        return False
    return signature.lstrip().startswith("export")
```

2. Give `build_function_context()` an optional `exported_override: bool | None = None` parameter and
   use it when not `None`. This is the whole integration cost: the Java builder computes
   `exported` properly and passes it, and the TS/Go callers are untouched.
3. Add to each `importantFunctions` entry: `"visibility": str`, `"visibilitySource": str`,
   `"isFrameworkEntryPoint": bool`, `"hasBody": bool`, `"enclosingType": str`,
   `"nestingDepth": int`, `"overloadKey": "name(Type1,Type2)"`.

`overloadKey` is not optional nicety: `save(Order)` and `save(Order, boolean)` collapse under any
name-keyed map, and `function_context.callers_of()` / `calls_made()` are name-keyed regex matches
over bodies. For Java, both will over-match overloads. The honest fix within scope: keep them, but
when a chunk contains two methods with the same `name`, set `assumed=True` on those entries'
`calledBy`/`calls` and attach "this chunk contains overloads of `<name>`; caller/callee attribution
between them was not resolved (that needs argument-type matching)".

`isFrameworkEntryPoint` is `True` for: any handler method with a mapping annotation, `@Scheduled`,
`@EventListener`, `@KafkaListener`/`@RabbitListener`/`@JmsListener`, `@ExceptionHandler`,
`@PostConstruct`/`@PreDestroy`, `@Bean` methods, and `public static void main`. These are the methods
with zero in-project callers that are *not* dead — see §10.

### Gaps
- JLS §6.6 access-control rules and the implicit-`public`-on-interface-members rule are standard
  Java but remain **uncited** in both rounds; the table above is engineering knowledge corroborated
  by the Spring Data quote and by my measurement that interface methods parse with `modifiers=None`.

---

## 8. Javadoc: avoiding the license-header trap

### Takeaway
The trap is real and the fix is three conditions, not one: the comment must (a) be a `block_comment`
whose text starts with exactly `/**` (not `/*`), (b) be the declaration's immediately-preceding
sibling in the tree, and (c) survive the boilerplate filter. Measured: the probe file's license block
and its Javadoc are **both** `block_comment` nodes (lines 1 and 9), distinguishable only by their
first three characters — so the `/**` test is load-bearing, and `function_context._strip_comment_markers()`
currently does `re.sub(r"^/\*\*?", "", text)`, which accepts both.

### Cited Findings
- Javadoc leading-asterisk stripping is **conditional**: "[i]f you omit the leading asterisk on a
  line, then the leading whitespace is no longer removed" — so stripping must be per-line and only
  where the asterisk is present, to preserve pasted code examples —
  [Oracle, Doc Comment Spec](https://docs.oracle.com/en/java/javase/22/docs/specs/javadoc/doc-comment-spec.html)
- "[A] missing item is considered as if it were provided with `{@inheritDoc}`" — an `@Override`
  method with no comment may be fully documented on a supertype — *ibid.*
- `{@code A<B>C}` is documented as displaying unchanged — braces and angle brackets legitimately
  appear inside comments — *ibid.*
- Javadoc contains embedded HTML (`<p>`, `<pre>`, `&#064;`) and the `@param <E> description` form for
  type parameters, which looks like a JSDoc type brace — *ibid.*
- Measured: the class-level Javadoc on the probe's `OrderController` sits at lines 9–13, the
  `class_declaration` starts at line **14** (its `modifiers`, i.e. `@RestController`), and the class
  `identifier` is at line **17**. A "comment on the line immediately above the declaration" rule
  anchored on the signature line would look at line 16 and find an annotation — which is exactly the
  documented failure "annotations sit BETWEEN the doc comment and the declaration". Anchored on
  `decl.start_point` (line 14) it finds the comment ending at 13. Correct.

### Inferences / Design

```python
_JAVADOC_TAG_RE = re.compile(r"^@\w+")
_INLINE_TAG_RE = re.compile(r"\{@(?:code|literal|link|linkplain|value|index)\s+([^}]*)\}")
_INHERITDOC_RE = re.compile(r"\{@inheritDoc\}")
_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
_HTML_ENTITY = {"&lt;": "<", "&gt;": ">", "&amp;": "&", "&quot;": '"',
                "&nbsp;": " ", "&#064;": "@", "&#38;": "&"}
# Reuses the project's stance in function_context._BOILERPLATE_RE, extended
# for Java's license vocabulary.
_LICENSE_RE = re.compile(
    r"^(copyright|\(c\)|license|licensed|spdx|all rights reserved|"
    r"apache license|gnu general public|mit license|redistribution and use)",
    re.IGNORECASE,
)


def javadoc_for(src: bytes, decl) -> tuple[str | None, dict, bool, str | None]:
    """Returns (prose, tags, inherits_doc, note).

    Anchored on decl.prev_named_sibling, NOT on a line above the signature:
    tree-sitter puts the annotations inside the declaration node, so the
    declaration's previous sibling is the doc comment even when four
    annotations sit between the comment text and the `class`/`public` keyword.
    """
    prev = decl.prev_named_sibling
    if prev is None or prev.type != "block_comment":
        return None, {}, False, None
    raw = node_text(src, prev)
    if not raw.startswith("/**"):
        # A plain /* ... */ block. Essentially every corporate Java file opens
        # with one and it is a LICENSE, not documentation. Returning it would
        # make every file's description a license notice.
        return None, {}, False, None

    body = raw[3:]
    body = body[:-2] if body.endswith("*/") else body
    lines_out: list[str] = []
    for line in body.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("*"):
            lines_out.append(stripped[1:].lstrip(" "))   # conditional: only when the * is there
        else:
            lines_out.append(line)                       # preserve indentation of pasted code

    prose_lines, tags, current_tag = [], {}, None
    for line in lines_out:
        token = line.strip()
        if _JAVADOC_TAG_RE.match(token):
            tag, _, rest = token.partition(" ")
            # `@param <E> element type` — the type-parameter form. Key it as
            # 'param:<E>' so it is never mistaken for a parameter named '<E>'.
            if tag == "@param" and rest.strip().startswith("<"):
                name, _, desc = rest.strip().partition(">")
                current_tag = f"param:{name}>"
                tags[current_tag] = desc.strip()
            else:
                name, _, desc = rest.strip().partition(" ")
                current_tag = f"{tag[1:]}:{name}" if tag in ("@param", "@throws", "@exception") else tag[1:]
                tags[current_tag] = desc.strip() or name
            continue
        if current_tag:
            tags[current_tag] = (tags[current_tag] + " " + token).strip()
        else:
            prose_lines.append(token)

    prose = " ".join(p for p in prose_lines if p)
    inherits = bool(_INHERITDOC_RE.search(prose))
    prose = _INHERITDOC_RE.sub("", prose)
    prose = _INLINE_TAG_RE.sub(r"\1", prose)       # {@code Foo} -> Foo, before HTML stripping
    prose = _HTML_TAG_RE.sub(" ", prose)           # <p>, <pre>, <ul> -> gone, never spoken
    for entity, char in _HTML_ENTITY.items():
        prose = prose.replace(entity, char)
    prose = re.sub(r"\s+", " ", prose).strip()

    if not prose or _LICENSE_RE.match(prose) or len(prose.split()) < 3:
        return None, tags, inherits, None
    from src.security.guardrails import redact_secrets
    prose, _ = redact_secrets(prose)             # same choke point as the rest of the pipeline
    return prose, tags, inherits, None
```

Three further rules:

- **`{@inheritDoc}` / an undocumented `@Override`.** When `prose` is empty (or carries
  `{@inheritDoc}`) and the method has `@Override`, emit `description = None` with
  `descriptionSource = "inherited-not-resolved"` and a note: "this method's documentation lives on
  the supertype it overrides; resolving which supertype needs type resolution (a JavaParser JVM
  sidecar), so it was not read." Never substitute a guess, and never report the file's license.
- **File-level description.** `function_context.file_header_comment()` takes the comment that *opens*
  the file. In Java that is the license in most real repos, and its `_BOILERPLATE_RE` catches
  `copyright|license|licensed|spdx` but not "All Rights Reserved" or "Apache License" on its own
  line. For Java, `fileDescription` must come from the **primary type's Javadoc**, not the file's
  first comment — because for a Spring file "what this file is for" and "what this class is" are the
  same question. Fall back to `None`, not to the license.
- **Ordering before TTS.** Inline-tag unwrapping must happen *before* HTML stripping, or
  `{@code List<E>}` loses `<E>` to the HTML regex.

### Gaps
- `_LICENSE_RE` is a heuristic keyword list. A license header with unusual wording will slip through;
  the `len(prose.split()) < 3` and `/**`-prefix conditions are the backstops. A stricter option not
  taken here: reject any candidate description containing a four-digit year plus an organisation-like
  token.

---

## 9. Lombok: members that are not in the source

### Takeaway
Report Lombok as an explicit, named uncertainty on the chunk — a `generatedMembers` list naming what
*ought* to exist with `assumed=True` — and, critically, when `@RequiredArgsConstructor`/`@AllArgsConstructor`
is present and **no `constructor_declaration` node exists**, treat the `private final` fields as the
injection points, because that is where they are.

### Cited Findings
- Lombok (`@Getter`, `@Setter`, `@Data`, `@Builder`, `@RequiredArgsConstructor`, `@Value`) "creates
  public members that **do not appear in the source at all**. A file using `@Data` has a public API
  far larger than its text. This should be flagged in output, not silently omitted" — prior round's
  inference in `documentation/research/pipeline-support-across-six-stacks/spring_boot.md`.
- Spring: "An `@Autowired` annotation on such a constructor is not necessary if the target bean
  defines only one constructor" and "[i]f a class only declares a single constructor to begin with,
  it will always be used, even if not annotated" — so a Lombok-generated single constructor is
  wired with nothing in the source marking it —
  [Spring Framework, Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)

### Inferences / Design

```python
LOMBOK_GENERATORS = {
    "Getter":                 ("accessors", "a public getter for each field"),
    "Setter":                 ("accessors", "a public setter for each non-final field"),
    "Data":                   ("accessors+equals+ctor", "getters, setters, toString, equals, hashCode, and a required-args constructor"),
    "Value":                  ("immutable", "an immutable variant: private final fields, getters, toString, equals, hashCode, an all-args constructor"),
    "Builder":                ("builder", "a nested Builder class with a fluent API"),
    "RequiredArgsConstructor": ("ctor", "a constructor taking every final / @NonNull field"),
    "AllArgsConstructor":     ("ctor", "a constructor taking every field"),
    "NoArgsConstructor":      ("ctor", "a no-argument constructor"),
    "ToString":               ("tostring", "a toString()"),
    "EqualsAndHashCode":      ("equals", "equals() and hashCode()"),
    "Slf4j":                  ("logger", "a `private static final Logger log` field"),
}
CTOR_GENERATORS = {"Data", "Value", "RequiredArgsConstructor", "AllArgsConstructor"}

LOMBOK_NOTE = (
    "This type is annotated {anns} (Project Lombok), which generates members at "
    "compile time that do not exist in the source: {what}. The public surface of this "
    "class is therefore larger than its text, and the members listed under "
    "generatedMembers were inferred from the annotation, not read from the file. "
    "Verify against the compiled class or the Lombok documentation."
)
LOMBOK_CTOR_NOTE = (
    "No constructor is declared in the source, but {anns} generates one. The "
    "`private final` fields listed as injectionPoints ARE this bean's constructor "
    "injection points — Spring uses the single generated constructor without needing "
    "@Autowired. Dependency types here were read from field declarations, not from a "
    "constructor parameter list."
)
```

The extractor emits, on the type's record:

```python
{
  "lombok": {
    "annotations": ["Data", "RequiredArgsConstructor"],
    "generatedMembers": [
      {"kind": "getter", "name": "getOrderService", "assumed": True},
      {"kind": "constructor", "name": "OrderServiceImpl", "params": ["OrderRepository"], "assumed": True},
    ],
    "constructorGeneratedNotInSource": True,
    "note": "...",
  }
}
```

and sets `injectionPointSource = "final-fields-lombok"` (vs `"constructor-params"` /
`"field-@Autowired"` / `"setter-@Autowired"`), with `assumed=True` on every edge derived that way.
Confidence is pulled down by the normal mechanism — these are `assumed_claims` fed to
`confidence_from_flags()` — so no special-case confidence arithmetic is needed.

Note the inverse trap, which must **not** be implemented: do not infer "no constructor ⇒ Lombok".
A `@Service` with no constructor and no Lombok annotation simply has a default constructor and no
constructor-injected dependencies. Only the presence of a `CTOR_GENERATORS` annotation licenses the
final-fields-as-injection-points reading.

### Gaps
- Lombok's `@Data` interaction with explicitly-declared members (it skips generating a member that
  already exists), `@NonNull`'s effect on `@RequiredArgsConstructor`'s parameter list,
  `lombok.config` opt-outs, and `@Accessors(fluent=true)` renaming are all **uncited** and
  unmodelled. Hence `assumed=True` on every generated member rather than a confident list.

---

## 10. The DI graph, and what tree-sitter cannot do

### Takeaway
Build the bean index **from the implementation side** (`@Service`/`@Component`/… classes and the
interfaces they declare `implements`), then resolve `caller → injected interface → implementation` by
simple-name lookup. One implementation ⇒ a confident edge; zero or several ⇒ emit every candidate
with `assumed=True`. **Say repeatedly and in the output that tree-sitter is syntax-only**: it resolves
the *token* `OrderService`, never the *type* `com.acme.order.OrderService`, so every edge is
name-matched, not type-resolved, and anything requiring the classpath (a jar, a generic's element
type, an overload, a wildcard import) is unavailable by construction.

### Cited Findings
- Injection is **by type**: "Make sure that your target components … are consistently declared by the
  type that you use for your `@Autowired`-annotated injection points" —
  [Spring Framework, Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- Multi-constructor resolution is a **runtime search**: "The constructor with the greatest number of
  dependencies that can be satisfied by matching beans in the Spring container will be chosen" —
  *ibid.*
- Injection points include fields, setters and "methods with arbitrary names and multiple arguments" —
  *ibid.*
- One injection point can mean **N beans**: `MovieCatalog[]`, `Set<MovieCatalog>`,
  `Map<String, MovieCatalog>` receive all beans of the type, ordered by `Ordered`/`@Order`/`@Priority`,
  "otherwise, their order follows the registration order" — *ibid.*
- Injection can be **optional**: with `required = false`, "A non-required field will not get populated
  at all in such cases, leaving its default value in place" — *ibid.*
- A `@Bean` factory method's **return type is the graph edge**: "declare the most specific return
  type on your factory method (at least as specific as required by the injection points referring to
  your bean)" — *ibid.*
- Some dependencies are injected with no declaration anywhere: `BeanFactory`, `ApplicationContext`,
  `Environment`, `ResourceLoader`, `ApplicationEventPublisher`, `MessageSource` are "well-known
  resolvable dependencies" — *ibid.*
- Why parsing alone is insufficient, stated plainly: "Parsing gives you the syntax tree, but a name
  like `foo` or a call like `list.add(x)` only gets its meaning from the declarations that live
  elsewhere: JDK classes, project sources, and dependency jars." Without dependencies registered,
  "many lookups will throw `UnsolvedSymbolException`" —
  [JavaParser symbol-resolution docs](https://tessl.io/registry/tessl/maven-com-github-javaparser--javaparser-core/3.27.0/files/docs/symbol-resolution.md)
- The JVM-sidecar shape, if Tier 2 is ever built:
  `ParserConfiguration.setSymbolResolver(JavaSymbolSolver(CombinedTypeSolver(ReflectionTypeSolver,
  JavaParserTypeSolver(src/main/java), JarTypeSolver(each dependency jar))))`, then `nameExpr.resolve()`
  / `methodCall.resolve()` / `expr.calculateResolvedType()` — *ibid.*
- The project's own conclusion: an import-based graph yields `OrderServiceImpl` with **zero inbound
  edges, i.e. presented as dead code** — "silent, plausible, and backwards"
  (`documentation/14-stack-support-validation.md`).

### Inferences / Design

```python
@dataclass
class BeanDecl:
    simple_name: str
    fqn: str | None                  # package_declaration + simple_name; None if no package
    file_path: str
    stereotype: str                  # "Service" | "Component" | ...
    implements: list[str]            # simple names from super_interfaces / extends_interfaces
    extends: str | None
    produced_by_bean_method: str | None   # "AppConfig.clock" for @Bean-produced beans


@dataclass
class InjectionPoint:
    owner: str                       # the bean's simple name
    type_name: str                   # the DECLARED type, e.g. "OrderService"
    member: str                      # parameter / field / setter name
    kind: str                        # "constructor-param"|"field-@Autowired"|"setter-@Autowired"|"final-field-lombok"|"@Bean-param"
    qualifier: str | None            # @Qualifier("fast")
    optional: bool                   # required=false / Optional<T> / @Nullable
    collection_of: str | None        # List<Handler> / Map<String,Handler> -> "Handler"
    line: int


@dataclass
class DiEdge:
    from_bean: str
    to_declared_type: str
    resolved_to: list[str]           # candidate implementation simple names
    resolution: str                  # "unique-impl"|"direct-class"|"ambiguous"|"unresolved"|"container-provided"|"collection"
    assumed: bool
    note: str


WELL_KNOWN_RESOLVABLE = {
    "BeanFactory", "ApplicationContext", "ApplicationEventPublisher", "Environment",
    "ResourceLoader", "ResourcePatternResolver", "MessageSource", "ConversionService",
    "ObjectProvider", "ObjectFactory",
}

SYNTAX_ONLY_NOTE = (
    "Resolved by matching the declared type's SIMPLE NAME against classes found in the "
    "scanned source. tree-sitter is a syntax parser with no type resolution: it cannot "
    "distinguish two classes with the same simple name in different packages, cannot see "
    "a type that lives in a dependency jar, and cannot resolve a generic's element type. "
    "A correct answer needs a JavaParser/JDT JVM sidecar with a CombinedTypeSolver over "
    "the source roots and the dependency jars."
)
```

Resolution order for one `InjectionPoint`:

1. `type_name in WELL_KNOWN_RESOLVABLE` → `resolution="container-provided"`, `assumed=False`,
   note "supplied by the Spring container itself; it is declared nowhere in this project."
2. `collection_of` is set → `resolution="collection"`, `resolved_to` = every bean implementing that
   element type, `assumed=True`, note quoting "the map values are all beans of the expected type"
   and that the order follows `@Order` or registration order.
3. `type_name` is itself a `BeanDecl` (a concrete `@Service` injected directly) →
   `resolution="direct-class"`, `assumed=False` + `SYNTAX_ONLY_NOTE`.
4. Exactly one `BeanDecl` whose `implements` contains `type_name` → `resolution="unique-impl"`,
   `assumed=True` + `SYNTAX_ONLY_NOTE` + "resolved to the only implementation found in this project;
   `@Primary`/`@Qualifier`/`@Profile`/`@ConditionalOnProperty` could select a different bean at
   runtime." The narration should then name **the implementation**, not the interface — that is the
   whole point of the index, and it is what stops `OrderServiceImpl` being reported as dead code.
5. Several → `resolution="ambiguous"`, all candidates emitted, `assumed=True`, note naming
   `qualifier` if present and saying `@Primary`/`@Qualifier` decide, which is not resolvable here.
6. None → `resolution="unresolved"`, `assumed=True`, note "no implementation of this type was found
   in the scanned source; it is probably provided by a dependency jar or a `@Bean` method, neither of
   which a syntax-only parser can see."

`@Bean` methods are indexed **by return type** and their **parameters are themselves injection
points** (`kind="@Bean-param"`), so a `@Configuration` is both producer and consumer.

**Where the DI graph goes in the record.** `dependencies` currently holds
`{"path", "usedFor"}` and is filled from internal imports. For Java, fill it from the **DI edges**,
not the imports, and keep the shape:

```python
{"path": "com.acme.order.OrderServiceImpl", "usedFor":
 "injected as OrderService (constructor parameter, resolved to the only implementation in this project)"}
```

plus an additive `diGraph: {"injectionPoints": [...], "edges": [...], "beanIndexSize": N,
"fidelity": "syntax"}`. `fidelity: "syntax"` is the single word that tells a downstream consumer
this graph was not type-resolved; the JavaParser sidecar would emit `"resolved"`.

**Framework-invoked methods — the other half of the dead-code error.** Any method whose
`isFrameworkEntryPoint` is True gets `calledBy = []` *and*:

```python
CONTAINER_INVOKED_NOTE = {
  "Scheduled":      "Invoked by the Spring container on a schedule, not called from project code.",
  "EventListener":  "Invoked by the Spring container when the matching application event is published, not called from project code.",
  "ExceptionHandler": "Invoked by the Spring container's exception resolver when the declared exception escapes a handler method, not called from project code.",
  "Aspect":         "Advice woven in by Spring AOP around matching join points, not called from project code.",
  "PostConstruct":  "Invoked by the container once after dependency injection completes.",
  "PreDestroy":     "Invoked by the container during shutdown.",
  "Bean":           "Invoked once by the container to produce a bean, not called from project code.",
  # handler methods
  "_mapping":       "Invoked by Spring's DispatcherServlet when a request matches its mapping, not called from project code.",
}
```

`invokedBy: "spring-container"` goes on the entry, and the narration must say "invoked by the Spring
container", never "unused". This is an explicit output field so the narrator cannot get it wrong by
omission — it is the same class of error as the `OrderServiceImpl` inversion.

**Stated plainly, what tree-sitter alone cannot resolve, all of which must be `assumed=True`:**
an injected interface → its implementation (name match only); two same-simple-name types in different
packages; any type from a dependency jar; a generic's element type (`List<OrderDto>` → `OrderDto` is
read syntactically from `type_arguments` but not *verified* to be a project type); which constructor
Spring picks when several exist; `@Primary`/`@Qualifier`/`@Profile`/`@ConditionalOnProperty`
selection; `@Bean`-produced beans whose return type is an external type; whether an `@Override`'s
supertype documentation exists; whether a derived-query property name matches a real entity field;
and whether a `SecurityFilterChain` protects a given URL.

### Gaps
- `@Qualifier`/`@Primary`/`@Fallback` precedence: still uncited (same gap as §4).
- No Python-usable off-the-shelf Spring bean-graph extractor was found in the prior round, and I did
  not search again; the heuristic index above is the design because nothing better is available
  without a JVM.

---

## 11. Chunking: the annotated type, grouped into feature slices

### Takeaway
The chunk unit is the **annotated type**, the narrative unit is the **feature slice**, and
`src/test/java` is excluded by default. This forces framework detection **before** chunking — which
the existing code already half-does (`src/chunk/chunker.py:60-62` calls
`group_spring_boot_features()` off `project_type.marker_hits["spring_boot"]`,
and `src/detect/project_type.py:111-122` already distinguishes `spring_boot` from plain `java` by
looking for `spring-boot`/`org.springframework.boot` in `pom.xml`/`build.gradle`).

### Cited Findings
- Spring's own recommended layout is **feature-sliced**: `com/example/myapplication/MyApplication.java`,
  then `customer/{Customer, CustomerController, CustomerService, CustomerRepository}.java` and
  `order/{...}` — [Spring Boot, Structuring Your Code](https://docs.spring.io/spring-boot/3.5.0/reference/using/structuring-your-code.html)
- "We generally recommend that you locate your main application class in a root package above other
  classes… Using a root package also allows component scan to apply only on your project" — *ibid.*
- Scan roots are configurable and may not match the directory tree:
  `@ComponentScan(basePackages = "org.example")` with Ant-style patterns like `"org.example.**"` —
  [Spring Framework, Classpath Scanning](https://docs.spring.io/spring-framework/reference/7.1/core/beans/classpath-scanning.html)
- A single `.java` file may declare **multiple top-level types** (one `public`, others
  package-private), so "the class in this file" is ambiguous — prior round's catalogue item 14.
- Measured: a file with five top-level declarations (class, interface, class, record, enum) yields
  five sibling declaration nodes under `program`, each with its own exact line range — so per-type
  chunking is a direct read, not an inference.

### Inferences / Design
- **Discovery.** Walk `src/main/java/**/*.java` (and `src/main/kotlin` if ever supported — out of
  scope: the grammar is Java). Exclude `src/test/java` and `src/it/java` by default behind a config
  flag; a test file is identifiable both by source root and by `@SpringBootTest`/`@WebMvcTest`/
  `@DataJpaTest`/`@Test`/`@MockBean`. Also exclude `target/`, `build/`, `generated-sources/`.
- **One chunk per top-level type**, with its nested types folded in (nested types are part of the
  enclosing type's story, not separate chunks; they carry `nestingDepth > 0`). A `chunk_id` of
  `<SimpleName>/<file_path>` matches the existing convention
  (`"Header/src/components/Header.tsx"`). A file with N top-level types produces N chunks sharing one
  `filePath` — which means `reuse_pipeline`'s `contentHash` keying by `chunk.file_path` and
  `write_stored(output_root, record["filePath"], record)` would **collide**. Minimal fix: key stored
  records by `chunkId` rather than `filePath`, or (smaller) emit one chunk per file whose
  `importantFunctions` spans all its types and whose `notes` says how many types it declares. The
  first is correct; the second is a one-line change. **Flag this as a required decision, not a silent
  assumption.**
- **Slice detection.** Group by the package directory immediately under the root package. Then
  classify: if those directory names are drawn from the layer vocabulary
  (`controller|controllers|service|services|repository|repositories|model|models|entity|entities|dto|dtos|config|web|api|mapper|exception`)
  the project is layer-sliced; otherwise feature-sliced. A layer-sliced project needs a second pass
  that groups by the type's **name stem** (`Order` from `OrderController`, `OrderService`,
  `OrderServiceImpl`, `OrderRepository`, `Order`, `OrderDto`) to recover feature slices — which is
  the same pairing idea `src/chunk/feature_grouping.py:198` already implements for Go.
- **The annotation beats the directory.** A `@Service` in `util/` is a service. Report the
  annotation-derived role as authoritative and the path-derived role as corroboration, and when they
  disagree emit `pathRoleConflict: {"pathSuggests": "util", "annotationSays": "service"}` rather than
  picking silently.
- **Fixed-position chunks regardless of size**: the `@SpringBootApplication` class is chunk #1 (it is
  short and load-bearing), and `src/main/resources/application*.yml|properties` gets its own short
  chunk (it holds `server.servlet.context-path`, datasource config and profiles — i.e. facts the
  route table depends on). Flyway `db/migration/*.sql` is optional and separate.
- **Oversized types**: a `@RestController` with >8 handler methods splits by path prefix; a
  `@Configuration` with many `@Bean`s splits by return-type family; an `@Entity` is **never** split —
  its relationship set is the point.
- **Ordering for narration**: entry point → configuration → route table (all endpoints, one frame) →
  then per feature slice: controller → DTOs → service (+ resolved impl) → repository → entity.

### Gaps
- `@ComponentScan(basePackages = ...)` can place beans outside the root package; the design reads the
  directory tree and does not evaluate scan patterns. Worth a note on the chunk when a
  `@ComponentScan` with an explicit `basePackages` is seen.
- The Maven Standard Directory Layout page itself was not cited in either round; `src/main/java` /
  `src/test/java` is asserted from general knowledge with the Spring Boot page confirming only the
  package layout under it.

---

## 12. Test plan

### Takeaway
Mirror `tests/test_go_extractor.py`'s style exactly: `from src.extract import java_extractor as java`,
one plain `def test_*` per behaviour, inline triple-quoted source as the fixture, bare `assert`, no
classes, no fixtures module, no mocks. Add a grammar-contract test so a grammar bump fails loudly.

### Inferences / Design — `tests/test_java_extractor.py`

Inline-source tests (fast, no files on disk; the existing Go/TS tests all do this):

```python
from src.extract import java_extractor as java


def test_grammar_contract_node_and_field_names_still_exist():
    """Pins this module's dependency on tree-sitter-java 0.23.5's node names.
    A grammar bump that renames a node must fail HERE, not silently return
    empty lists from every extractor function."""
    root, src = java.parse(
        "class C extends B implements I { void m(); }\n"
        "interface I extends J { }\n"
        "record R(int a) { }\n"
        "enum E { A; }\n"
    )
    assert root.has_error is False
    cls = root.named_children[0]
    assert cls.type == "class_declaration"
    assert [cls.child_by_field_name(f) is not None
            for f in ("name", "superclass", "interfaces", "body")] == [True] * 4
    iface = root.named_children[1]
    assert iface.type == "interface_declaration"
    # extends_interfaces is an UNNAMED child on interface_declaration
    assert iface.child_by_field_name("interfaces") is None
    assert any(c.type == "extends_interfaces" for c in iface.children)
    rec = root.named_children[2]
    assert rec.child_by_field_name("parameters").type == "formal_parameters"


def test_bodyless_interface_method_does_not_steal_the_next_methods_body():
    """The brace-matcher bug: an abstract/interface method has no body, so a
    matcher walking to the next `{` attached the FOLLOWING method's body and
    shifted every range by one method."""
    text = """
interface OrderRepository extends JpaRepository<Order, Long> {
    List<Order> findByCustomerId(Long id);
    default List<Order> findActive() {
        return findByStatus(Status.ACTIVE);
    }
}
"""
    methods = {m.name: m for m in java.extract_methods(text)}
    assert methods["findByCustomerId"].has_body is False
    assert methods["findByCustomerId"].line_range == (3, 3)
    assert methods["findActive"].has_body is True
    assert methods["findActive"].line_range == (4, 6)


def test_text_block_containing_braces_does_not_truncate_the_method():
    text = '''
class Dao {
    String sql() {
        return """
            select * from orders where payload = {"k": 1}
            """;
    }
    void after() { }
}
'''
    methods = {m.name: m for m in java.extract_methods(text)}
    assert methods["sql"].line_range == (3, 7)
    assert methods["after"].line_range == (8, 8)


def test_route_concatenates_class_and_method_paths():
    text = """
@RestController
@RequestMapping("/persons")
class PersonController {
    @GetMapping("/{id}")
    public Person find(@PathVariable Long id) { return null; }
    @PostMapping
    public void add(@RequestBody Person p) { }
}
"""
    routes = {(r.method, r.path) for r in java.extract_routes(text)}
    assert ("GET", "/persons/{id}") in routes
    assert ("POST", "/persons") in routes        # not "/persons/"


def test_regex_path_variable_splits_on_first_colon():
    text = """
@RestController
class C {
    @GetMapping("/items/{code:[a-z]+}")
    void get(@PathVariable String code) { }
}
"""
    route = java.extract_routes(text)[0]
    assert route.path == "/items/{code:[a-z]+}"
    assert route.path_variables == [
        {"name": "code", "pattern": "[a-z]+", "capturesTrailing": False}]


def test_array_valued_class_path_multiplies_routes():
    text = """
@RestController
@RequestMapping({"/api/orders", "/api/v1/orders"})
class C {
    @GetMapping("/{id}")
    void find() { }
}
"""
    paths = sorted(r.path for r in java.extract_routes(text))
    assert paths == ["/api/orders/{id}", "/api/v1/orders/{id}"]


def test_property_placeholder_path_is_reported_unresolved_not_verbatim():
    text = """
@RestController
@RequestMapping("${api.base}/orders")
class C { @GetMapping void all() { } }
"""
    route = java.extract_routes(text)[0]
    assert route.assumed is True
    assert "${...}" in route.note and "placeholder" in route.note


def test_method_level_produces_overrides_class_level():
    text = """
@RestController
@RequestMapping(value = "/a", produces = "application/xml")
class C {
    @GetMapping(value = "/b", produces = "application/json")
    void g() { }
}
"""
    route = java.extract_routes(text)[0]
    assert route.produces == ["application/json"]      # overrides, does NOT extend


def test_context_path_is_prefixed_and_labelled():
    route = java.extract_routes(
        '@RestController @RequestMapping("/orders") class C { @GetMapping void a() { } }',
        context_path="/api",
    )[0]
    assert route.path == "/api/orders"
    assert route.context_path_applied == "/api"
    assert route.assumed is True


def test_rest_controller_role_is_not_matched_by_substring():
    """@RestController is META-annotated @Controller; it contains no literal
    '@Controller' text. The built-in table must still classify it."""
    role = java.extract_types("@RestController class C { }")[0].spring_role
    assert role.role == "rest_controller"
    assert role.via == "builtin"
    assert role.assumed is False


def test_unknown_composed_annotation_degrades_to_unknown_with_a_note():
    role = java.extract_types("@AcmeHandler class C { }")[0].spring_role
    assert role.role == "unknown"
    assert role.assumed is True
    assert "meta-annotated" in role.note


def test_project_local_composed_annotation_resolves_via_the_index():
    index = java.build_composed_annotation_index({
        "A.java": "@Service public @interface AcmeHandler { }"})
    role = java.extract_types("@AcmeHandler class C { }", composed_index=index)[0].spring_role
    assert role.role == "service"
    assert role.via == "composed:AcmeHandler"
    assert role.assumed is True


def test_visibility_absent_modifier_is_package_private_in_a_class():
    v = java.extract_methods("class C { void m() { } }")[0]
    assert (v.visibility, v.exported) == ("package-private", False)


def test_visibility_absent_modifier_is_public_on_an_interface_member():
    v = java.extract_methods("interface I { void m(); }")[0]
    assert (v.visibility, v.visibility_source, v.exported) == (
        "public", "implicit-interface_body", True)


def test_javadoc_is_read_and_the_license_header_is_not():
    text = '''
/*
 * Copyright 2024 Acme Corp. All Rights Reserved.
 */
package com.acme;

/**
 * Serves order lookups for the storefront.
 * <p>Returns {@code OrderDto} payloads.</p>
 * @param <E> element type
 */
@RestController
@RequestMapping("/orders")
public class OrderController { }
'''
    t = java.extract_types(text)[0]
    assert t.description.startswith("Serves order lookups")
    assert "Copyright" not in t.description
    assert "<p>" not in t.description and "{@code" not in t.description
    assert "OrderDto payloads" in t.description          # inline tag unwrapped, HTML stripped
    assert t.doc_tags["param:<E>"] == "element type"


def test_javadoc_found_across_intervening_annotations():
    """Annotations sit BETWEEN the doc comment and the `class`/`public`
    keyword, so a 'comment on the line immediately above' rule fails on every
    Spring controller."""
    text = '/**\n * Does a thing well.\n */\n@Service\n@Transactional\nclass S { }'
    assert java.extract_types(text)[0].description == "Does a thing well."


def test_derived_query_is_parsed_into_a_sentence():
    q = java.extract_repository_queries(
        "interface R extends JpaRepository<O, Long> {"
        " List<O> findByCustomerIdAndStatusOrderByCreatedAtDesc(Long c, S s); }")[0]
    assert q.source == "method-name"
    assert q.conditions == ["customer id equals", "status equals"]
    assert q.combinator == "And"
    assert q.order_by == ["created at descending"]
    assert "ordered by created at" in q.sentence


def test_query_annotation_wins_over_the_method_name():
    q = java.extract_repository_queries(
        'interface R { @Query("select o from O o where o.total > ?1")'
        ' List<O> findByTotalGreaterThan(BigDecimal t); }')[0]
    assert q.source == "@Query"
    assert q.query_text == "select o from O o where o.total > ?1"
    assert q.conditions == []              # the NAME is not the query here


def test_lombok_required_args_constructor_makes_final_fields_the_injection_points():
    text = """
@Service
@RequiredArgsConstructor
class OrderServiceImpl implements OrderService {
    private final OrderRepository repo;
    private final Clock clock;
}
"""
    t = java.extract_types(text)[0]
    assert t.lombok.constructor_generated_not_in_source is True
    assert [p.type_name for p in t.injection_points] == ["OrderRepository", "Clock"]
    assert all(p.kind == "final-field-lombok" for p in t.injection_points)
    assert "ARE this bean's constructor injection points" in t.lombok.note


def test_di_edge_resolves_interface_to_its_single_implementation():
    index = java.build_bean_index({
        "Svc.java": "interface OrderService { }",
        "Impl.java": "@Service class OrderServiceImpl implements OrderService { }",
    })
    edges = java.resolve_injection(
        java.extract_types(
            "@RestController class OrderController {"
            " OrderController(OrderService s) { } }")[0], index)
    assert edges[0].resolved_to == ["OrderServiceImpl"]
    assert edges[0].resolution == "unique-impl"
    assert edges[0].assumed is True
    assert "simple name" in edges[0].note.lower()


def test_di_edge_with_two_implementations_is_ambiguous_not_a_guess():
    index = java.build_bean_index({
        "A.java": "@Service class FastOrderService implements OrderService { }",
        "B.java": "@Service class SlowOrderService implements OrderService { }",
    })
    edge = java.resolve_injection(
        java.extract_types("@RestController class C { C(OrderService s) { } }")[0], index)[0]
    assert edge.resolution == "ambiguous"
    assert sorted(edge.resolved_to) == ["FastOrderService", "SlowOrderService"]
    assert edge.assumed is True


def test_scheduled_method_is_labelled_container_invoked_not_unused():
    m = java.extract_methods(
        'class S { @Scheduled(cron = "0 0 * * * *") public void sweep() { } }')[0]
    assert m.is_framework_entry_point is True
    assert m.invoked_by == "spring-container"
    assert "not called from project code" in m.invocation_note


def test_overloads_are_keyed_separately():
    ms = java.extract_methods(
        "class C { void save(Order o) { } void save(Order o, boolean f) { } }")
    assert {m.overload_key for m in ms} == {"save(Order)", "save(Order,boolean)"}
    assert len(ms) == 2


def test_record_components_are_data_model_fields_with_generated_accessors():
    m = java.extract_data_models("record OrderDto(Long id, String ref) { }")[0]
    assert [(f.name, f.type) for f in m.fields] == [("id", "Long"), ("ref", "String")]
    assert m.generated_accessors == ["id()", "ref()"]


def test_generic_return_type_and_params_are_not_split_on_commas():
    m = java.extract_methods(
        "class C { public ResponseEntity<Map<String, List<OrderDto>>> f(Map<String, Integer> m)"
        " { return null; } }")[0]
    assert m.return_type == "ResponseEntity<Map<String, List<OrderDto>>>"
    assert [(p.type_name, p.name) for p in m.params] == [("Map<String, Integer>", "m")]


def test_secret_in_a_java_snippet_is_redacted_through_trim_snippet():
    text = ('@Configuration class C {'
            ' private static final String KEY = "sk_live_0123456789abcdefghij"; }')
    t = java.extract_types(text)[0]
    assert t.snippet.secrets_redacted is True
    assert "sk_live_0123456789abcdefghij" not in t.snippet.text


def test_anonymous_class_method_is_not_reported_as_a_top_level_method():
    text = """
class C {
    void run() {
        Comparator<Order> c = new Comparator<>() {
            public int compare(Order a, Order b) { return 0; }
        };
    }
}
"""
    ms = java.extract_methods(text)
    assert [m.name for m in ms if m.nesting_depth == 0] == ["run"]
    inner = next(m for m in ms if m.name == "compare")
    assert inner.nesting_depth > 0
```

Fixture repo for integration, in the shape `tests/test_extractor_integration.py` already uses
(`tmp_path`-built mini repo + `extract_repo`), under
`tests/fixtures/spring_boot_mini/`:

```
pom.xml                                     (contains org.springframework.boot)
src/main/resources/application.yml          (server.servlet.context-path: /api)
src/main/java/com/acme/DemoApplication.java (@SpringBootApplication)
src/main/java/com/acme/order/Order.java     (@Entity, @OneToMany, enum Status with a body)
src/main/java/com/acme/order/OrderDto.java  (record, 3 components)
src/main/java/com/acme/order/OrderRepository.java  (3 derived queries + 1 @Query + 1 default)
src/main/java/com/acme/order/OrderService.java     (interface, no annotations)
src/main/java/com/acme/order/OrderServiceImpl.java (@Service + @RequiredArgsConstructor, no ctor)
src/main/java/com/acme/order/OrderController.java  (@RestController + array @RequestMapping,
                                                    4 handlers incl. {id:[0-9]+}, a text block,
                                                    a license header AND a Javadoc)
src/main/java/com/acme/config/AppConfig.java       (@Configuration + 2 @Bean methods)
src/main/java/com/acme/sched/Sweeper.java          (@Scheduled + @EventListener)
src/test/java/com/acme/order/OrderControllerTest.java  (@WebMvcTest — must be EXCLUDED)
```

Integration assertions: the record set contains no `"not yet implemented"` note; `language == "Java"`;
`schema_check` reports all records valid (`tests/test_schema_check.py` currently locks the *failure*
at lines 81-96 and must be updated); `OrderControllerTest` produces no chunk; the route table
contains exactly the expected 8 paths (4 handlers × 2 class paths) all prefixed `/api`;
`OrderServiceImpl` has at least one inbound DI edge (**this is the regression test for the dead-code
inversion**); `Sweeper.sweep` has `calledBy == []` *and* `invokedBy == "spring-container"`;
`fileDescription` for `OrderController` is its Javadoc, not its license.

---

## 13. Acceptance criteria

### Takeaway
Acceptance is "every one of the previously catalogued silent failures now either produces the right
answer or says `assumed=True` with a note naming what to verify" — not "an mp4 was produced".

### Inferences / Design

**Correctness (hard, must pass).**
1. No `.java` chunk reaches the `"Extraction for stack '<stack>' is not yet implemented in Phase 3."`
   branch in `extractor.py` or `reuse_pipeline.py`; `tests/test_schema_check.py` is updated so Java
   records validate instead of locking in the failure.
2. `schema_check` reports **100% valid** for every Java record on the fixture repo and on one real
   Spring Boot repository.
3. Every method's `lineRange` is exact — verified by asserting the snippet's first line contains the
   method name and the last line is `}` or `;`. In particular **no body-less declaration borrows the
   following method's body** (the shifted-by-one-method bug).
4. Every route's `path` is the **full** path: context-path + class + method, with array paths
   multiplied and `{name:regex}` preserved intact with the variable name split on the first colon.
   Zero routes whose path begins with `/{` or is bare `/` unless the source really says so.
5. No `${…}` or `#{…}` is ever emitted as a literal URL without `assumed=True` and a note.
6. `@RestController` and friends are classified correctly despite meta-annotation; an unrecognised
   annotation yields `role="unknown"`, `assumed=True`, never a plausible-looking layer.
7. `visibility` matches the §7 decision table on every row, including the implicit-`public` interface
   member and the `private` nested type's `public` method.
8. `fileDescription` is **never** a license notice on any file in the fixture repo or in a real repo
   scan. This is a grep-able acceptance test: no record's `fileDescription` contains
   `copyright|license|rights reserved` case-insensitively.
9. Repository interfaces produce one narration-ready sentence per derived query; `@Query`-annotated
   methods report the annotation value as the query and **do not** parse the method name.
10. No `@Service`/`@Component` class that is injected anywhere in the project has zero inbound DI
    edges. (The `OrderServiceImpl`-as-dead-code regression.)
11. Every `@Scheduled`/`@EventListener`/`@ExceptionHandler`/`@Bean`/`@Aspect`/handler method carries
    `invokedBy: "spring-container"`; none is reportable as unused.
12. `src/test/java` contributes zero chunks by default.
13. `root.has_error == True` on any file adds a note and caps that record's confidence at 0.5; it
    never raises and never silently yields empty lists.

**Honesty (hard).**
14. Every `assumed=True` field carries a non-empty note naming what to verify — assertable
    mechanically: `all(r["note"] for r in everything if r["assumed"])`.
15. Every record's `diGraph.fidelity == "syntax"` and every name-matched DI edge's note states that
    tree-sitter performs no type resolution and names the JavaParser sidecar as the fix.
16. A file whose extraction yields nothing scores **0.3**, not 0.95 — i.e. the Java path must go
    through `confidence_from_flags()` and must not special-case empties. This is the Angular-silence
    failure mode and it must not be reproduced for Java.
17. Lombok-annotated types list `generatedMembers` with `assumed=True` and a note; nothing generated
    is presented as read from the source.
18. Every snippet comes from `trim_snippet()` — assertable by checking that a fixture with a
    `sk_live_…`-shaped literal has `secretsRedacted: True` and that a >120-line method has a
    `continuationNote`.

**Mechanical.**
19. `pip install -r requirements.txt` installs `tree_sitter==0.25.2` and `tree_sitter_java==0.23.5`;
    `test_grammar_contract_node_and_field_names_still_exist` passes.
20. `src/extract/java_extractor.py` imports tree-sitter **lazily** (inside `_language()`/`_parser()`),
    so a repo with no Java files never pays the import and the other stacks' tests do not gain a hard
    dependency.
21. No regression in the TS or Go suites: the only shared-file edits are the additive `java` branch in
    `function_context.is_exported()` and the optional `exported_override` parameter on
    `build_function_context()`.

### Gaps
- Per-file yield on a large real Spring repository is unmeasured (the prior round's audit used
  minimal synthetic repos and never executed the Remotion render or TTS). Criterion 2's "one real
  Spring Boot repository" needs one to be chosen; none is present under
  `/home/claude/codeExplanation-v2`.
- Whether the multi-top-level-type chunking decision (§11) should change the storage key from
  `filePath` to `chunkId` is a **design decision left open** — it touches
  `storage/mirror_store.py` and `reuse_pipeline.py`, not just the extractor, and should be settled
  before implementation rather than discovered during it.
