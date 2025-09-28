import os, importlib
from fastapi.routing import APIRoute

def _dedup_routes(app):
    seen = {}
    keep = []
    for r in app.router.routes:
        if isinstance(r, APIRoute):
            key = (r.path, tuple(sorted((r.methods or []))))
            seen[key] = r
        else:
            keep.append(r)
    keep.extend(seen.values())
    app.router.routes = keep

def _strip_conflicts(app):
    new_routes = []
    for r in app.router.routes:
        if isinstance(r, APIRoute):
            pf = getattr(r, "path", "")
            methods = set(r.methods or [])
            if (pf == "/tasks" and "GET" in methods) or (pf == "/tasks/{task_id}" and "GET" in methods):
                continue
            if (pf == "/import" and "POST" in methods):
            if (pf == "/tasks/bulk" and "PATCH" in methods):
                continue
                continue
        new_routes.append(r)
    app.router.routes = new_routes

def apply(app):
    if getattr(app.state, "rf_applied", False):
        return
    app.state.rf_applied = True

    _strip_conflicts(app)

    import bulk_router, fields_router, read_router, metrics_router, export_router, import_router, bulk_alias_router
    try:
        import admin_router
    except Exception:
        admin_router = None

    for m in (bulk_router, fields_router, read_router, metrics_router, export_router, import_router, bulk_alias_router):
        importlib.reload(m)
    if admin_router:
        importlib.reload(admin_router)

    app.include_router(bulk_router.router)        # /tasks/bulk (problemli ortamda bile kalsın)
    app.include_router(bulk_alias_router.router)  # /bulk  (yeni alias)
    app.include_router(import_router.router)      # /import
    app.include_router(fields_router.router)      # /tasks/{id}/fields
    app.include_router(export_router.router)      # /export
    app.include_router(metrics_router.router)     # /metrics
    if os.getenv("TODO_API_ENABLE_ADMIN", "0") == "1" and admin_router:
        app.include_router(admin_router.router)   # /admin/*
    app.include_router(read_router.router)        # /tasks, /tasks/{task_id}

    _dedup_routes(app)
