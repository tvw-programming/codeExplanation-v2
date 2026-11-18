from pathlib import Path

from src.chunk.feature_grouping import Feature
from src.chunk.chunk_splitter import plan_chunks_for_feature, classify_size, make_chunk_id


def _write_lines(path: Path, n: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"line {i}" for i in range(n)) + "\n")


def test_classify_size_boundaries():
    assert classify_size(200) == "small"
    assert classify_size(201) == "medium"
    assert classify_size(800) == "medium"
    assert classify_size(801) == "large"


def test_small_feature_is_one_chunk(tmp_path):
    _write_lines(tmp_path / "a.tsx", 50)
    _write_lines(tmp_path / "b.ts", 50)
    feature = Feature(name="alumni", stack="react", files=["a.tsx", "b.ts"], primary_file="a.tsx")
    chunks = plan_chunks_for_feature(feature, tmp_path)
    assert len(chunks) == 1
    assert chunks[0].size_class == "small"
    assert chunks[0].file_path == "a.tsx"
    assert chunks[0].related_files == ["b.ts"]
    assert chunks[0].needs_further_split is False


def test_medium_feature_splits_one_chunk_per_file(tmp_path):
    _write_lines(tmp_path / "a.go", 186)
    _write_lines(tmp_path / "b.go", 248)
    feature = Feature(name="alumni", stack="go", files=["a.go", "b.go"], primary_file="a.go")
    chunks = plan_chunks_for_feature(feature, tmp_path)
    assert len(chunks) == 2
    paths = {c.file_path for c in chunks}
    assert paths == {"a.go", "b.go"}
    b_chunk = next(c for c in chunks if c.file_path == "b.go")
    assert b_chunk.size_class == "medium"
    assert b_chunk.needs_further_split is True  # 248 > 200


def test_large_feature_flags_oversized_files_for_further_split(tmp_path):
    _write_lines(tmp_path / "AdminGrid.tsx", 284)
    _write_lines(tmp_path / "FormDialog.tsx", 221)
    _write_lines(tmp_path / "ImportDialog.tsx", 190)
    _write_lines(tmp_path / "workbook.ts", 187)
    _write_lines(tmp_path / "profileRules.ts", 144)
    feature = Feature(
        name="admin", stack="react",
        files=["AdminGrid.tsx", "FormDialog.tsx", "ImportDialog.tsx", "workbook.ts", "profileRules.ts"],
        primary_file="AdminGrid.tsx",
    )
    chunks = plan_chunks_for_feature(feature, tmp_path)
    assert len(chunks) == 5
    import_dialog = next(c for c in chunks if c.file_path == "ImportDialog.tsx")
    assert import_dialog.size_class == "small"
    assert import_dialog.needs_further_split is False
    admin_grid = next(c for c in chunks if c.file_path == "AdminGrid.tsx")
    assert admin_grid.needs_further_split is True  # 284 > 200


def test_chunk_id_is_stable_and_readable():
    cid1 = make_chunk_id("Auth Login", "src/auth/login.tsx")
    cid2 = make_chunk_id("Auth Login", "src/auth/login.tsx")
    assert cid1 == cid2
    assert cid1.startswith("auth-login-")


def test_chunk_id_differs_for_different_files():
    cid_a = make_chunk_id("alumni", "api/internal/handler/alumni_handler.go")
    cid_b = make_chunk_id("alumni", "api/internal/repository/alumni_repository.go")
    assert cid_a != cid_b
