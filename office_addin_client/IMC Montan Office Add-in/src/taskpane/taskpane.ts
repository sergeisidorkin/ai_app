// src/taskpane/taskpane.ts
/* global document, Office, Word */

// Делаем файл модулем, чтобы не было конфликтов глобальных деклараций
export {};

let ws: WebSocket | null = null;

// ── Глобальная сериализация Word.run ─────────────────────────────────────────
let __wordRunTail: Promise<any> = Promise.resolve();

// Установим сериализацию как можно раньше
installWordRunSerializer();

async function installWordRunSerializer() {
  // ждём готовность Office.js один раз
  try { await Office.onReady(); } catch {}
  const anyWord: any = (window as any).Word;
  if (!anyWord || typeof anyWord.run !== "function") return;
  if (anyWord.run.__serialPatched) return;

  const origRun = anyWord.run.bind(anyWord);
  anyWord.run = function serialWordRun(fn: any) {
    // Каждую новую задачу линкуем в хвост цепочки
    __wordRunTail = __wordRunTail.then(() => origRun(fn));
    return __wordRunTail;
  };
  anyWord.run.__serialPatched = true;
}

// Дождаться, пока очередь Word.run опустеет (на случай,
// если inline-handler не возвращает промис из Word.run)
async function waitWordIdle() {
  try { await __wordRunTail; } catch { /* проглатываем */ }
}

let wsQueue: Promise<void> = Promise.resolve();

function enqueueWS(task: () => Promise<void>): Promise<void> {
  wsQueue = wsQueue.then(task).catch((e) => {
    log("[ws.queue] " + (e?.message || e));
  });
  return wsQueue;
}

function log(s: string) {
  const el = document.getElementById("log");
  if (el) el.textContent = (el.textContent || "") + s + "\n";
  try { console.log("[addin]", s); } catch {}
}

function showUI() {
  const sideload = document.getElementById("sideload-msg");
  if (sideload) sideload.style.display = "none";
  const body = document.getElementById("app-body");
  if (body) body.style.display = "flex";
}

// Общая очередь, чтобы Word.run не вызывался параллельно
let wordQueue: Promise<void> = Promise.resolve();
function enqueueWord(task: () => Promise<void>): Promise<void> {
  wordQueue = wordQueue.then(task).catch((e) => {
    try { log(`[Word.queue] task error: ${e?.message || e}`); } catch {}
  });
  return wordQueue;
}

/** ВСТАВКА: один параграф простого текста (с onReady и сериализацией) */
async function insertParagraph(text: string, styleBuiltIn: string = "Normal") {
  const safeText = (text ?? "").toString();
  if (!safeText) return;
  await Office.onReady();
  await enqueueWord(async () => {
    await Word.run(async (ctx) => {
      const p = ctx.document.body.insertParagraph(safeText, Word.InsertLocation.end);
      try {
        // @ts-ignore
        p.styleBuiltIn = styleBuiltIn as any;
      } catch {}
      await ctx.sync();
    });
  });
}

/** ВСТАВКА: несколько параграфов */
async function insertParagraphs(lines: string[], styleBuiltIn: string = "Normal") {
  for (const line of lines) {
    await insertParagraph(line, styleBuiltIn);
  }
}

async function applyStyleSafe(ctx: Word.RequestContext, p: Word.Paragraph, preferredName: string) {
  try { (p as any).style = preferredName; } catch {}
  try { await ctx.sync(); } catch {
    try { (p as any).styleBuiltIn = "ListBullet" as any; } catch {}
    try { await ctx.sync(); } catch {}
  }
}

function sendAck(jobId: string | null, traceId: string | null, appliedOps: number, anchorFound: boolean, selectionMoved: boolean) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  const msg: any = { type: "addin.ack", appliedOps, anchorFound: !!anchorFound, selectionMoved: !!selectionMoved };
  if (jobId)   msg.jobId = jobId;
  if (traceId) msg.traceId = traceId;
  try { ws.send(JSON.stringify(msg)); } catch {}
}

function countAppliedOps(ops: any[]): number {
  let n = 0;
  for (const op of (ops || [])) {
    const k = String(op?.op || op?.kind || op?.type || '').toLowerCase();
    if (k === 'paragraph.insert' && isAnchorOp(op)) continue; // якорь не считаем вставкой
    if (k === 'list.start' || k === 'list.end') continue;     // структура
    n += 1;
  }
  return n;
}

// ─────────────────────────────────────────────────────────────────────────────
// Fallback-нормализация DocOps → примитивные параграфы
// Используется ТОЛЬКО если НЕТ инлайн-обработчика window.docops.handle
// ─────────────────────────────────────────────────────────────────────────────
type AddinParagraph = { type: "paragraph"; text: string; styleBuiltIn?: string };

