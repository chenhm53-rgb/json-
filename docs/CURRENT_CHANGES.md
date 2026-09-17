# Current Changes

- The credit checker now calls the real credit API once for each cookie.
- Cookies are sent in the `Cookie` request header by default.
- GET and POST, JSON field paths, request body templates, delays, retries, and timeouts are supported.
- Results are grouped by credit value from low to high.
- Detail and summary JSON/CSV files are generated without storing raw cookies.
- Fixed the `{cookie}` URL template so it receives the current cookie instead of an empty string.
- Added support for common cookie object formats.
