param([string]$AppPath = "C:\maiq_demo\apps\todo_api\app.py")

if (-not (Test-Path $AppPath)) { throw "Bulunamadı: $AppPath" }
$raw = Get-Content $AppPath -Raw
$hasOpenApi = $raw -match '"/openapi\.json"' -or $raw -match 'def\s+_openapi\('
$hasDocs    = $raw -match '"/docs"'         -or $raw -match 'def\s+_docs\('
$hasRedoc   = $raw -match '"/redoc"'        -or $raw -match 'def\s+_redoc\('

$block = @"
# === injected: docs/openapi endpoints (idempotent) ===
try:
    from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
    # /openapi.json
    if not any([r.path == "/openapi.json" for r in app.routes]):
        @app.get("/openapi.json")
        def _openapi():
            return app.openapi()
    # /docs
    if not any([r.path == "/docs" for r in app.routes]):
        @app.get("/docs")
        def _docs():
            return get_swagger_ui_html(openapi_url="/openapi.json", title="Docs")
    # /redoc
    if not any([r.path == "/redoc" for r in app.routes]):
        @app.get("/redoc")
        def _redoc():
            return get_redoc_html(openapi_url="/openapi.json", title="ReDoc")
except Exception as _e:
    pass
# === end injected ===
"@

if (-not ($hasOpenApi -and $hasDocs -and $hasRedoc)) {
  $backup = "$AppPath.bak.$([DateTime]::Now.ToString('yyyyMMdd_HHmmss'))"
  Copy-Item $AppPath $backup -Force
  ($raw.TrimEnd() + "`r`n`r`n" + $block) | Set-Content $AppPath -Encoding UTF8
  "Patched ✅ (yedek: $backup)"
} else {
  "Zaten mevcut; patch gereksiz ✅"
}
