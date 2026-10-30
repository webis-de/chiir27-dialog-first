/* Static deployment: the Python backend (app/service.py) runs in the browser with Pyodide, so that the
   prototype can be hosted as static files. Included only by the static build (scripts/build-static.py),
   which also copies the Python sources to py/ and lists them in py/files.json. */
(() => {
  const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
  const ready = (async () => {
    await new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = `${PYODIDE}pyodide.js`;
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
    const pyodide = await loadPyodide({ indexURL: PYODIDE });
    await pyodide.loadPackage(["pydantic", "sqlite3"]);
    const files = await (await fetch("py/files.json")).json();
    pyodide.FS.mkdirTree("/home/pyodide/app");
    for (const file of files) {
      pyodide.FS.writeFile(`/home/pyodide/app/${file}`, await (await fetch(`py/app/${file}`)).text());
    }
    return pyodide.runPython("from app.service import handle; handle");
  })();

  window.backend = async (url, body) => {
    const handle = await ready;
    return JSON.parse(handle(url, body === undefined ? null : JSON.stringify(body)));
  };

  // Until the backend is loaded, the dialog shows a notice instead of the opening answer.
  document.addEventListener("DOMContentLoaded", () => {
    const thread = document.getElementById("thread");
    if (!thread.children.length) {
      thread.innerHTML = '<p class="pending">Loading the catalog in your browser …</p>';
    }
  });
})();
