import { readFileSync } from "node:fs"
import { join } from "node:path"

const FILE_NAME = "report-check-temperature.json"

function selectedTemperature() {
  let raw
  try {
    raw = JSON.parse(readFileSync(join(process.cwd(), FILE_NAME), "utf8"))
  } catch {
    return undefined
  }
  const temperature = Number(raw && raw.temperature)
  if (!Number.isFinite(temperature) || temperature < 0 || temperature > 2) return undefined
  return temperature
}

export function apply(ctx) {
  ctx.on("agent/request", async (_payload, next) => {
    const resolved = await next()
    const temperature = selectedTemperature()
    if (temperature === undefined || !resolved || typeof resolved !== "object") return resolved
    return { ...resolved, temperature }
  })
}
