const tabs = document.querySelectorAll(".tab");
const panels = {
  profile: document.getElementById("tab-profile"),
  single: document.getElementById("tab-single"),
};
const singleForm = document.getElementById("single-form");
const singleButton = document.getElementById("single-button");
const singleResult = document.getElementById("single-result");
const qualityPreference = document.getElementById("quality-preference");
const downloadSelectedButton = document.getElementById("download-selected-button");
const resultCard = document.getElementById("result-card");
const caseSummary = document.getElementById("case-summary");
const uploadResult = document.getElementById("upload-result");
const buildCaseButton = document.getElementById("build-case-button");
const jobCard = document.getElementById("job-card");
const progressBar = document.getElementById("progress-bar");
const jobMessage = document.getElementById("job-message");
const jobResult = document.getElementById("job-result");

let currentLocalVideoId = "";
let currentAwemeId = "";
let selectedCandidate = null;

function showTab(name) {
  tabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === name));
  Object.entries(panels).forEach(([key, panel]) => {
    panel.classList.toggle("hidden", key !== name);
  });
}

function showJson(element, payload) {
  element.textContent = JSON.stringify(payload, null, 2);
}

function renderWorkflowResult(result) {
  const caseInfo = result.case || {};
  const downloadInfo = result.download || {};
  const caseId = result.case_id || caseInfo.case_id || "";
  const rows = [
    ["素材包 ID", caseId ? `<a class="text-link" href="/cases/${caseId}" target="_blank">${caseId}</a>` : ""],
    ["视频文件", caseInfo.video_path || downloadInfo.file_path || ""],
    ["分析输入", result.analysis_input_path || caseInfo.analysis_input_path || ""],
    ["Prompt 模板", result.prompt_path || caseInfo.prompt_path || ""],
    ["关键帧总览", result.contact_sheet_path || caseInfo.contact_sheet_path || ""],
    ["关键帧目录", result.keyframes_dir || caseInfo.keyframes_dir || ""],
  ].filter(([, value]) => value);

  caseSummary.innerHTML = `
    <div class="case-status">素材包已生成</div>
    ${caseId ? `<p><a class="text-link" href="/cases/${caseId}" target="_blank">打开分析视图</a></p>` : ""}
    <dl>
      ${rows.map(([label, value]) => `<dt>${label}</dt><dd>${value}</dd>`).join("")}
    </dl>
  `;
  showJson(uploadResult, result);
}

function getCaseId(result) {
  const caseInfo = result.case || {};
  return result.case_id || caseInfo.case_id || "";
}

function openAnalysisView(result) {
  const caseId = getCaseId(result);
  if (!caseId) {
    return false;
  }
  jobResult.textContent = "";
  jobMessage.textContent = "素材包已生成，正在打开分析视图...";
  window.location.replace(`/cases/${caseId}`);
  return true;
}

async function readJsonResponse(response) {
  const payload = await response.json().catch(() => ({
    ok: false,
    error_code: "INVALID_RESPONSE",
    message: "接口返回不是 JSON。",
  }));
  if (!response.ok || payload.ok === false) {
    throw payload;
  }
  return payload;
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => showTab(tab.dataset.tab));
});

singleForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  singleButton.disabled = true;
  singleButton.textContent = "导入中...";
  selectedCandidate = null;
  downloadSelectedButton.hidden = true;
  try {
    const value = new FormData(singleForm).get("value");
    const importResponse = await fetch("/api/videos/import-single", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({value}),
    });
    const imported = await readJsonResponse(importResponse);
    currentAwemeId = imported.video.aweme_id;
    singleResult.classList.remove("hidden");
    singleResult.textContent = `已导入作品：${currentAwemeId}，正在解析可用清晰度...`;
    await resolveQualities([currentAwemeId]);
  } catch (error) {
    singleResult.classList.remove("hidden");
    singleResult.textContent = `${error.error_code || "ERROR"}：${error.message || "导入失败"}`;
  } finally {
    singleButton.disabled = false;
    singleButton.textContent = "导入作品";
  }
});

