// LEO widget loader -- content-addressed bundle resolver.
//
// Integrators embed ONE script tag:
//   <script type="module" src="https://<cdn>/v1/leo-loader.js"></script>
//
// This loader (short-cached, always fresh) reads manifest.json to find
// the current bundle filename (immutable, long-cached), then imports it.
// The custom element <leo-sbar> registers itself on import.
//
// Cache strategy:
//   leo-loader.js    max-age=60, must-revalidate  (always pick up new pointer)
//   manifest.json    max-age=60, must-revalidate  (same)
//   leo-widget.*.js  max-age=31536000, immutable  (hash changes per release)

(async () => {
  const base = new URL("./", import.meta.url).href;

  let manifest;
  try {
    const res = await fetch(`${base}manifest.json`, {
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    manifest = await res.json();
  } catch (err) {
    console.error("[LEO loader] Failed to fetch manifest:", err);
    document.dispatchEvent(
      new CustomEvent("leo:loader-error", {
        detail: { reason: "manifest-fetch-failed", error: String(err) },
      })
    );
    return;
  }

  const bundle = manifest.bundle;
  if (!bundle) {
    console.error("[LEO loader] manifest.json has no bundle field");
    document.dispatchEvent(
      new CustomEvent("leo:loader-error", {
        detail: { reason: "manifest-no-bundle" },
      })
    );
    return;
  }

  try {
    await import(`${base}${bundle}`);
  } catch (err) {
    console.error("[LEO loader] Failed to import bundle:", bundle, err);
    document.dispatchEvent(
      new CustomEvent("leo:loader-error", {
        detail: { reason: "bundle-import-failed", bundle, error: String(err) },
      })
    );
  }
})();
