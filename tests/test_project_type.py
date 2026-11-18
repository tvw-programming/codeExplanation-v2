import json
from pathlib import Path

from src.detect.project_type import detect_project_type


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_detects_react_frontend_only(tmp_path):
    _write(tmp_path / "package.json", json.dumps({"dependencies": {"react": "^19.0.0"}}))
    result = detect_project_type(tmp_path)
    assert result.frontend_stack == "react"
    assert result.backend_stacks == []
    assert result.architecture == "monolith"
    assert result.dockerized is False


def test_detects_angular_frontend(tmp_path):
    _write(tmp_path / "package.json", json.dumps({"dependencies": {"@angular/core": "^17.0.0"}}))
    result = detect_project_type(tmp_path)
    assert result.frontend_stack == "angular"


def test_detects_go_backend(tmp_path):
    _write(tmp_path / "api" / "go.mod", "module example.com/api\n\ngo 1.22\n")
    result = detect_project_type(tmp_path)
    assert result.backend_stacks == ["go"]
    assert result.frontend_stack is None


def test_detects_python_backend(tmp_path):
    _write(tmp_path / "requirements.txt", "fastapi\n")
    result = detect_project_type(tmp_path)
    assert result.backend_stacks == ["python"]


def test_detects_spring_boot_vs_plain_java(tmp_path):
    _write(tmp_path / "pom.xml", "<project><dependency>org.springframework.boot</dependency></project>")
    result = detect_project_type(tmp_path)
    assert result.backend_stacks == ["spring_boot"]


def test_detects_plain_java_when_no_spring_dependency(tmp_path):
    _write(tmp_path / "pom.xml", "<project><dependency>some.other.framework</dependency></project>")
    result = detect_project_type(tmp_path)
    assert result.backend_stacks == ["java"]


def test_full_stack_single_backend_is_monolith(tmp_path):
    _write(tmp_path / "package.json", json.dumps({"dependencies": {"react": "^19.0.0"}}))
    _write(tmp_path / "api" / "go.mod", "module example.com/api\n\ngo 1.22\n")
    result = detect_project_type(tmp_path)
    assert result.frontend_stack == "react"
    assert result.backend_stacks == ["go"]
    assert result.architecture == "monolith"


def test_two_sibling_backend_roots_is_microservice(tmp_path):
    _write(tmp_path / "service-a" / "go.mod", "module example.com/a\n\ngo 1.22\n")
    _write(tmp_path / "service-b" / "go.mod", "module example.com/b\n\ngo 1.22\n")
    result = detect_project_type(tmp_path)
    assert result.architecture == "microservice"


def test_dockerized_flag_true_when_dockerfile_present(tmp_path):
    _write(tmp_path / "Dockerfile", "FROM node:20\n")
    result = detect_project_type(tmp_path)
    assert result.dockerized is True


def test_dockerized_flag_false_when_absent(tmp_path):
    _write(tmp_path / "package.json", "{}")
    result = detect_project_type(tmp_path)
    assert result.dockerized is False


def test_no_unknown_fallback_when_nothing_matches(tmp_path):
    _write(tmp_path / "README.md", "just docs")
    result = detect_project_type(tmp_path)
    assert result.frontend_stack is None
    assert result.backend_stacks == []
    assert result.to_dict()["frontend"] is None
    assert "unknown" not in json.dumps(result.to_dict())


def test_stray_python_files_without_marker_are_surfaced_not_claimed(tmp_path):
    # Mirrors the alumni-web repo: .py files exist with no requirements.txt
    # or pyproject.toml anywhere. Must not be promoted to a backend stack.
    _write(tmp_path / "package.json", json.dumps({"dependencies": {"react": "^19.0.0"}}))
    _write(tmp_path / "app" / "a.py", "print('hi')\n")
    _write(tmp_path / "src" / "existing.py", "print('hi')\n")
    result = detect_project_type(tmp_path)
    assert "python" not in result.backend_stacks
    assert "app/a.py" in result.unclaimed_hint_files.get("python", [])
    assert "src/existing.py" in result.unclaimed_hint_files.get("python", [])