// Инлайн-обработчик активен, если есть функция либо современная (docops.handle), либо легаси (handleAddinBlockOp)

// Выбираем инлайн-хендлер: сперва новый __addin_handle, затем legacy, затем docops.handle
type InlineHandler = (b: any) => Promise<any> | any;

function pickInlineHandler(): InlineHandler | null {
  const w = window as any;
  try { if (typeof w.__addin_handle === "function") return w.__addin_handle.bind(w); } catch {}
  try { if (w.docops && typeof w.docops.handle === "function") return w.docops.handle.bind(w.docops); } catch {}
  return null;
}

// Флаг наличия инлайн-хендлера
function hasInlineHandler(): boolean {
  return !!pickInlineHandler();
}

// Последовательная прокси-очередь в inline-handler
let inlineQueue: Promise<void> = Promise.resolve();

function forwardToInline(blocks: any[], handler: (b: any) => Promise<any> | any): Promise<void> {
  for (const b of (blocks || [])) {
    inlineQueue = inlineQueue
      .then(async () => {
        // защита: Office.onReady + сериализатор уже стоит
        try { await Office.onReady(); } catch {}
        // вызываем inline-handler
        await Promise.resolve(handler(b));
        // и ОБЯЗАТЕЛЬНО ждём, пока все вложенные Word.run из него доработают
        await waitWordIdle();
      })
      .catch((e) => { try { log(`[inline.err] ${e?.message || e}`); } catch {} });
  }
  return inlineQueue;
}

function normalizeDocops(b: any): AddinParagraph[] {
  if (!b || typeof b !== "object") return [];

  const kind = (b.kind || b.op || b.type);

  if (kind === "paragraph.insert") {
    return [{ type: "paragraph", text: String(b.text || ""), styleBuiltIn: b.styleBuiltIn || "Normal" }];
  }

  if (kind === "list.item") {
    const line = "• " + String(b.text || "").trim();
    return [{ type: "paragraph", text: line, styleBuiltIn: "Normal" }];
  }

  if (b.type === "heading") {
    return [{ type: "paragraph", text: String(b.text || ""), styleBuiltIn: "Heading2" }];
  }

  if (b.type === "paragraph") {
    return [{ type: "paragraph", text: String(b.text || ""), styleBuiltIn: b.styleBuiltIn || "Normal" }];
  }

  return [];
}

async function applyBlock(block: AddinParagraph) {
  if (!block || typeof block !== "object") return;
  const txt = (block.text ?? "").toString();

  if (/\r?\n/.test(txt)) {
    const lines = txt.split(/\r?\n/).filter(Boolean);
    await insertParagraphs(lines, block.styleBuiltIn || "Normal");
    return;
  }

  await insertParagraph(txt, block.styleBuiltIn || "Normal");
}

// ─────────────────────────────────────────────────────────────────────────────
// WebSocket
// ─────────────────────────────────────────────────────────────────────────────

// --- Dedup с окном времени ---
const WS_DEDUP_WINDOW_MS = 15000;
const seen = new Map<string, number>();

function opSig(op: any): string {
  const k = String(op?.op || op?.kind || op?.type || '').toLowerCase();
  const t = String(op?.text || '').replace(/\s+/g, ' ').trim();
  return `${k}|${t}`;
}
function isAnchorText(t: string): boolean {
  return /^\s*</.test((t || '').trim());
}
function isAnchorOp(op: any): boolean {
  const k = String(op?.op || op?.kind || op?.type || '').toLowerCase();
  const t = String(op?.text || '');
  return (k === 'paragraph.insert' || k === 'paragraph') && isAnchorText(t);
}
function seenOrRememberTTL(sig: string): boolean {
  const now = Date.now();
  const last = seen.get(sig) || 0;
  seen.set(sig, now);

  // зачистка старых записей без for..of
  seen.forEach((ts, key) => {
    if (now - ts > WS_DEDUP_WINDOW_MS) seen.delete(key);
  });

  // true → считаем дублем только в окне времени
  return last > 0 && (now - last) < WS_DEDUP_WINDOW_MS;
}


type ListAcc = { active: boolean; items: string[]; styleName: string };
const listAcc: ListAcc = { active: false, items: [], styleName: "Маркированный список" };

async function flushListTS() {
  if (!listAcc.active || listAcc.items.length === 0) {
    listAcc.active = false; listAcc.items = [];
    return;
  }
  const items = [...listAcc.items];
  listAcc.active = false; listAcc.items = [];

  await Word.run(async (ctx) => {
    const body = ctx.document.body;

    // 1) первый пункт → стартуем список и синкаем сразу
    let p = body.insertParagraph(items[0] || "", Word.InsertLocation.end);
    p.startNewList();
    await ctx.sync();                               // критично на Mac
    await applyStyleSafe(ctx, p, listAcc.styleName);

    // 2) остальные пункты — ПОСЛЕ предыдущего (Word продолжит список)
    for (let i = 1; i < items.length; i++) {
      p = p.insertParagraph(items[i] || "", Word.InsertLocation.after);
      await applyStyleSafe(ctx, p, listAcc.styleName);
    }
  });
}



