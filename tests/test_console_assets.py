from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSOLE = ROOT / "console"
DEPLOY = ROOT / "deploy" / "console"


def test_console_uses_external_same_origin_assets_without_inline_code():
    page = (CONSOLE / "index.html").read_text(encoding="utf-8")
    script = (CONSOLE / "app.js").read_text(encoding="utf-8")

    assert '<script src="app.js" defer></script>' in page
    assert '<link rel="stylesheet" href="styles.css">' in page
    assert "<script>" not in page
    assert "<style>" not in page
    assert "localStorage" not in script
    assert "sessionStorage" not in script
    assert "credentials: \"same-origin\"" in script
    assert 'redirect: "error"' in script
    assert "Authorization:" in script


def test_console_downloads_verify_artifact_integrity():
    script = (CONSOLE / "app.js").read_text(encoding="utf-8")

    assert "crypto.subtle.digest(\"SHA-256\"" in script
    assert "X-Content-SHA256" in script
    assert "artifact.checksum.value" in script
    assert "artifact.size_bytes" in script


def test_console_reverse_proxy_enforces_same_origin_security_headers():
    config = (DEPLOY / "default.conf").read_text(encoding="utf-8")
    dockerfile = (DEPLOY / "Dockerfile").read_text(encoding="utf-8")

    assert "proxy_pass http://foundry-control-plane:8000/;" in config
    assert "proxy_set_header Authorization $http_authorization;" in config
    assert "client_max_body_size 32m;" in config
    assert "frame-ancestors 'none'" in config
    assert "X-Content-Type-Options" in config
    assert "nginx-unprivileged" in dockerfile
