"""Integration tests using a small synthetic repo (not the real alumni
clone, which lives outside the repo and isn't available in CI) covering
the same shapes: a React API client calling a Go Fiber backend."""

import json
from pathlib import Path

from src.detect.project_type import detect_project_type
from src.extract.extractor import extract_repo


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _build_synthetic_repo(root: Path) -> None:
    _write(root / "package.json", json.dumps({
        "dependencies": {"react": "^19.0.0", "axios": "^1.9.0"},
    }))
    _write(root / "src" / "api" / "client.ts", """
import axios from 'axios';
export const api = axios.create({ baseURL: '/api/v1' });
""")
    _write(root / "src" / "features" / "widgets" / "widgetApi.ts", """
import { api } from '../../api/client';

export interface Widget {
  id: number;
  name: string;
}

export async function fetchWidget(id: number): Promise<Widget> {
  const { data } = await api.get(`/widgets/${id}`);
  return data;
}

export async function listWidgets(): Promise<Widget[]> {
  const { data } = await api.get('/widgets');
  return data;
}
""")
    _write(root / "api" / "go.mod", "module example.com/widgetapp/api\n\ngo 1.22\n")
    _write(root / "api" / "main.go", """
package main

import (
	"github.com/gofiber/fiber/v2"
)

func main() {
	app := fiber.New()
	v1 := app.Group("/api/v1")
	v1.Get("/widgets", listHandler)
	v1.Get("/widgets/:id", getHandler)
	app.Listen(":8080")
}
""")


def test_extract_repo_links_frontend_calls_to_backend_routes(tmp_path):
    _build_synthetic_repo(tmp_path)
    project_type = detect_project_type(tmp_path)
    records = extract_repo(tmp_path, project_type)

    widget_api = next(r for r in records if r["filePath"] == "src/features/widgets/widgetApi.ts")
    main_go = next(r for r in records if r["filePath"] == "api/main.go")

    assert main_go["chunkId"] in widget_api["featureMapping"]
    assert widget_api["chunkId"] in main_go["featureMapping"]

    get_calls = {c["url"]: c for c in widget_api["apiCalls"]}
    assert "/widgets" in get_calls
    assert get_calls["/widgets"]["assumed"] is False
    assert get_calls["/widgets/${id}"]["assumed"] is True  # template literal


def test_extract_repo_required_fields_present_on_every_record(tmp_path):
    _build_synthetic_repo(tmp_path)
    project_type = detect_project_type(tmp_path)
    records = extract_repo(tmp_path, project_type)

    required = ["chunkId", "filePath", "featureName", "projectType", "confidence", "confidenceLevel"]
    for record in records:
        for field in required:
            assert field in record, f"missing {field} in {record.get('filePath')}"


def test_extract_repo_data_model_captured_with_fields(tmp_path):
    _build_synthetic_repo(tmp_path)
    project_type = detect_project_type(tmp_path)
    records = extract_repo(tmp_path, project_type)

    widget_api = next(r for r in records if r["filePath"] == "src/features/widgets/widgetApi.ts")
    model_names = {m["name"] for m in widget_api["dataModels"]}
    assert "Widget" in model_names


def test_extract_repo_go_route_types_classified(tmp_path):
    _build_synthetic_repo(tmp_path)
    project_type = detect_project_type(tmp_path)
    records = extract_repo(tmp_path, project_type)

    main_go = next(r for r in records if r["filePath"] == "api/main.go")
    by_path = {r["path"]: r for r in main_go["routes"]}
    assert by_path["/api/v1/widgets"]["type"] == "static"
    assert by_path["/api/v1/widgets/:id"]["type"] == "dynamic"


def test_pull_request_field_honestly_null_with_note(tmp_path):
    _build_synthetic_repo(tmp_path)
    project_type = detect_project_type(tmp_path)
    records = extract_repo(tmp_path, project_type)
    for record in records:
        assert record["pullRequest"] is None
        assert "pullRequestNote" in record
