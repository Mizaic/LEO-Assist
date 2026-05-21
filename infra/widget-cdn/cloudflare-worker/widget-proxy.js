/**
 * LEO widget CDN edge proxy (Cloudflare Workers, Free tier).
 *
 * Azure Storage Static Website requires the storage web endpoint Host
 * header. Origin Rules that rewrite Host need a paid Cloudflare plan,
 * so this worker fetches the Azure origin directly instead.
 */

const ALLOWED_PREFIXES = ["/v1/", "/iframe/", "/demo/"];

function cacheOptions(pathname) {
  if (
    pathname.endsWith("/manifest.json") ||
    pathname.endsWith("/advisory.json")
  ) {
    return { cacheEverything: true, cacheTtl: 60 };
  }
  if (
    pathname.startsWith("/v1/leo-widget.js") ||
    pathname.startsWith("/iframe/")
  ) {
    return { cacheEverything: true, cacheTtl: 31536000 };
  }
  return { cacheEverything: true, cacheTtl: 3600 };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const allowed = ALLOWED_PREFIXES.some((prefix) =>
      url.pathname.startsWith(prefix),
    );
    if (!allowed) {
      return new Response("Not found", { status: 404 });
    }

    const originHost = env.ORIGIN_HOST;
    if (!originHost) {
      return new Response("Origin not configured", { status: 500 });
    }

    const originUrl = `https://${originHost}${url.pathname}${url.search}`;
    const originRequest = new Request(originUrl, {
      method: request.method,
      headers: {
        Accept: request.headers.get("Accept") || "*/*",
      },
      cf: cacheOptions(url.pathname),
    });

    return fetch(originRequest);
  },
};
