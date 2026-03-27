1. When Cloudflare Workers supports Python 3.14 in Pyodide, we want to remove the `from __future__ import annotations` hack we use to stringify the output annotation hints due to our lazy loading of panel where necessary for `views`.

