// src/taskpane/taskpane.ts
/* global document, Office, Word */
declare global {
  interface Window {
    __job_id?: string;
    __trace_id?: string;
    __addin_email?: string;
    __bulletproofQueue?: any;
    DocOpsCore?: any;
    enqueueOperation?: (op: any) => string;
    processQueue?: () => Promise<void>;
    getQueueStats?: () => any;
    debugQueue?: () => void;
    plogSend?: (level: string, event: string, message?: string, data?: any) => Promise<boolean>;
  }
}
export {};
// ============================================================================
// CONFIGURATION
// ============================================================================
const BUNDLE_ID = (window as any).__BUNDLE_BUILD_ID || 'inline';
let ws: WebSocket | null = null;
// ============================================================================
// UTILITIES
// ============================================================================
function genId(): string {
  return Math.random().toString(36).slice(2, 8) + "-" + Date.now().toString(36).slice(-6);
}
function log(s: string) {
  const el = document.getElementById("log");
  if (el) el.textContent = (el.textContent || "") + s + "\n";
  try {
    console.log("[addin]", s);
  } catch {}
}
function showUI() {
  const sideload = document.getElementById("sideload-msg");
  if (sideload) sideload.style.display = "none";

  const body = document.getElementById("app-body");
  if (body) body.style.display = "flex";
}
function sLog(level: string, event: string, message?: string, data?: any){
  try {
    if (window.plogSend) {
      window.plogSend(level, event, message || '', data || {});
    } else if ((window as any).DocOpsCore?.plogSend) {
      (window as any).DocOpsCore.plogSend(level, event, message || '', data || {});
    }
  } catch {}
}
function kindOf(op: any): string {
  return String(op?.op || op?.kind || op?.type || '').toLowerCase();
}
// ============================================================================
// WEBSOCKET
// ============================================================================
async function connect(email: string) {
  try {
    await Office.onReady();
  } catch {}

  try {
    ws?.close();
  } catch {}
  ws = null;

  const enc = encodeURIComponent((email || "").trim().toLowerCase());
  const url = `wss://localhost:8001/ws/addin/user/${enc}/`;

  log(`[ws] connecting ${url}`);

  const sock = new WebSocket(url);
  ws = sock;

  sock.onopen = () => {
    log("WS open");
    sLog('info','ws.open','ok');
  };

  sock.onclose = () => {
    log("WS close");
    sLog('info','ws.close','ok');
  };

  sock.onerror = () => {
    log("WS error");
    sLog('error','ws.error','socket error');
  };

  sock.onmessage = (ev) => {
    handleWebSocketMessage(ev.data);
  };
}
async function handleWebSocketMessage(data: string) {
  let msg: any = null;
  try {
    msg = JSON.parse(data);
  } catch {
    log("parse fail");
    return;
  }

  // Extract trace/job IDs
  try {
    if (msg && typeof msg === 'object') {
      const jobIdRoot = (msg as any).jobId || (msg as any).job_id || null;
      const traceIdRoot = (msg as any).traceId || (msg as any).trace_id || null;

      let jobIdFromOp = null, traceIdFromOp = null;

      const opsArr = Array.isArray((msg as any).blocks) ? (msg as any).blocks :
        Array.isArray((msg as any).ops) ? (msg as any).ops : null;

      if (opsArr && opsArr.length) {
        const first = opsArr[0] || {};
        jobIdFromOp = (first as any).jobId || (first as any).job_id || null;
        traceIdFromOp = (first as any).traceId || (first as any).trace_id || null;
      }

      (window as any).__trace_id = traceIdRoot || traceIdFromOp || (window as any).__trace_id || null;
      (window as any).__job_id = jobIdRoot || jobIdFromOp || (window as any).__job_id || null;
    }
  } catch {}

  if (msg?.type === "hello") {
    log("hello group=" + (msg.group || ""));
    return;
  }

  if (msg?.type === "addin.block") {
    const jobId = (msg as any).jobId || (msg as any).job_id || null;
    const traceId = (msg as any).traceId || (msg as any).trace_id || null;

    const payload: any[] = Array.isArray((msg as any).blocks) ? (msg as any).blocks :
      Array.isArray((msg as any).ops) ? (msg as any).ops :
        (msg as any).block ? [(msg as any).block] :
          ((msg as any).kind || (msg as any).op) ? [msg as any] : [];

    sLog('info','bundle.version', String(BUNDLE_ID));
    sLog('info', 'ws.receive.batch', '', {
      jobId,
      count: payload.length,
      kinds: payload.map(kindOf)
    });

    if (!payload.length) {
      log("ts: empty batch");
      return;
    }

    // ========================================================================
    // DOCOPS CORE INTEGRATION
    // ========================================================================
    if (typeof window.enqueueOperation === 'function') {
      const enqueuedIds: string[] = [];

      for (const op of payload) {
        if (!op.__opId) op.__opId = genId();
        if (!op.jobId && !op.job_id) op.jobId = jobId;
        if (!op.traceId && !op.trace_id) op.traceId = traceId;

        const opId = window.enqueueOperation(op);
        enqueuedIds.push(opId);
      }

      sLog('info', 'queue.enqueued_batch', '', {
        count: enqueuedIds.length,
        ids: enqueuedIds
      });

      // Start processing
      if (typeof window.processQueue === 'function') {
        window.processQueue().catch((e: any) => {
          sLog('error', 'queue.process.fatal', String(e?.message || e));
        });
      }
    } else {
      log("ERROR: DocOps Core not loaded!");
      sLog('error', 'core.not_loaded', 'window.enqueueOperation not found');
    }

    return;
  }

  log("unknown message: " + JSON.stringify(Object.keys(msg || {})));
}
// ============================================================================
// INSERT HELLO (test command)
// ============================================================================
export async function run() {
  try {
    await Office.onReady();
    await Word.run(async (ctx) => {
      const p = ctx.document.body.insertParagraph("Hello from Add-in", Word.InsertLocation.end);
      await ctx.sync();
      log("[run] hello inserted");
    });
  } catch(e: any) {
    log("[run] error: " + (e?.message || e));
  }
}
// ============================================================================
// UI WIRING
// ============================================================================
let uiWired = false;
function wireUi() {
  if (uiWired) return;
  uiWired = true;
  const emailInput = document.getElementById("email-input") as HTMLInputElement | null;
  const connectBtn = document.getElementById("connect-btn") as HTMLButtonElement | null;
  const pushTestBtn = document.getElementById("push-test-btn") as HTMLButtonElement | null;
  const runBtn = document.getElementById("run") as HTMLButtonElement | null;
  log("[boot] wiring UI…");
  connectBtn?.addEventListener("click", () => {
    const email = (emailInput?.value || "").trim();
    (window as any).__addin_email = email;
    log(`[ui] connect click email="${email}"`);

    if (!email) {
      log("Укажите email");
      return;
    }

    connect(email);
  });
  pushTestBtn?.addEventListener("click", async () => {
    const email = (emailInput?.value || "").trim();
    log(`[ui] push-test click email="${email}"`);

    if (!email) {
      log("Укажите email");
      return;
    }

    const u = new URL("https://localhost:8001/api/addin/push-test/");
    u.searchParams.set("email", email);

    const r = await fetch(u.toString(), { credentials: "omit" });
    log("push-test status " + r.status);
  });
  runBtn?.addEventListener("click", async () => {
    log("[ui] insert-hello click");
    try {
      await run();
      log("[ui] hello done");
    } catch(e:any){
      log("[ui] hello error: " + (e?.message||e));
    }
  });
}
// ============================================================================
// BOOTSTRAP
// ============================================================================
(function boot() {
  document.addEventListener("DOMContentLoaded", () => {
    showUI();
    wireUi();
    log("[boot] DOMContentLoaded");
  });

  try {
    if (typeof Office !== "undefined" && typeof Office.onReady === "function") {
      Office.onReady((info) => {
        try {
          log(`[boot] Office.onReady host=${(info as any).host} platform=${(info as any).platform}`);
        } catch {
          log("[boot] Office.onReady");
        }

        showUI();
        wireUi();
      });
    }
  } catch {}

  // Error handling
  window.addEventListener("error", (e: ErrorEvent) => {
    const msg = String(e?.message || "");
    const file = (e as any)?.filename || "";

    if (/appsforoffice\.microsoft\.com/.test(file)) return;
    if (/Script error/.test(msg)) return;

    log("[window.error] " + msg);
  });

  window.addEventListener("unhandledrejection", (e: PromiseRejectionEvent) => {
    const reason: any = (e as any)?.reason;
    const msg = String((reason && (reason.message || reason)) || "unhandledrejection");

    log("[unhandledrejection] " + msg);
  });
})();