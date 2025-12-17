"""Launch Chrome with the project profile in remote-debug mode for manual setup (e.g., install Tampermonkey)."""
import os
import shutil
import subprocess
import sys


def _find_chrome_executable() -> str:
    """Locate Chrome on common Windows paths or via PATH."""
    candidates = [
        os.environ.get("CHROME_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        shutil.which("chrome"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    raise FileNotFoundError(
        "Chrome executable not found. Set CHROME_PATH or install Chrome."
    )


def main():
    chrome_path = _find_chrome_executable()
    profile_dir = os.path.abspath("chrome_profile")
    os.makedirs(profile_dir, exist_ok=True)

    # Remote debugging lets Selenium attach later if needed; also keeps the profile persistent.
    port = 9222
    cmd = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--disable-blink-features=AutomationControlled",
    ]

    print("Launching Chrome for manual setup (install Tampermonkey script, etc.)...")
    print("Command:", " ".join(cmd))
    subprocess.Popen(cmd)
    print(
        "Chrome started. Finish installing Tampermonkey/userscript in this profile, then close the browser."
    )


if __name__ == "__main__":
    main()
