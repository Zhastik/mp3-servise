"""Keep HTTP, use cases, persistence and media adapters from mixing again.

These checks inspect imports and operations without starting the application or
connecting to a database. Aliased and relative imports are resolved as well.
"""
import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "api_route"}


def sources():
    for path in sorted(APP.rglob("*.py")):
        relative = path.relative_to(APP)
        yield relative, ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(relative))


def imported_names(path, tree):
    package = ["app", *path.parent.parts]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.asname or alias.name.split(".")[0], alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                prefix = package[:len(package) - node.level + 1]
                module = ".".join([*prefix, *((node.module or "").split(".") if node.module else [])])
            else:
                module = node.module or ""
            for alias in node.names:
                yield alias.asname or alias.name, f"{module}.{alias.name}", node.lineno


def under(name, prefix):
    return name == prefix or name.startswith(prefix + ".")


def assert_no(violations):
    assert not violations, "Architecture boundary violated:\n" + "\n".join(violations)


def test_use_cases_persistence_and_media_adapters_are_transport_independent():
    violations = []
    for path, tree in sources():
        application_layer = path.parts[0] == "modules" and path.stem in {"service", "repository", "security", "models", "schemas", "ports"}
        media_adapter = path.parts[:2] == ("infrastructure", "media")
        if not (application_layer or media_adapter):
            continue
        for _, name, line in imported_names(path, tree):
            if any(under(name, prefix) for prefix in ("fastapi", "starlette", "app.api", "app.main", "app.lifespan", "app.core.middleware")):
                violations.append(f"{path}:{line} imports transport dependency {name}")
            if name.startswith("app.modules.") and any(part in {"routers", "dependencies"} for part in name.split(".")):
                violations.append(f"{path}:{line} imports an HTTP/composition adapter {name}")
    assert_no(violations)


def test_routers_do_not_query_or_manage_database_transactions():
    violations = []
    for path, tree in sources():
        if path.stem != "routers":
            continue
        for _, name, line in imported_names(path, tree):
            if under(name, "sqlalchemy") or under(name, "app.core.database") or under(name, "app.core.db_depends") or ".repository" in name:
                violations.append(f"{path}:{line} imports persistence dependency {name}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"execute", "scalar", "scalars", "commit", "rollback", "flush", "refresh", "begin", "begin_nested"}:
                    violations.append(f"{path}:{node.lineno} performs persistence operation {node.func.attr}")
    assert_no(violations)


def test_repositories_cannot_finish_the_callers_transaction():
    violations = []
    for path, tree in sources():
        if path.stem != "repository":
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"commit", "rollback"}:
                violations.append(f"{path}:{node.lineno} ends the use-case transaction with {node.func.attr}")
        for _, name, line in imported_names(path, tree):
            if any(part in {"service", "routers", "dependencies"} for part in name.split(".")):
                violations.append(f"{path}:{line} depends on an upper layer {name}")
    assert_no(violations)


def test_services_use_repositories_and_ports_instead_of_direct_sql_or_media_adapters():
    violations = []
    for path, tree in sources():
        if path.parts[0] != "modules" or path.stem != "service":
            continue
        for _, name, line in imported_names(path, tree):
            # Session typing and the transaction helper are allowed; SQL
            # construction/execution and concrete media adapters are not.
            if under(name, "app.infrastructure") or (under(name, "sqlalchemy") and not under(name, "sqlalchemy.ext.asyncio.AsyncSession") and not under(name, "sqlalchemy.exc")):
                violations.append(f"{path}:{line} bypasses a repository/port with {name}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"execute", "scalar", "scalars", "flush", "refresh"}:
                violations.append(f"{path}:{node.lineno} executes SQL outside its repository")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"get", "add", "add_all", "delete", "merge"}:
                receiver = node.func.value
                direct_session = isinstance(receiver, ast.Name) and receiver.id in {"db", "session"}
                session_attribute = isinstance(receiver, ast.Attribute) and receiver.attr in {"db", "session"}
                if direct_session or session_attribute:
                    violations.append(f"{path}:{node.lineno} accesses ORM persistence outside its repository")
    assert_no(violations)


def test_http_routes_are_registered_only_in_http_adapters():
    violations = []
    for path, tree in sources():
        allowed = path.parts[0] == "api" or path.stem == "routers" or path == Path("main.py")
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr in HTTP_METHODS and not allowed:
                    violations.append(f"{path}:{node.lineno} declares an HTTP route outside an HTTP adapter")
    assert_no(violations)


def test_removed_god_modules_cannot_be_reintroduced_as_dependencies():
    violations = []
    for path, tree in sources():
        for _, name, line in imported_names(path, tree):
            if any(under(name, old) for old in ("app.core.auth", "app.api.catalog", "app.media")):
                violations.append(f"{path}:{line} imports removed monolithic module {name}")
    assert_no(violations)


def test_track_use_cases_and_media_processing_share_the_same_ports():
    trees = {path: tree for path, tree in sources()}
    service_path = Path("modules/tracks/service.py")
    processor_path = Path("infrastructure/media/processor.py")
    service = trees[service_path]
    processor = trees[processor_path]
    service_imports = {alias: name for alias, name, _ in imported_names(service_path, service)}
    processor_imports = {alias: name for alias, name, _ in imported_names(processor_path, processor)}
    use_case = next(node for node in service.body if isinstance(node, ast.ClassDef) and node.name == "TrackService")
    constructor = next(node for node in use_case.body if isinstance(node, ast.FunctionDef) and node.name == "__init__")
    constructor_types = {service_imports.get(node.id) for argument in constructor.args.args if argument.annotation for node in ast.walk(argument.annotation) if isinstance(node, ast.Name)}
    prefix = "app.modules.tracks.ports."
    assert {prefix + name for name in ("AudioProcessor", "AudioStorage", "FileCleanup")} <= constructor_types
    assert prefix + "UploadSource" in processor_imports.values()
    assert prefix + "StoredAudio" in processor_imports.values()
