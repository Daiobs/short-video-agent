from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import settings
from app.errors import AppError
from app.routes.settings import LLMSettingsUpdate
from app.services import runtime_settings
from app.services.llm_settings import update_llm_settings_payload


def test_long_creator_settings_save_and_manual_override():
    saved = update_llm_settings_payload({
        "creator_distill_budget_mode": "auto",
        "creator_distill_request_timeout_seconds": 1200,
        "final_reduce_timeout_seconds": 2400,
        "quick_distill_budget_seconds": 1800,
        "deep_distill_budget_seconds": 3600,
        "batch_job_budget_seconds": 14400,
    })
    assert saved["creator_distill_budget_mode"] == "auto"
    assert saved["creator_distill_request_timeout_seconds"] == 1200
    assert saved["batch_job_budget_seconds"] == 14400
    short = update_llm_settings_payload({
        "creator_distill_budget_mode": "manual",
        "creator_distill_request_timeout_seconds": 90,
        "quick_distill_budget_seconds": 120,
    })
    assert short["creator_distill_request_timeout_seconds"] == 90
    assert short["quick_distill_budget_seconds"] == 120
    assert runtime_settings.effective_llm_settings()["creator_distill_budget_mode"] == "manual"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 1201])
def test_invalid_timing_save_does_not_partially_write(value):
    update_llm_settings_payload({"creator_distill_budget_mode": "auto"})
    before = runtime_settings.LOCAL_SETTINGS_PATH.read_bytes()
    with pytest.raises(AppError):
        update_llm_settings_payload({"model": "must-not-save", "creator_distill_request_timeout_seconds": value})
    assert runtime_settings.LOCAL_SETTINGS_PATH.read_bytes() == before


def test_mode_crosschecks_and_route_limits():
    LLMSettingsUpdate(creator_distill_request_timeout_seconds=1200, final_reduce_timeout_seconds=2400,
                      quick_distill_budget_seconds=14400, creator_distill_budget_mode="auto")
    for fields in ({"timeout_seconds": 301}, {"creator_distill_budget_mode": "other"},
                   {"final_reduce_timeout_seconds": 2401}, {"quick_distill_budget_seconds": float("inf")}):
        with pytest.raises(ValidationError):
            LLMSettingsUpdate(**fields)
    with pytest.raises(AppError):
        update_llm_settings_payload({"creator_distill_budget_mode": "manual",
                                     "creator_distill_request_timeout_seconds": 400,
                                     "quick_distill_budget_seconds": 300})
    assert not runtime_settings.LOCAL_SETTINGS_PATH.exists()
    # Auto cap may be lower than a planned request: execution must report insufficient
    # budget instead of pretending that this explicit cap is an enlarged request.
    result = update_llm_settings_payload({"creator_distill_budget_mode": "auto",
                                         "creator_distill_request_timeout_seconds": 400,
                                         "quick_distill_budget_seconds": 300})
    assert result["quick_distill_budget_seconds"] == 300


def test_legacy_defaults_upgrade_without_rewriting_and_explicit_caps_remain(monkeypatch):
    monkeypatch.setattr(settings, "llm_quick_distill_budget_seconds", 1800)
    monkeypatch.setattr(settings, "llm_deep_distill_budget_seconds", 3600)
    monkeypatch.setattr(settings, "llm_batch_job_budget_seconds", 7200)
    runtime_settings.update_local_section("llm", {
        "quick_distill_budget_seconds": 240, "deep_distill_budget_seconds": 600,
        "batch_job_budget_seconds": 600,
    })
    before = runtime_settings.LOCAL_SETTINGS_PATH.read_bytes()
    effective = runtime_settings.effective_llm_settings()
    assert [effective[key] for key in ("quick_distill_budget_seconds", "deep_distill_budget_seconds", "batch_job_budget_seconds")] == [1800, 3600, 7200]
    assert runtime_settings.LOCAL_SETTINGS_PATH.read_bytes() == before
    runtime_settings.update_local_section("llm", {"batch_job_budget_seconds": 1200})
    assert runtime_settings.effective_llm_settings()["batch_job_budget_seconds"] == 1200
    runtime_settings.update_local_section("llm", {"creator_distill_budget_mode": "auto"})
    assert runtime_settings.effective_llm_settings()["quick_distill_budget_seconds"] == 240
    runtime_settings.update_local_section("llm", {"creator_distill_budget_mode": "manual"})
    assert runtime_settings.effective_llm_settings()["deep_distill_budget_seconds"] == 600


