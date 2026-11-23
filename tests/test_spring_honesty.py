"""Spring Boot extractor honesty enrichments (landed as EXTRACTOR_VERSION 12)."""

from __future__ import annotations

from pathlib import Path

from src.chunk.chunk_splitter import ChunkPlan
from src.extract.spring import extract_spring, build_spring_chunk_record
from src.storage.mirror_store import EXTRACTOR_VERSION
from src.visual.availability import is_present


FIX = Path(__file__).resolve().parent / "fixtures"


def test_extractor_version_is_21():
    assert EXTRACTOR_VERSION == 25


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
    assert record["extractorVersion"] == 25
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


def test_component_scan_and_import_never_invent_beans():
    """@ComponentScan / @Import literals alone must not invent types or Impl.

    Skip-lock (bean-index refused): package/class literals are not evidence
    for a Spring bean graph. Extract stays unchanged — never invent.
    """
    src = """
package com.example;
import com.example.OrderServiceImpl;
import com.example.config.OrderConfig;

@SpringBootApplication
@Import(OrderConfig.class)
@ComponentScan("com.example.service")
@ComponentScan(basePackages = {"com.example.repo"})
public class App {
}
"""
    types, routes = extract_spring(src)
    assert types == []
    assert routes == []
    assert "OrderServiceImpl" not in src or not any(
        "Impl" in t.name for t in types
    )


def test_bean_index_from_import_scan_still_refused():
    """Documented refusal: no bean-index / typed-Impl invent path ships."""
    src = """
@Import(FooConfig.class)
@ComponentScan(basePackages = "com.example")
public class Boot {}
"""
    types, routes = extract_spring(src)
    assert types == [] and routes == []
    # Stereotype + inject evidence required; annotations alone never seed DI.
    assert not any(hasattr(extract_spring, name) for name in (
        "build_bean_index", "resolve_bean_impl", "index_component_scan",
    ))


def test_implements_alone_never_binds_typed_impl():
    """``implements Iface`` without an explicit inject of Impl → no Impl invent."""
    src = """
package com.example;

public interface OrderService {
    void place();
}

@Service
public class OrderServiceImpl implements OrderService {
    public void place() {}
}
"""
    types, routes = extract_spring(src)
    assert routes == []
    names = {t.name for t in types}
    # Stereotype on the class is recorded; interface without stereotype is not
    # a SpringType, and no injectee/Impl edge is invented from implements.
    assert "OrderServiceImpl" in names
    impl = next(t for t in types if t.name == "OrderServiceImpl")
    assert impl.injectees == []
    assert not any(t.name.endswith("Impl") and t.kind == "interface" for t in types)


def test_autowired_interface_field_does_not_invent_impl_node():
    """Typed interface injectee stays the interface — never synthesize *Impl."""
    src = """
@RestController
public class OrderController {
    @Autowired
    private OrderService orderService;
}
"""
    types, _ = extract_spring(src)
    assert len(types) == 1
    assert types[0].injectees == [
        {"type": "OrderService", "field": "orderService", "via": "field", "assumed": False}
    ]
    assert not any("Impl" in i["type"] for i in types[0].injectees)
