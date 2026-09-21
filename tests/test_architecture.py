"""ARC-1: the import rules of ARCHITECTURE.md section 1 and the service dependency graph of section 3."""
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent / "app"

# Service graph: each service may import only these other services (downward only).
HELPERS = {"errors", "audit", "settings", "validation", "outlet_service"}
ALLOWED_SERVICES = {
    "auth_service": set(),
    "data_management_service": set(),
    "inventory_service": set(),
    "forecasting_service": {"data_management_service"},
    "kitchen_service": {"data_management_service", "inventory_service"},
    "recommendation_service": {"forecasting_service", "inventory_service", "data_management_service"},
    "alert_service": {"recommendation_service", "inventory_service", "kitchen_service", "forecasting_service"},
    "dashboard_service": {"auth_service", "data_management_service", "inventory_service", "forecasting_service",
                          "kitchen_service", "recommendation_service", "alert_service"},
}


def imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            base = node.module
            found.add(base)
            found.update(f"{base}.{a.name}" for a in node.names)
    return found


def modules(sub: str):
    return sorted((ROOT / sub).rglob("*.py"))


def starts(names: set[str], *prefixes: str) -> list[str]:
    return sorted(n for n in names if any(n == p or n.startswith(p + ".") for p in prefixes))


def test_controllers_have_no_business_logic():
    for path in modules("controllers"):
        bad = starts(imports(path), "app.models", "app.ml", "app.extensions", "sqlalchemy", "flask_sqlalchemy")
        assert not bad, f"{path.name} imports {bad}"
        assert ".commit(" not in path.read_text(), f"{path.name} commits a transaction"


def test_services_do_not_know_http():
    for path in modules("services"):
        names = imports(path)
        assert not starts(names, "app.controllers", "flask_login"), path.name
        assert "flask.request" not in names and "flask.session" not in names, path.name
        assert "flask.g" not in names and "flask.jsonify" not in names, path.name
        if path.name != "forecasting_service.py":
            assert not starts(names, "app.ml"), f"{path.name} must not import app.ml"


def test_service_dependency_graph_is_downward():
    for path in modules("services"):
        name = path.stem
        if name in HELPERS or name == "__init__":
            continue
        assert name in ALLOWED_SERVICES, f"unknown service {name}: add it to the graph"
        used = {n.split(".")[2] for n in imports(path) if n.startswith("app.services.") and n.count(".") >= 2}
        used -= HELPERS | {name}
        extra = used - ALLOWED_SERVICES[name]
        assert not extra, f"{name} may not import {sorted(extra)}"


def test_ml_is_pure():
    for path in modules("ml"):
        bad = starts(imports(path), "flask", "app.models", "app.services", "app.controllers", "sqlalchemy", "app.extensions")
        assert not bad, f"{path.name} imports {bad}"


def test_models_only_import_extensions_and_sqlalchemy():
    for path in modules("models"):
        bad = starts(imports(path), "flask", "app.services", "app.controllers", "app.ml", "app.utils")
        assert not bad, f"{path.name} imports {bad}"


def test_seed_goes_through_services():
    for path in modules("seed"):
        bad = starts(imports(path), "app.models", "app.controllers", "sqlalchemy", "app.extensions")
        assert not bad, f"{path.name} imports {bad}"