@pytest.mark.parametrize("key,value", [
    ("creator_distill_request_timeout_seconds", float("inf")),
    ("final_reduce_timeout_seconds", float("nan")),
    ("quick_distill_budget_seconds", 14401),
    ("deep_distill_budget_seconds", -10),
    ("batch_job_budget_seconds", float("inf")),
    ("final_reduce_min_reserve_seconds", 601),
    ("compact_retry_min_remaining_seconds", 0),
])
@pytest.mark.parametrize("source", ["environment", "local"])
def test_creator_persisted_timing_is_finite_and_bounded(monkeypatch, key, value, source):
    if source == "environment":
        monkeypatch.setattr(settings, "llm_" + key, value)
    else:
        runtime_settings.update_local_section("llm", {key: value})
    before = runtime_settings.LOCAL_SETTINGS_PATH.read_bytes() if runtime_settings.LOCAL_SETTINGS_PATH.exists() else None
    with pytest.raises(AppError) as error:
        runtime_settings.effective_llm_settings()
    assert error.value.code == "LLM_SETTINGS_INVALID"
    after = runtime_settings.LOCAL_SETTINGS_PATH.read_bytes() if runtime_settings.LOCAL_SETTINGS_PATH.exists() else None
    assert after == before


NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node.js unavailable")
def test_settings_panel_renders_mode_and_saves_manual_budget():
    source = Path("app/static/modules/settings-panel.js").read_text()
    script = """
const vm = require('vm'); const context = {console}; context.window = context;
vm.runInNewContext(SOURCE, context);
function element() { return {value:'',innerHTML:'',listeners:{},classList:{toggle(){},add(){},remove(){}},
 addEventListener(name, callback){this.listeners[name]=callback;}}; }
const e = Object.fromEntries(['modal','llmForm','llmCreatorBudgetModeInput','llmCreatorDistillTimeoutInput',
 'llmStatusList','llmQuickDistillBudgetInput','llmDeepDistillBudgetInput','llmBatchJobBudgetInput'].map(k=>[k,element()]));
let posted;
const controller = context.SettingsPanel.init({elements:e,requestJson:async(url, options)=>{
 posted=JSON.parse(options.body);return {llm:posted};}});
controller.renderLlmStatus({creator_distill_budget_mode:'auto',creator_distill_request_timeout_seconds:345,
 quick_distill_budget_seconds:1800,deep_distill_budget_seconds:3600,batch_job_budget_seconds:7200});
const auto=e.llmStatusList.innerHTML;
e.llmCreatorBudgetModeInput.value='manual';e.llmCreatorDistillTimeoutInput.value='90';
(async()=>{await e.llmForm.listeners.submit({preventDefault(){}});
 process.stdout.write(JSON.stringify({auto,posted,manual:e.llmStatusList.innerHTML}));})();
""".replace("SOURCE", json.dumps(source))
    result = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True, timeout=15)
    data = json.loads(result.stdout)
    assert "基础等待" in data["auto"]
    assert data["posted"]["creator_distill_budget_mode"] == "manual"
    assert data["posted"]["creator_distill_request_timeout_seconds"] == 90
    assert "人工覆盖" in data["manual"]
    assert "请求上限" in data["manual"]


