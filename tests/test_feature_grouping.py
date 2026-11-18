from pathlib import Path

from src.chunk.feature_grouping import (
    group_react_or_angular_features,
    group_go_features,
    group_python_agent_features,
    group_spring_boot_features,
)


def _write(path: Path, content: str = "x = 1\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_react_groups_by_features_folder(tmp_path):
    src = tmp_path / "src"
    _write(src / "features" / "admin" / "AdminGrid.tsx")
    _write(src / "features" / "admin" / "helpers.ts")
    _write(src / "features" / "alumni" / "ProfilePage.tsx")
    features = group_react_or_angular_features(tmp_path, src)
    names = {f.name for f in features}
    assert "admin" in names
    assert "alumni" in names
    admin = next(f for f in features if f.name == "admin")
    assert len(admin.files) == 2


def test_react_groups_other_subdirs_as_their_own_feature(tmp_path):
    src = tmp_path / "src"
    _write(src / "features" / "admin" / "AdminGrid.tsx")
    _write(src / "api" / "client.ts")
    _write(src / "lib" / "firebase.ts")
    features = group_react_or_angular_features(tmp_path, src)
    names = {f.name for f in features}
    assert "api" in names
    assert "lib" in names


def test_react_groups_loose_root_files(tmp_path):
    src = tmp_path / "src"
    _write(src / "App.tsx")
    _write(src / "main.tsx")
    features = group_react_or_angular_features(tmp_path, src)
    loose = [f for f in features if set(f.files) == {"src/App.tsx", "src/main.tsx"}]
    assert len(loose) == 1
    assert loose[0].name == "src"


def test_go_pairs_handler_and_repository_by_resource_name(tmp_path):
    backend = tmp_path / "api" / "internal"
    _write(backend / "handler" / "alumni_handler.go")
    _write(backend / "repository" / "alumni_repository.go")
    _write(backend / "handler" / "media_handler.go")
    _write(backend / "repository" / "media_repository.go")
    features = group_go_features(tmp_path, tmp_path / "api")
    paired = {f.name: f for f in features if f.name in ("alumni", "media")}
    assert set(paired) == {"alumni", "media"}
    assert len(paired["alumni"].files) == 2
    assert len(paired["media"].files) == 2


def test_go_non_resource_dirs_become_own_feature(tmp_path):
    backend = tmp_path / "api" / "internal"
    _write(backend / "firebaseauth" / "middleware.go")
    _write(backend / "migrate" / "migrate.go")
    features = group_go_features(tmp_path, tmp_path / "api")
    names = {f.name for f in features}
    assert "firebaseauth" in names
    assert "migrate" in names


def test_python_groups_agent_files_by_shared_name(tmp_path):
    backend = tmp_path / "agents"
    _write(backend / "payments_main.py")
    _write(backend / "payments_router.py")
    _write(backend / "payments_config.py")
    _write(backend / "test_payments_main.py")
    features = group_python_agent_features(tmp_path, backend)
    payments = [f for f in features if f.name == "payments"]
    assert len(payments) == 1
    assert len(payments[0].files) == 4


def test_python_unmatched_file_becomes_own_feature(tmp_path):
    backend = tmp_path / "agents"
    _write(backend / "utils.py")
    features = group_python_agent_features(tmp_path, backend)
    assert any(f.name == "utils" and f.files == ["agents/utils.py"] for f in features)


def test_spring_boot_pairs_controller_and_service(tmp_path):
    backend = tmp_path / "src" / "main" / "java" / "com" / "example"
    _write(backend / "controller" / "AlumniController.java")
    _write(backend / "service" / "AlumniService.java")
    features = group_spring_boot_features(tmp_path, tmp_path / "src")
    alumni = [f for f in features if f.name == "Alumni"]
    assert len(alumni) == 1
    assert len(alumni[0].files) == 2
