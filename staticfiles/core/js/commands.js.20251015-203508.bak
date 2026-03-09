/* global Office, Word */
(function(){
  const API_BASE = ""; // тот же origin, где Django (например, https://localhost:8001)

  async function postJson(url, body) {
    const r = await fetch(url, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(body||{})
    });
    if (!r.ok) throw new Error("HTTP "+r.status);
    return await r.json();
  }

  async function claimNextForThisDoc() {
    const url = Office.context.document.url || "";
    const res = await postJson(`${API_BASE}/api/docs/next`, { url });
    return (res && res.job) ? res.job : null;
  }

  async function complete(jobId, ok, message) {
    try {
      await postJson(`${API_BASE}/api/jobs/${jobId}/complete`, { ok, message });
    } catch(_) {}
  }

  async function applyPayload(payload) {
    // Минимум: поддержим paragraph.insert (дальше можно вынести общую логику в docops_core.js)
    if (!payload) return;
    const blocks = Array.isArray(payload) ? payload
                  : (payload.blocks) ? payload.blocks
                  : (payload.block) ? [payload.block]
                  : [payload];

    for (const b of blocks) {
      const kind = String(b.kind || b.op || b.type || "").toLowerCase();
      if (kind === "paragraph.insert" && typeof b.text === "string") {
        await Word.run(async (ctx) => {
          const p = ctx.document.body.insertParagraph(String(b.text), Word.InsertLocation.end);
          try { p.style = b.style || "Normal"; } catch {}
          await ctx.sync();
        });
      } else {
        // если подключили /static/docops_core.js — делегируем:
        if (window.docops && typeof window.docops.handle === "function") {
          await window.docops.handle(b);
        }
      }
    }

    // сохранить
    await Word.run(async (ctx) => { ctx.document.save(); await ctx.sync(); });
  }

  async function processOnce() {
    const job = await claimNextForThisDoc();
    if (!job) return false;
    try {
      await applyPayload(job.payload);
      await complete(job.id, true, "ok");
    } catch (e) {
      await complete(job.id, false, String(e && e.message || e));
    }
    return true;
  }

  async function backgroundLoop() {
    // Небольшой «джиттер», чтобы не долбить сервер
    const sleep = (ms)=>new Promise(r=>setTimeout(r,ms));
    while (true) {
      try {
        const done = await processOnce();
        await sleep(done ? 400 : 1200);
      } catch(_) {
        await sleep(2000);
      }
    }
  }

  // Фоновая активация
  Office.onReady(async () => { /* NOP */ });

  // ВАЖНО: имя функции должно совпадать с манифестом
  window.onDocOpen = function(event){
    // стартуем фоновый поллинг, завершение события сразу
    try { backgroundLoop(); } catch {}
    try { event.completed(); } catch {}
  };
})();