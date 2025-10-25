# macroops_app/schema.py

# v1: минимальный «конверт» задания; ops = массив addin.block
ADDIN_JOB_KIND = "addin.job"

def make_addin_job(ops, anchor=None, meta=None, job_id=None):
    return {
        "kind": ADDIN_JOB_KIND,
        "version": "v1",
        "ops": list(ops or []),         # каждый элемент — наш «addin.block» (dict)
        "anchor": (anchor or {"at": "end"}),   # будущие варианты: {"at":"bookmark","name":"..."} и т.п.
        "meta": (meta or {}),
        "id": job_id or None,
    }