from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


HERE = Path(__file__).resolve().parent
VALIDATION_PORT = 8876
WINDOWS_BROWSER_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
)
MACOS_BROWSER_CANDIDATES = (
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
)


def find_browser() -> Path | None:
    configured = os.environ.get("CHROME_PATH", "").strip()
    candidates = [Path(configured)] if configured else []
    candidates.extend(WINDOWS_BROWSER_CANDIDATES)
    candidates.extend(MACOS_BROWSER_CANDIDATES)
    for command in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "msedge"):
        found = shutil.which(command)
        if found:
            candidates.append(Path(found))
    return next((path for path in candidates if path.is_file()), None)


def wait_for_health(url: str, attempts: int = 40) -> dict[str, object]:
    last_error = None
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as error:
            last_error = error
            time.sleep(0.25)
    raise RuntimeError(f"Annotation server did not become ready: {last_error}")


def main():
    browser = find_browser()
    if browser is None:
        raise FileNotFoundError(
            "Chrome, Edge, or Chromium was not found. Set CHROME_PATH to its executable."
        )
    validation_dir = HERE / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    screenshot = validation_dir / "ui_1440x900.png"
    screenshot.unlink(missing_ok=True)
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    server = subprocess.Popen(
        [sys.executable, str(HERE / "app.py"), "--port", str(VALIDATION_PORT)],
        cwd=HERE.parents[1],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )
    try:
        base_url = f"http://127.0.0.1:{VALIDATION_PORT}"
        health = wait_for_health(base_url + "/api/health")
        with tempfile.TemporaryDirectory(prefix="mpr_rel_edge_") as profile:
            subprocess.run(
                [
                    str(browser),
                    "--headless",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    "--window-size=1440,900",
                    "--virtual-time-budget=5000",
                    f"--user-data-dir={profile}",
                    f"--screenshot={screenshot}",
                    base_url + "/?annotator=ui_test",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
                timeout=25,
            )
        for _ in range(20):
            if screenshot.exists() and screenshot.stat().st_size > 0:
                break
            time.sleep(0.25)
        if not screenshot.exists() or screenshot.stat().st_size == 0:
            raise RuntimeError("Browser screenshot was not created")
        print(
            json.dumps(
                {
                    "health": health,
                    "screenshot": str(screenshot),
                    "screenshot_bytes": screenshot.stat().st_size,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
