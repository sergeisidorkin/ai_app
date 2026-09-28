import { randomUUID } from "node:crypto"

export const MAX_RESUMES = 3
export const WAIT_MS = 8 * 60 * 1000
export const POLL_MS = 2000
export const RESUME_TEXT = "Продолжай, дождись находок и запиши файл."

function eachAgent(agents) {
  const store = agents?.store
  if (!store || typeof store.values !== "function") return []
  return [...store.values()].map((entry) => entry?.agent || entry).filter(Boolean)
}

export function runningChildCount(agents, parentId) {
  let running = 0
  for (const child of eachAgent(agents)) {
    const header = child.session?.header
    if (!header || header.parentSession !== parentId || header.origin !== "subagent") continue
    if (child.status === "running") running += 1
  }
  return running
}

function resumeMessage() {
  return {
    role: "user",
    id: randomUUID(),
    source: { kind: "user" },
    content: [{ type: "text", text: RESUME_TEXT }],
  }
}

export async function resumeIfSubagentsRunning({
  resumes,
  parent,
  agents,
  signal,
  now = () => Date.now(),
  sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  maxResumes = MAX_RESUMES,
  waitMs = WAIT_MS,
  pollMs = POLL_MS,
}) {
  const header = parent?.session?.header
  if (!header || header.origin === "subagent" || (header.delegationDepth ?? 0) !== 0) return false
  const parentId = header.id
  if (!parentId || runningChildCount(agents, parentId) === 0) return false
  const used = resumes.get(parentId) || 0
  if (used >= maxResumes) return false
  const deadline = now() + waitMs
  while (runningChildCount(agents, parentId) > 0 && now() < deadline) {
    if (signal?.aborted) return false
    await sleep(pollMs)
  }
  if (signal?.aborted) return false
  resumes.set(parentId, used + 1)
  parent.steer(resumeMessage())
  return true
}

export function apply(ctx) {
  const resumes = new Map()
  ctx.on("agent/turn-stopping", (payload) => resumeIfSubagentsRunning({
    resumes,
    parent: payload?.agent,
    agents: ctx.get("agents"),
    signal: payload?.signal,
  }))
}