async function resolveQualities(awemeIds) {
  const response = await fetch("/api/videos/qualities", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({aweme_ids: awemeIds}),
  });
  const payload = await readJsonResponse(response);
  const candidates = payload.results[currentAwemeId] || [];
  if (!candidates.length) {
    singleResult.textContent = "没有解析到可用清晰度候选。";
    return;
  }
  selectedCandidate = chooseCandidate(candidates);
  const sizeMb = selectedCandidate.size_bytes
    ? (selectedCandidate.size_bytes / 1024 / 1024).toFixed(2)
    : "未知";
  const bitrate = selectedCandidate.bitrate
    ? `${Math.round(selectedCandidate.bitrate / 1000)} kbps`
    : "未知码率";
  singleResult.textContent = `已按设置选择：${selectedCandidate.quality_label || "网页候选"} · ${sizeMb} MB · ${bitrate}`;
  downloadSelectedButton.hidden = false;
}

function chooseCandidate(candidates) {
  const preference = qualityPreference.value;
  if (preference === "1080") {
    return candidates.find((candidate) => String(candidate.quality_label || "").includes("1080")) || candidates[0];
  }
  if (preference === "720") {
    return candidates.find((candidate) => String(candidate.quality_label || "").includes("720")) || candidates[0];
  }
  return candidates[0];
}

async function downloadCandidate(candidate) {
  jobCard.classList.remove("hidden");
  progressBar.style.width = "0%";
  jobMessage.className = "job-message";
  jobMessage.textContent = "创建下载、素材包和自动拆解任务...";
  jobResult.textContent = "";
  caseSummary.innerHTML = "";
  resultCard.classList.add("hidden");
  buildCaseButton.hidden = true;
  try {
    const response = await fetch("/api/jobs/download-build-analyze-case", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({aweme_id: currentAwemeId, candidate_id: candidate.candidate_id}),
    });
    const payload = await readJsonResponse(response);
    pollJob(payload.job_id, (job) => {
      if (job.status === "success" && job.result_json.local_video_id) {
        currentLocalVideoId = job.result_json.local_video_id;
        if (openAnalysisView(job.result_json)) {
          return;
        }
        resultCard.classList.remove("hidden");
        buildCaseButton.hidden = true;
        renderWorkflowResult(job.result_json);
      }
    });
  } catch (error) {
    jobMessage.className = "job-message failed";
    jobMessage.textContent = `${error.error_code || "ERROR"}：${error.message || "任务创建失败"}`;
  }
}

downloadSelectedButton.addEventListener("click", () => {
  if (selectedCandidate) {
    downloadCandidate(selectedCandidate);
  }
});

buildCaseButton.addEventListener("click", async () => {
  if (!currentLocalVideoId) {
    return;
  }
  buildCaseButton.disabled = true;
  jobCard.classList.remove("hidden");
  progressBar.style.width = "0%";
  jobMessage.className = "job-message";
  jobMessage.textContent = "创建任务...";
  jobResult.textContent = "";
  try {
    const response = await fetch("/api/jobs/build-case", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({local_video_id: currentLocalVideoId}),
    });
    const payload = await readJsonResponse(response);
    pollJob(payload.job_id);
  } catch (error) {
    jobMessage.className = "job-message failed";
    jobMessage.textContent = `${error.error_code || "ERROR"}：${error.message || "任务创建失败"}`;
    buildCaseButton.disabled = false;
  }
});

async function pollJob(jobId, onSuccess) {
  try {
    const response = await fetch(`/api/jobs/${jobId}`, {cache: "no-store"});
    const payload = await readJsonResponse(response);
    const job = payload.job;
    progressBar.style.width = `${job.progress || 0}%`;
    jobMessage.textContent = `${job.status} · ${job.progress}% · ${job.message || ""}`;
    if (job.status === "success") {
      jobMessage.className = "job-message success";
      if (onSuccess) {
        onSuccess(job);
      } else {
        showJson(jobResult, job.result_json);
      }
      buildCaseButton.disabled = false;
      return;
    }
    if (job.status === "failed") {
      jobMessage.className = "job-message failed";
      jobMessage.textContent = `${job.error_code || "ERROR"}：${job.message || "任务失败"}`;
      showJson(jobResult, job);
      buildCaseButton.disabled = false;
      return;
    }
    window.setTimeout(() => pollJob(jobId, onSuccess), 700);
  } catch (error) {
    jobMessage.className = "job-message failed";
    jobMessage.textContent = `${error.error_code || "ERROR"}：${error.message || "查询任务失败"}`;
    buildCaseButton.disabled = false;
  }
}