async function connect(email: string) {
  try { await Office.onReady(); } catch {}
  try { ws?.close(); } catch {}
  ws = null;

  const enc = encodeURIComponent((email || "").trim().toLowerCase());
  const url = `wss://localhost:8001/ws/addin/user/${enc}/`;
  log(`[ws] connecting ${url}`);

  const sock = new WebSocket(url);
  ws = sock;

  sock.onopen  = () => log("WS open");
  sock.onclose = () => log("WS close");
  sock.onerror = (ev) => log("WS error");

  sock.onmessage = async (ev) => {
      let msg: any = null;
      try { msg = JSON.parse(ev.data); } catch { log("parse fail"); return; }

      if (msg?.type === "hello") {
        log("hello group=" + (msg.group || ""));
        return;
      }

      if (msg?.type === "addin.block") {
          const jobId   = (msg as any).jobId || null;
          const traceId = (msg as any).traceId || null;
          const prevSel = !!(window as any).__addin_use_selection;
          const payload: any[] = Array.isArray(msg.blocks) ? msg.blocks
              : msg.block ? [msg.block]
                  : (msg.kind || msg.op) ? [msg] : [];

          // дедуп одинаковых операций
          const filtered: any[] = [];
          for (const op of payload) {
              const sig = opSig(op);
              if (!isAnchorOp(op) && seenOrRememberTTL(sig)) {
                log(`ts: dedup skip op ${sig}`);
                continue;
              }
              filtered.push(op);
          }
          if (!filtered.length) {
              log("ts: dedup all ops — nothing to apply");
              return;
          }


          // === ВЕРНУТЬ handler и проверку ===
          const handler = pickInlineHandler();
          const inlineActive = !!handler;
          log(`ts: got addin.block (inlineActive=${inlineActive})`);

          if (inlineActive) {
              log("ts: forward addin.block → inline handler");

              await forwardToInline(filtered, handler!);
              // ACK (после inline) — приблизительный appliedOps без якоря
              const appliedOps = countAppliedOps(filtered);
              const nowSel = !!(window as any).__addin_use_selection;
              sendAck(jobId, traceId, appliedOps, /*anchorFound*/ (nowSel && filtered.some(isAnchorOp)), /*selectionMoved*/ (!prevSel && nowSel));
              return; // ранний выход сохраняем
          }

          // ==== ФОЛБЭК: когда инлайн-хендлера нет ====
          for (const op of filtered) {
              const kind = String(op?.op || op?.kind || op?.type || "").toLowerCase();
              const text = String(op?.text || "");

              if (kind === "list.start") {
                listAcc.active = true;
                listAcc.items = [];
                listAcc.styleName = op?.styleName || op?.styleNameHint || "Маркированный список";
                continue;
              }
              if (kind === "list.item") {
                listAcc.items.push(text.trim());
                continue;
              }
              if (kind === "list.end") {
                await flushListTS();
                continue;
              }

              // любой абзац/другой блок → сначала закрываем список (если он был)
              await flushListTS();

              if (kind === "paragraph.insert" || kind === "paragraph") {
                  if (isAnchorText(text)) {
                    try {
                      const go: any = (window as any).gotoAnchor;
                      if (typeof go === "function") {
                        const found = await go(text);
                        (window as any).__addin_use_selection = !!found; // важно для ACK
                      }
                    } catch {}
                    continue;
                  }

                  // 2) Обычный абзац — как раньше
                  await Word.run(async (ctx) => {
                    ctx.document.body.insertParagraph(text, Word.InsertLocation.end);
                    await ctx.sync();
                  });
              }
          }
          // после цикла — на всякий случай дожмём хвост списка
          await flushListTS();
          const appliedOps = countAppliedOps(filtered);
          const nowSel = !!(window as any).__addin_use_selection;
          sendAck(jobId, traceId, appliedOps, /*anchorFound*/ (nowSel && filtered.some(isAnchorOp)), /*selectionMoved*/ (!prevSel && nowSel));
      }

      // Примитивы — как раньше
      if (msg?.type === "paragraph" || msg?.type === "heading") {
        const b = {
          type: "paragraph",
          text: String(msg.text || ""),
          styleBuiltIn: msg.type === "heading" ? "Heading2" : (msg.styleBuiltIn || "Normal"),
        };
        // разбивка по строкам внутри insertParagraphs
        const txt = (b.text ?? "").toString();
        if (/\r?\n/.test(txt)) {
          await insertParagraphs(txt.split(/\r?\n/).filter(Boolean), b.styleBuiltIn || "Normal");
        } else {
          await insertParagraph(txt, b.styleBuiltIn || "Normal");
        }
        return;
      }

      log("unknown message: " + JSON.stringify(Object.keys(msg || {})));
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Команда «Insert Hello» для кнопки
// ─────────────────────────────────────────────────────────────────────────────
export async function run() {
  await insertParagraph("Hello from Add-in", "Normal");
}

// ─────────────────────────────────────────────────────────────────────────────
// Привязка UI + корректный Office.onReady без явной аннотации типов
// ─────────────────────────────────────────────────────────────────────────────
let uiWired = false;

function wireUi() {
  if (uiWired) return;
  uiWired = true;
  const emailInput  = document.getElementById("email-input")  as HTMLInputElement | null;
  const connectBtn  = document.getElementById("connect-btn")  as HTMLButtonElement | null;
  const pushTestBtn = document.getElementById("push-test-btn") as HTMLButtonElement | null;
  const runBtn      = document.getElementById("run") as HTMLButtonElement | null;

  log("[boot] wiring UI… found: " + JSON.stringify({
    email: !!emailInput, connect: !!connectBtn, push: !!pushTestBtn, run: !!runBtn
  }));

  connectBtn?.addEventListener("click", () => {
    const email = (emailInput?.value || "").trim();
    log(`[ui] connect click email="${email}"`);
    if (!email) { log("Укажите email"); return; }
    connect(email);
  });

  pushTestBtn?.addEventListener("click", async () => {
    const email = (emailInput?.value || "").trim();
    log(`[ui] push-test click email="${email}"`);
    if (!email) { log("Укажите email"); return; }
    const u = new URL("https://localhost:8001/api/addin/push-test/");
    u.searchParams.set("email", email);
    const r = await fetch(u.toString(), { credentials: "omit" });
    log("push-test status " + r.status);
  });

  runBtn?.addEventListener("click", async () => {
    log("[ui] insert-hello click");
    try { await insertParagraph("Hello from Add-in", "Normal"); log("[ui] hello done"); }
    catch(e:any){ log("[ui] hello error: " + (e?.message||e)); }
  });
}

// Двойной бутстрап: DOMContentLoaded и Office.onReady
(function boot() {
  document.addEventListener("DOMContentLoaded", () => {
    showUI();
    wireUi();
    log("[boot] DOMContentLoaded");
  });

  try {
    // ВАЖНО: без явной аннотации — совместимо с версией ваших d.ts
    if (typeof Office !== "undefined" && typeof Office.onReady === "function") {
      Office.onReady((info) => {
        try { log(`[boot] Office.onReady host=${(info as any).host} platform=${(info as any).platform}`); }
        catch { log("[boot] Office.onReady"); }
        showUI();
        wireUi();
      });
    }
  } catch {
    // no-op
  }

  // Диагностика в рантайме (фильтруем шум от Office.js CDN)
  function isThirdPartyFile(name: string | undefined): boolean {
    if (!name) return false;
    try {
      const u = new URL(name, location.href);
      return u.origin !== location.origin;
    } catch {
      return false;
    }
  }

  const OFFICE_CDN_RE = /appsforoffice\.microsoft\.com\/lib\/.*\/hosted\/word/i;
  const IGNORE_MSG_RE = /Attempting to change the getter of an unconfigurable property/i;

  window.addEventListener("error", (e: ErrorEvent) => {
    const msg = String(e?.message || "");
    const file = (e as any)?.filename || "";

    // Игнорируем известный шум от Office.js (Mac Word) и любые кросс-доменные "Script error."
    if (IGNORE_MSG_RE.test(msg)) return;
    if (OFFICE_CDN_RE.test(file)) return;
    if (isThirdPartyFile(file) && msg === "Script error.") return;

    try { console.error("[window.error]", msg, "@", file, ":", (e as any).lineno); } catch {}
    log("[window.error] " + msg);
  });

  window.addEventListener("unhandledrejection", (e: PromiseRejectionEvent) => {
    const reason: any = (e as any)?.reason;
    const msg = String((reason && (reason.message || reason)) || "unhandledrejection");

    // На всякий случай те же фильтры
    if (IGNORE_MSG_RE.test(msg)) return;

    try { console.error("[unhandledrejection]", reason); } catch {}
    log("[unhandledrejection] " + msg);
  });

  // Поставь это в консоли один раз на сессию:
  window.addEventListener('error',  e => {
      console.log('[diag.window.error]', e.message, '@', e.filename, e.lineno+':'+e.colno, e.error?.stack||'');
  }, true);
  window.addEventListener('unhandledrejection', e => {
      console.log('[diag.unhandled]', e.reason);
  });
  console.log('[diag] error hooks armed');
})();