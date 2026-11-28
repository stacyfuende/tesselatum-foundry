from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pytest

from playwright.sync_api import sync_playwright


PAGE = Path(__file__).parents[2] / "viewer" / "request" / "index.html"
SOURCE = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "id": "site-001",
            "geometry": {"type": "Point", "coordinates": [36.8219, -1.2921]},
            "properties": {"site_name": "Central acquisition site"},
        }
    ],
}


class _QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        return


def _start_servers(response_status: int):
    captured = {}

    class ApiHandler(BaseHTTPRequestHandler):
        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Max-Age", "0")
            self.end_headers()

        def do_POST(self):
            captured["path"] = urlparse(self.path).path
            captured["authorization"] = self.headers.get("Authorization")
            captured["payload"] = json.loads(
                self.rfile.read(int(self.headers["Content-Length"]))
            )
            self.send_response(response_status)
            self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
            self.send_header("Access-Control-Expose-Headers", "X-Foundry-Request-ID")
            self.send_header("Cache-Control", "no-store")
            if response_status == 200:
                self.send_header("Content-Type", "application/zip")
                self.send_header(
                    "Content-Disposition", 'attachment; filename="spatial-product.zip"'
                )
                self.send_header("X-Foundry-Request-ID", "browser-request-001")
                body = b"PK\\x03\\x04browser-test"
            else:
                self.send_header("Content-Type", "application/json")
                body = b'{"error":"product_not_releasable","status":"rejected"}'
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    static = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        lambda *args, **kwargs: _QuietStaticHandler(
            *args, directory=str(PAGE.parent), **kwargs
        ),
    )
    api = ThreadingHTTPServer(("127.0.0.1", 0), ApiHandler)
    threads = [
        threading.Thread(target=static.serve_forever, daemon=True),
        threading.Thread(target=api.serve_forever, daemon=True),
    ]
    for thread in threads:
        thread.start()
    return static, api, threads, captured


def _prepare_request(page):
    page.goto(page._static_url)
    page.locator("#source-file").set_input_files(
        {
            "name": "sites.geojson",
            "mimeType": "application/geo+json",
            "buffer": json.dumps(SOURCE).encode(),
        }
    )
    assert "passed the local intake checks" in page.locator("#file-status").inner_text()
    page.locator("#confirm-crs").check()
    page.locator("#audience").fill("Property investment team")
    page.locator("#context").fill("Prepare sites for metric distance analysis.")
    page.locator("#prepare").click()
    assert page.locator("#download-area").is_visible()


@pytest.mark.parametrize(
    ("response_status", "expected_status"),
    [(200, "success"), (422, "error")],
)
def test_customer_request_page_completes_browser_submission(response_status, expected_status):
    static, api, threads, captured = _start_servers(response_status)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(accept_downloads=True)
            page._static_url = f"http://127.0.0.1:{static.server_port}/index.html"
            _prepare_request(page)
            page.locator("#api-endpoint").fill(
                f"http://127.0.0.1:{api.server_port}/v1/products"
            )
            page.locator("#api-token").fill("Bearer browser-test-token")
            page.locator("#confirm-submit").check()

            if response_status == 200:
                with page.expect_download() as download_info:
                    page.locator("#submit-product").click()
                download = download_info.value
                assert download.suggested_filename == "spatial-product.zip"
                assert "browser-request-001" in page.locator("#submit-status").inner_text()
            else:
                page.locator("#submit-product").click()
                page.wait_for_function(
                    "() => document.querySelector('#submit-status').innerText.includes('HTTP 422')"
                )
                assert "HTTP 422" in page.locator("#submit-status").inner_text()

            assert expected_status in page.locator("#submit-status").get_attribute("class")
            assert captured["path"] == "/v1/products"
            assert captured["authorization"] == "Bearer browser-test-token"
            envelope = captured["payload"]
            assert envelope["request_version"] == "1.0.0"
            assert envelope["request"]["audience"] == "Property investment team"
            assert envelope["request"]["decision_context"] == (
                "Prepare sites for metric distance analysis."
            )
            assert json.loads(
                base64.b64decode(envelope["source_file_base64"])
            ) == SOURCE
            assert page.locator("#api-token").input_value() == "Bearer browser-test-token"
            page.evaluate("window.dispatchEvent(new Event('pagehide'))")
            assert page.locator("#api-token").input_value() == ""
            browser.close()
    finally:
        for server in (static, api):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=3)