@pytest.mark.skipif(NODE is None, reason="Node.js unavailable")
def test_progress_displays_actual_phase_timeout_not_recommendation():
    source = Path("app/static/app.js").read_text()
    function = source[source.index("function renderJobPhase(job)"):source.index("function renderJobStatus(job,")]
    script = """
const vm = require('vm');
const jobPhase={innerHTML:'',classList:{add(){},remove(){}}};
const context={jobPhase,Date,formatNumber:String,escapeHtml:String,
 normalizeItems:(v)=>Array.isArray(v)?v:[],isMeaningfulReportText:(v)=>Boolean(v),formatReportValue:String};
vm.runInNewContext(SOURCE,context);
const phase={status:'running',current_phase:'llm_wait',timeout_seconds:345,total_budget_seconds:720,
 elapsed_seconds:281,remaining_seconds:439,execution_plan:{selected_count:5,timeout_policy:{
 budget_mode:'auto',recommended_batch_timeout_seconds:999}}};
context.renderJobPhase({status:'running',result_json:{distill_phase:phase}});
const html=jobPhase.innerHTML;
context.renderJobPhase({status:'running',result_json:{distill_phase:{...phase,
 timeout_seconds:90,execution_plan:{selected_count:5,timeout_policy:{budget_mode:'manual'}}}}});
const manual=jobPhase.innerHTML;
const waitingStates=[];
for (const current_phase of ['llm_wait','llm_retry','batch_reduce','final_reduce']) {
 for (const status of ['running','prompt_only','success','failed',undefined]) {
  context.renderJobPhase({status:'running',result_json:{distill_phase:{...phase,current_phase,status}}});
  waitingStates.push({current_phase,status:status ?? 'missing',waiting:jobPhase.innerHTML.includes('等待模型响应')});
 }
}
context.renderJobPhase({status:'success',result_json:{distill_phase:{...phase,current_phase:'final_reduce'}}});
process.stdout.write(JSON.stringify({html,manual,waitingStates,completedWaiting:jobPhase.innerHTML.includes('等待模型响应')}));
""".replace("SOURCE", json.dumps(function))
    result = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True, timeout=15)
    data = json.loads(result.stdout)
    assert "本次请求最多等待 345 秒" in data["html"]
    assert "总预算 720 秒" in data["html"]
    assert "已等待 281 秒" in data["html"]
    assert "已选 5 条样本" in data["html"]
    assert "等待模型响应" in data["html"]
    assert "本次请求最多等待 999 秒" not in data["html"]
    assert "人工覆盖" in data["manual"]
    assert "本次请求最多等待 90 秒" in data["manual"]
    for state in data["waitingStates"]:
        assert state["waiting"] is (state["status"] == "running"), state
    assert data["completedWaiting"] is False


@pytest.mark.skipif(NODE is None, reason="Node.js unavailable")
def test_creator_safe_recovery_observes_long_budget_but_rejects_expired_or_invalid():
    source = Path("app/static/app.js").read_text()
    helpers = source[source.index("function parseBackendJobTimestampMilliseconds"):source.index("function setActiveProfileBuildJob")]
    poll = source[source.index("async function pollCreatorCloneDistillJob"):source.index("function waitForCreatorCloneReportPaint")]
    script = """
const vm = require('vm');const now=Date.now();
const iso=(offset)=>new Date(now+offset*1000).toISOString();
const base={type:'creator-clone-batch-distill',status:'running',created_at:iso(-2500),updated_at:iso(-2400),
 result_json:{distill_phase:{budget_started_at:iso(-2400),deadline_at:iso(4800),total_budget_seconds:7200,remaining_seconds:4800}}};
const phase=base.result_json.distill_phase;
const context={Date,activeHomeRoute:'profile',activeProfileBuildJobUpdatedAt:'',activeProfileBuildJobStatus:'',
 WORKBENCH_TASK_STALE_SECONDS:1800,jobMessage:{},profileScanStatus:{},renderJobStatus(){},updateCreatorCloneSelectionStatus(){},
 window:{setTimeout(resolve){resolve();}}};
vm.runInNewContext(HELPERS+POLL,context);
const valid=context.hasActiveCreatorJobBudget(base,now);
const rejected=[{...phase,total_budget_seconds:Infinity},{...phase,total_budget_seconds:'7200'},
 {...phase,total_budget_seconds:14401},{...phase,remaining_seconds:0},{...phase,remaining_seconds:8000},
 {...phase,deadline_at:iso(-1)},{...phase,budget_started_at:'bad'},{...phase,deadline_at:iso(20000)}]
 .map(p=>context.hasActiveCreatorJobBudget({...base,result_json:{distill_phase:p}},now));
const single=context.hasActiveCreatorJobBudget({...base,type:'analyze-case'},now);
const pending=context.hasActiveCreatorJobBudget({...base,status:'pending'},now);
async function run(job){let calls=0;context.fetchWorkbenchJob=async()=>++calls===1?job:{status:'failed',message:'stopped'};
 const result=await context.pollCreatorCloneDistillJob('job_test',{safeStatus:true});return {calls,result};}
(async()=>{const live=await run(base);const expired=await run({...base,result_json:{distill_phase:{...phase,deadline_at:iso(-1)}}});
 const stale=await run({...base,status:'stale'});const missing=await run({...base,result_json:{}});
 process.stdout.write(JSON.stringify({valid,rejected,single,pending,live,expired,stale,missing}));})();
""".replace("HELPERS", json.dumps(helpers)).replace("POLL", json.dumps(poll))
    result = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True, timeout=15)
    data = json.loads(result.stdout)
    assert data["valid"] is True
    assert not any(data["rejected"])
    assert data["single"] is False
    assert data["pending"] is False
    assert data["live"]["calls"] == 2
    for key in ("expired", "stale", "missing"):
        assert data[key]["calls"] == 1
        assert data[key]["result"]["stale"] is True
