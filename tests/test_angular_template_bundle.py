"""Angular templateUrl class+html bundle chunking (EXTRACTOR_VERSION 21).

Relative ``../`` / nested paths join when uniquely resolved under the repo;
absolute / ``node_modules`` / orphan HTML stay out of scope.
"""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import plan_chunks_for_feature
from src.chunk.feature_grouping import Feature, group_react_or_angular_features
from src.extract.angular.extract import (
    pair_angular_template_bundles,
    resolve_template_url_sibling,
)
from src.storage.mirror_store import EXTRACTOR_VERSION


def test_extractor_version_22():
    assert EXTRACTOR_VERSION == 24


def test_resolve_template_url_sibling_relative_paths(tmp_path: Path):
    (tmp_path / "host.component.ts").write_text(
        "@Component({ templateUrl: './host.component.html' })\nexport class Host {}\n",
        encoding="utf-8",
    )
    (tmp_path / "host.component.html").write_text("<p>hi</p>\n", encoding="utf-8")
    (tmp_path / "other.html").write_text("<p>x</p>\n", encoding="utf-8")
    assert (
        resolve_template_url_sibling(tmp_path, "host.component.ts", "./host.component.html")
        == "host.component.html"
    )
    assert resolve_template_url_sibling(tmp_path, "host.component.ts", "/abs.html") is None
    assert resolve_template_url_sibling(tmp_path, "host.component.ts", "missing.html") is None


def test_resolve_template_url_parent_and_nested(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "host").mkdir()
    (tmp_path / "src" / "shared").mkdir()
    (tmp_path / "src" / "shared" / "tpls").mkdir()
    (tmp_path / "src" / "host" / "host.component.ts").write_text(
        "@Component({ templateUrl: '../shared/tpls/host.html' })\nexport class Host {}\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "shared" / "tpls" / "host.html").write_text("<p>hi</p>\n", encoding="utf-8")
    assert (
        resolve_template_url_sibling(
            tmp_path, "src/host/host.component.ts", "../shared/tpls/host.html"
        )
        == "src/shared/tpls/host.html"
    )
    # Escape outside repo → None
    assert (
        resolve_template_url_sibling(
            tmp_path, "src/host/host.component.ts", "../../../../etc/passwd.html"
        )
        is None
    )


def test_resolve_template_url_rejects_node_modules(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg").mkdir()
    (tmp_path / "src" / "host.component.ts").write_text("x\n", encoding="utf-8")
    (tmp_path / "node_modules" / "pkg" / "x.html").write_text("<p>x</p>\n", encoding="utf-8")
    assert (
        resolve_template_url_sibling(
            tmp_path, "src/host.component.ts", "../node_modules/pkg/x.html"
        )
        is None
    )


def test_feature_grouping_attaches_clear_template_sibling(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "host.component.ts").write_text(
        "@Component({ selector: 'app-host', templateUrl: './host.component.html' })\n"
        "export class Host {}\n",
        encoding="utf-8",
    )
    (src / "host.component.html").write_text("<app-tile></app-tile>\n", encoding="utf-8")
    (src / "orphan.html").write_text("<p>orphan</p>\n", encoding="utf-8")
    features = group_react_or_angular_features(tmp_path, src, stack="angular")
    assert len(features) == 1
    files = set(features[0].files)
    assert "src/host.component.ts" in files
    assert "src/host.component.html" in files
    # Orphan html never claimed without templateUrl evidence.
    assert "src/orphan.html" not in files


def test_feature_grouping_attaches_parent_relative_template(tmp_path: Path):
    src = tmp_path / "src"
    (src / "feature").mkdir(parents=True)
    (src / "shared").mkdir()
    (src / "feature" / "host.component.ts").write_text(
        "@Component({ selector: 'app-host', templateUrl: '../shared/host.html' })\n"
        "export class Host {}\n",
        encoding="utf-8",
    )
    (src / "shared" / "host.html").write_text("<p>shared</p>\n", encoding="utf-8")
    (src / "shared" / "orphan.html").write_text("<p>orphan</p>\n", encoding="utf-8")
    features = group_react_or_angular_features(tmp_path, src / "feature", stack="angular")
    assert len(features) == 1
    files = set(features[0].files)
    assert "src/feature/host.component.ts" in files
    assert "src/shared/host.html" in files
    assert "src/shared/orphan.html" not in files


def test_medium_feature_keeps_class_html_one_chunk(tmp_path: Path):
    # Force medium by exceeding 200 combined lines across the feature.
    ts_lines = "\n".join(f"// pad {i}" for i in range(120))
    html_lines = "\n".join(f"<!-- pad {i} -->" for i in range(100))
    other_lines = "\n".join(f"export const x{i} = {i};" for i in range(50))
    (tmp_path / "host.component.ts").write_text(
        "@Component({ selector: 'app-host', templateUrl: './host.component.html' })\n"
        "export class Host {}\n" + ts_lines + "\n",
        encoding="utf-8",
    )
    (tmp_path / "host.component.html").write_text("<p>hi</p>\n" + html_lines + "\n", encoding="utf-8")
    (tmp_path / "other.ts").write_text(other_lines + "\n", encoding="utf-8")
    feature = Feature(
        name="host",
        stack="angular",
        files=["host.component.ts", "host.component.html", "other.ts"],
        primary_file="host.component.ts",
    )
    bundles = pair_angular_template_bundles(tmp_path, feature.files)
    assert ("host.component.ts", ["host.component.ts", "host.component.html"]) in bundles
    chunks = plan_chunks_for_feature(feature, tmp_path)
    host = next(c for c in chunks if c.file_path == "host.component.ts")
    assert "host.component.html" in host.related_files
    # No separate chunk whose primary is the template sibling.
    assert not any(c.file_path == "host.component.html" for c in chunks)
    assert any(c.file_path == "other.ts" for c in chunks)
