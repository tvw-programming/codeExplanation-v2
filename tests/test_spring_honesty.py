"""Spring Boot extractor honesty enrichments (landed as EXTRACTOR_VERSION 12)."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.extract.spring import extract_spring, build_spring_chunk_record
from src.storage.mirror_store import EXTRACTOR_VERSION
from src.visual.availability import is_present


FIX = Path(__file__).resolve().parent / "fixtures"


def test_extractor_version_is_18():
    assert EXTRACTOR_VERSION == 18


def test_bare_request_mapping_is_all_not_get():
    src = """
@RestController
@RequestMapping("/api")
public class C {
    @RequestMapping("/ping")
    public String ping() { return "ok"; }
}
"""
    _types, routes = extract_spring(src)
    hits = [r for r in routes if r.path == "/api/ping"]
    assert hits
    assert all(r.method == "ALL" for r in hits)
    assert not any(r.method == "GET" for r in hits)


def test_multi_request_method_emits_one_route_each():
    src = """
@RestController
public class C {
    @RequestMapping(value="/x", method={RequestMethod.POST, RequestMethod.PUT})
    public void x() {}
}
"""
    _types, routes = extract_spring(src)
    methods = {r.method for r in routes if r.path == "/x"}
    assert methods == {"POST", "PUT"}
    assert "GET" not in methods


def test_path_array_emits_one_route_per_path():
    src = """
@RestController
@RequestMapping({"/api", "/v1"})
public class C {
    @GetMapping({"/a", "/b"})
    public String dual() { return "x"; }
}
"""
    _types, routes = extract_spring(src)
    paths = {r.path for r in routes if r.method == "GET"}
    assert paths == {"/api/a", "/api/b", "/v1/a", "/v1/b"}


def test_placeholder_path_is_assumed():
    src = """
@RestController
@RequestMapping("${api.prefix}")
public class C {
    @GetMapping("/users")
    public String users() { return "x"; }

    @GetMapping("#{spel.path}")
    public String spel() { return "y"; }
}
"""
    _types, routes = extract_spring(src)
    assert any("${api.prefix}" in r.path and r.assumed for r in routes)
    assert any("#{spel.path}" in r.path and r.assumed for r in routes)


def test_autowired_setter_and_inject_field():
    src = """
@Service
public class OrderService {
    @Inject
    private PaymentClient paymentClient;

    @Autowired
    public void setRepo(OrderRepository repo) {}
}
"""
    types, _routes = extract_spring(src)
    assert types
    vias = {(i["type"], i["via"], i["assumed"]) for i in types[0].injectees}
    assert ("PaymentClient", "field", False) in vias
    assert ("OrderRepository", "setter", False) in vias


def test_multi_ctor_without_annotation_is_assumed():
    src = """
@Service
public class Svc {
    public Svc() {}
    public Svc(UserRepository users) {}
}
"""
    types, _ = extract_spring(src)
    inj = types[0].injectees
    assert any(i["type"] == "UserRepository" and i["via"] == "constructor" and i["assumed"] for i in inj)


def test_single_ctor_unannotated_is_confident():
    src = """
@RestController
public class UserController {
    public UserController(UserService userService) {}
}
"""
    types, _ = extract_spring(src)
    inj = types[0].injectees
    assert inj
    assert all(i["type"] == "UserService" and not i["assumed"] for i in inj)


def test_imports_never_become_injectees():
    src = """
package com.example;
import com.example.OrderServiceImpl;
import com.example.ExtraHelper;

@RestController
public class OrderController {
    private final OrderService orderService;
    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }
}
"""
    types, _ = extract_spring(src)
    names = {i["type"] for i in types[0].injectees}
    assert names == {"OrderService"}
    assert "OrderServiceImpl" not in names
    assert "ExtraHelper" not in names


def test_spring_data_repository_interface_no_impl():
    src = """
public interface UserRepository extends JpaRepository<User, Long> {
    User findByEmail(String email);
}
"""
    types, routes = extract_spring(src)
    assert len(types) == 1
    assert types[0].name == "UserRepository"
    assert types[0].stereotype == "Repository"
    assert types[0].kind == "interface"
    assert types[0].injectees == []
    assert routes == []
    # No invented *Impl type
    assert not any("Impl" in t.name for t in types)


def test_annotated_repository_interface():
    src = """
@Repository
public interface AccountRepository {
    Account findById(long id);
}
"""
    types, _ = extract_spring(src)
    assert types[0].name == "AccountRepository"
    assert types[0].kind == "interface"
    assert types[0].stereotype == "Repository"


def test_lombok_and_request_mapping_method_still_work():
    src = """
@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class C {
    private final UserService userService;

    @GetMapping("/{id:[0-9]+}")
    public User get(@PathVariable String id) { return userService.find(id); }

    @RequestMapping(value="/search", method=RequestMethod.POST)
    public void search() {}
}
"""
    types, routes = extract_spring(src)
    assert any(i["type"] == "UserService" and i["via"] == "lombok" for i in types[0].injectees)
    assert any(r.method == "POST" and "/search" in r.path for r in routes)
    assert any(r.method == "GET" and "{id:[0-9]+}" in r.path for r in routes)


def test_fixture_controller_builds_di_graph(tmp_path: Path):
    dest = tmp_path / "UserController.java"
    dest.write_text((FIX / "spring" / "UserController.java").read_text())
    chunk = ChunkPlan("UserController", "Users", "spring_boot", "UserController.java", 40, "small")
    record = build_spring_chunk_record(
        tmp_path, chunk, {"frontend": None, "backend": ["spring_boot"]},
    )
    assert record["extractorVersion"] == 18
    assert record["springTypes"]
    assert record["springTypes"][0]["kind"] == "class"
    assert is_present(record["visualAvailability"]["componentTree"])
    graph = record["visualGraph"]
    assert graph["kind"] == "di_graph"
    inject = [e for e in graph["edges"] if e["kind"] == "injects"]
    assert inject
    assert any("UserService" in (e["to"] or "") for e in inject)
    # Still never an imports-as-inject edge kind for DI
    assert not any(e["kind"] == "imports" for e in graph["edges"])
