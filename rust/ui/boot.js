// Runs before the first paint.
//
// It lives in its own file rather than inline in `index.html` because the
// Tauri shell ships a strict Content-Security-Policy: `script-src` falls back
// to `default-src 'self'`, which blocks inline scripts. A same-origin file is
// allowed, and being synchronous it still runs before the stylesheet paints.
(function () {
  var params = new URLSearchParams(location.search);
  var theme = params.get("theme");
  if (theme === "dark" || theme === "light") {
    document.documentElement.dataset.theme = theme;
  } else if (params.get("lang") || params.get("still")) {
    // Screenshot helpers may force the light palette explicitly.
    if (theme === "light") document.documentElement.dataset.theme = "light";
  }
  if (params.has("still")) document.documentElement.dataset.motion = "off";
})();
