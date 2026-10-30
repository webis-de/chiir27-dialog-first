"""Static build of the prototype: the frontend, the product images, and the Python backend, which runs in the
browser with Pyodide (static/backend.js). The result can be served by any static web server, e.g. a static
Hugging Face Space (scripts/deploy-space.sh).

Usage: python3 scripts/build-static.py [out-dir]   (default build/static)
Try locally: python3 -m http.server -d build/static 8028
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.catalog import Catalog, placeholder_svg  # noqa: E402


def main(out: Path):
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "static", out)
    index = out / "index.html"
    html = index.read_text(encoding="utf-8")
    index.write_text(html.replace('<script src="app.js" defer></script>',
                                  '<script src="backend.js" defer></script>\n  <script src="app.js" defer></script>'),
                     encoding="utf-8")
    (out / "img").mkdir()
    for product in Catalog().products:
        (out / "img" / f"{product['id']}.svg").write_text(placeholder_svg(product), encoding="utf-8")
    sources = sorted(p.name for p in (ROOT / "app").glob("*.py") if p.name != "main.py")  # main.py needs FastAPI
    (out / "py" / "app").mkdir(parents=True)
    for name in sources:
        shutil.copy(ROOT / "app" / name, out / "py" / "app" / name)
    (out / "py" / "files.json").write_text(json.dumps(sources), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "build" / "static").resolve())
