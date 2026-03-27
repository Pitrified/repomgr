# Plan: Relocate Static & Templates, Self-Host Swagger

Move all non-Python assets (static files, templates) out of `src/` to the repo root, wire them through `RepomgrPaths` as the single source of truth, and replace the CDN-hosted Swagger/ReDoc UI with locally-served files — eliminating all external CDN dependencies from the CSP.

## Steps

### 1. Consolidate static assets into repo root `static/`

Move files from `src/repomgr/webapp/static/` (`css/app.css`, `css/bulma.min.css`, `js/htmx.min.js`, `img/logo.svg`) into the existing `static/` directory, merging with the already-present `swagger/` and `bulma/` subdirectories. Remove the duplicate `bulma/bulma.min.css` (keep only `css/bulma.min.css`). Delete `src/repomgr/webapp/static/` afterward.

### 2. Move templates to repo root `templates/`

Relocate all 7 template files from `src/repomgr/webapp/templates/` (including `partials/` subfolder) to a new top-level `templates/` directory. Delete the old `src/repomgr/webapp/templates/` directory. No template content changes needed — they reference `/static/…` URL paths, not filesystem paths.

### 3. Add `templates_fol` to `RepomgrPaths`

In `src/repomgr/params/repomgr_paths.py`, add `self.templates_fol = self.root_fol / "templates"` alongside the existing `self.static_fol` in `load_common_config_pre()`.

### 4. Update `main.py` to use `RepomgrPaths` and self-host Swagger

In `src/repomgr/webapp/main.py`:

- Replace the hardcoded `static_dir = Path(__file__).resolve().parent / "static"` (line 108) with `get_repomgr_paths().static_fol`.
- Set `docs_url=None, redoc_url=None` in the `FastAPI()` constructor to disable CDN-loaded docs.
- Add a custom docs router (or inline routes) (standard FastAPI endpoint names) using `get_swagger_ui_html()` and `get_redoc_html()` from `fastapi.openapi.docs`, pointing JS/CSS URLs to `/static/swagger/swagger-ui-bundle.js` and `/static/swagger/swagger-ui.css`. Include the `swagger_ui_oauth2_redirect_url` helper route.
- Download and add `redoc.standalone.js` to `static/swagger/` for self-hosted ReDoc (currently missing).
  Use classic static folder structure to save css/js files.

### 5. Update `templating.py` to use `RepomgrPaths`

In `src/repomgr/webapp/core/templating.py`, replace the hardcoded `_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"` (line 19) with `get_repomgr_paths().templates_fol`.

### 6. Simplify CSP in `middleware.py`

In `src/repomgr/webapp/core/middleware.py`, remove all `cdn.jsdelivr.net` references from `docs_csp`. Since Swagger UI's own HTML uses inline scripts/styles, keep `'unsafe-inline'` for both `script-src` and `style-src` in the docs CSP, but drop the external CDN hostnames entirely. The strict app CSP stays unchanged.

### 7. Update tests

In `tests/webapp/test_security.py`, update `test_relaxed_csp_on_docs` to assert `cdn.jsdelivr.net` is **absent** (reverse current assertion). In `tests/webapp/test_pages.py`, keep `TestStaticAssets` URL-path assertions as-is (they test `/static/…` URL routes, which don't change). Add new test(s) verifying Swagger static assets are served at `/static/swagger/swagger-ui-bundle.js` and `/static/swagger/swagger-ui.css`.

## Further Considerations

1. **ReDoc JS file** — The repo currently has Swagger UI files in `static/swagger/` but no `redoc.standalone.js`. Download it from the official CDN and commit it, or drop ReDoc support entirely? **Recommendation:** Download and add it to keep feature parity.
2. **Swagger `oauth2-redirect.html`** — FastAPI's `get_swagger_ui_oauth2_redirect_html()` returns this inline (no external file needed), but since you use Google OAuth, verify the redirect helper works with the self-hosted setup during manual testing.
3. **Stale `static/bulma/` subdirectory** — The repo root already has `static/bulma/bulma.min.css` alongside the webapp's `css/bulma.min.css`. After consolidation, remove the redundant `static/bulma/` directory to avoid confusion.
