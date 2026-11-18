from src.extract.feature_mapping import match_calls_to_routes, normalize_path


def test_normalize_path_strips_dynamic_segments():
    assert normalize_path("/alumni/${id}") == "alumni/{}"
    assert normalize_path("/api/v1/alumni/:id") == "api/v1/alumni/{}"
    assert normalize_path("/alumni") == "alumni"


def test_match_calls_to_routes_with_base_url():
    frontend_calls = [("fe-1", "GET", "/alumni", False)]
    backend_routes = [("be-1", "GET", "/api/v1/alumni", False)]
    links = match_calls_to_routes(frontend_calls, backend_routes, "/api/v1")
    assert len(links) == 1
    assert links[0].frontend_chunk_id == "fe-1"
    assert links[0].backend_chunk_id == "be-1"
    assert links[0].assumed is False


def test_match_calls_to_routes_dynamic_segment_marked_assumed():
    frontend_calls = [("fe-1", "PUT", "/alumni/${id}", True)]
    backend_routes = [("be-1", "PUT", "/api/v1/alumni/:id", False)]
    links = match_calls_to_routes(frontend_calls, backend_routes, "/api/v1")
    assert len(links) == 1
    assert links[0].assumed is True


def test_no_match_when_method_differs():
    frontend_calls = [("fe-1", "DELETE", "/alumni", False)]
    backend_routes = [("be-1", "GET", "/api/v1/alumni", False)]
    links = match_calls_to_routes(frontend_calls, backend_routes, "/api/v1")
    assert links == []


def test_no_base_url_uses_raw_call_path():
    frontend_calls = [("fe-1", "GET", "/health", False)]
    backend_routes = [("be-1", "GET", "/health", False)]
    links = match_calls_to_routes(frontend_calls, backend_routes, None)
    assert len(links) == 1
