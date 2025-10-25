/* global Office, Word */
(function(){
  const API_BASE = ""; // тот же origin, где Django (например, https://localhost:8001)
  const MARKER_PREFIX = "DOCOPS_DONE:";

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
    try { await postJson(`${API_BASE}/api/jobs/${jobId}/complete`, { ok, message }); } catch(_) {}
  }

  function normalizeBlocks(payload){
    if (!payload) return [];
    if (Array.isArray(payload)) return payload;
    if (payload.blocks) return Array.isArray(payload.blocks) ? payload.blocks : [payload.blocks];
    if (payload.block)  return [payload.block];
    return [payload]; // fallback «как есть»
  }

  async function hasMarker(jobId){
    try{
      return await Word.run(async (ctx)=>{
        const r = ctx.document.body.getRange("Whole");
        r.load("text");
        await ctx.sync();
        const txt = r.text || "";
        return txt.indexOf(`${MARKER_PREFIX} ${jobId}`) >= 0;
      });
    }catch(_){ return false; }
  }

  // вставка ВСЕХ блоков + маркера за один Word.run + один save
  async function insertBlocksAndMarker(blocks, jobId){
    await Word.run(async (ctx)=>{
      const body = ctx.document.body;
      for (const b of blocks){
        const kind = String((b && (b.kind||b.op||b.type)) || "").toLowerCase();
        if (kind === "paragraph.insert" && typeof b.text === "string"){
          const p = body.insertParagraph(String(b.text), Word.InsertLocation.end);
          try { if (b.style) p.style = b.style; } catch(_){}
        } else if (window.docops && typeof window.docops.handle === "function"){
          // делегируем в общий обработчик, если подключён
          await window.docops.handle(b, ctx);
        } else {
          // минимальный fallback: вставим как текст
          body.insertParagraph(String(b && b.text || JSON.stringify(b)), Word.InsertLocation.end);
        }
      }
      body.insertParagraph(`${MARKER_PREFIX} ${jobId}`, Word.InsertLocation.end);
      await ctx.sync();
      ctx.document.save();
      await ctx.sync();
    });
  }

  // (необязательно) быстрый локальный пинок синхры OneDrive, если есть мост
  function tryBridgeSync(){
    try{
      if (window.chrome && chrome.webview && chrome.webview.hostObjects && chrome.webview.hostObjects.sync){
        chrome.webview.hostObjects.sync.PutUpdate();
        return true;
      }
    }catch(_){}
    return false;
  }

  let loopStarted = false;
  let inflight = false;

  async function processOnce() {
    if (inflight) return false;
    inflight = true;
    try{
      const job = await claimNextForThisDoc();
      if (!job){ return false; }

      const jobId = job.id;
      // идемпотентность: если маркер уже есть — завершаем без повторной вставки
      if (await hasMarker(jobId)){
        await complete(jobId, true, "already-present");
        return true;
      }

      const blocks = normalizeBlocks(job.payload);
      await insertBlocksAndMarker(blocks, jobId);
      tryBridgeSync();
      await complete(jobId, true, "insert+marker+1save");
      return true;
    }catch(e){
      // если что-то пошло не так, лучше завершить job как failed, чтобы не зациклиться
      try{
        const j = await claimNextForThisDoc(); // мог быть тот же
        if (j && j.id) await complete(j.id, false, String(e && e.message || e));
      }catch(_){}
      return false;
    }finally{
      inflight = false;
    }
  }

  async function backgroundLoop() {
    if (loopStarted) return; loopStarted = true;
    const sleep = (ms)=>new Promise(r=>setTimeout(r,ms));
    let idle = 0;
    while (true) {
      const done = await processOnce();
      if (done){ idle = 0; await sleep(600); }       // после удачной вставки — короткая пауза
      else      { idle = Math.min(idle+1, 4);
                  await sleep(idle<2 ? 800 : 1500); } // бэкофф в простое
    }
  }

  // Фоновая активация
  Office.onReady(async () => { /* NOP */ });

  // ВАЖНО: имя функции должно совпадать с манифестом
  window.onDocOpen = function(event){
    try { backgroundLoop(); } catch(_){}
    try { event.completed(); } catch(_){}
  };
})();