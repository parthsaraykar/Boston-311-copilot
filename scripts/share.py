"""Share the running app over HTTPS with a free Cloudflare quick tunnel (no account needed).

Run the API first (make api), then: python -m scripts.share   (or make share)
The public URL is written to data/public_url.txt so the app's QR code points at it. Ctrl+C stops sharing.
Visitors get public mode: they can file requests and browse, but can't approve plans or run agents.
"""
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL_FILE = ROOT / "data" / "public_url.txt"


def find_cloudflared() -> str:
    for c in (ROOT / "tools" / "cloudflared", shutil.which("cloudflared")):
        if c and Path(c).exists():
            return str(c)
    sys.exit("cloudflared not found. Install it (brew install cloudflared) or put the binary in tools/.")


def main(port: int = 8000) -> None:
    proc = subprocess.Popen([find_cloudflared(), "tunnel", "--no-autoupdate", "--url", f"http://localhost:{port}"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def stop(*_):
        URL_FILE.unlink(missing_ok=True)
        proc.terminate()
        print("\nSharing stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    url = None
    for line in proc.stdout:
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m and not url:
            url = m.group(0)
            URL_FILE.write_text(url)
            print(f"\n  Public link:  {url}\n  Resident form (QR target):  {url}/#file\n\n  Keep this running while judges use it. Ctrl+C to stop.\n", flush=True)
        if "ERR" in line and "failed" in line.lower():
            print(line.strip(), flush=True)
    stop()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
