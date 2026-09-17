import { readFile, realpath, stat } from "node:fs/promises"
import { extname, isAbsolute } from "node:path"

const BRAND_GLOBAL = "__IMC_DSH_BRAND__"
const LOGO_ROUTE = "/plugins/imc-dsh-brand/logo"
const MIME = {
  ".gif": "image/gif",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
}

export const inject = ["webServer"]

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
}

async function loadLogo(logoPath) {
  if (!logoPath) {
    return null
  }
  if (!isAbsolute(logoPath)) {
    throw new Error("imc-dsh-brand: logoPath must be an absolute path")
  }
  const canonicalPath = await realpath(logoPath)
  const info = await stat(canonicalPath)
  if (!info.isFile()) {
    throw new Error("imc-dsh-brand: logoPath must be a regular file")
  }
  const contentType = MIME[extname(canonicalPath).toLowerCase()]
  if (!contentType) {
    throw new Error("imc-dsh-brand: logoPath must be gif, jpeg, jpg, png, svg, or webp")
  }
  return { canonicalPath, contentType }
}

function serveLogo(logo) {
  return async (req, res) => {
    if (req.method !== "GET" && req.method !== "HEAD") {
      res.writeHead(405, { allow: "GET, HEAD" })
      res.end()
      return
    }
    try {
      const body = await readFile(logo.canonicalPath)
      res.writeHead(200, {
        "cache-control": "no-store",
        "content-length": String(body.byteLength),
        "content-type": logo.contentType,
        "x-content-type-options": "nosniff",
      })
      res.end(req.method === "HEAD" ? undefined : body)
    } catch {
      res.writeHead(404)
      res.end()
    }
  }
}

function brandIndex(html, boot) {
  let rendered = html.replace(
    /<title\b[^>]*>[\s\S]*?<\/title\s*>/i,
    `<title>${escapeHtml(boot.productName)}</title>`,
  )
  if (boot.logoHref) {
    rendered = rendered.replace(
      /<link\b(?=[^>]*\brel\s*=\s*["']icon["'])[^>]*>/i,
      `<link rel="icon" href="${escapeHtml(boot.logoHref)}" type="image/svg+xml">`,
    )
  }
  return rendered
}

export async function apply(ctx, config = {}) {
  const productName = String(config.productName || "IMC Montan AI").trim() || "IMC Montan AI"
  const logoAlt = String(config.logoAlt || productName).trim() || productName
  const logo = await loadLogo(config.logoPath)
  const boot = {
    productName,
    logoAlt,
    ...(logo ? { logoHref: LOGO_ROUTE } : {}),
  }

  ctx.on("webserver/index-inject", (table) => {
    table.push({ kind: "global", name: BRAND_GLOBAL, value: boot })
  })
  ctx.effect(
    () => ctx.webServer.tapIndex((html) => brandIndex(html, boot)),
    "imc-dsh-brand: document metadata",
  )
  if (logo) {
    ctx.effect(
      () => ctx.webServer.register({ kind: "exact", path: LOGO_ROUTE, handler: serveLogo(logo) }),
      "imc-dsh-brand: logo route",
    )
  }
}

export { BRAND_GLOBAL, LOGO_ROUTE }
