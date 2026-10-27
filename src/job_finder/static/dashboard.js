const state = { page: 1, pageSize: 10, total: 0, stats: null };
const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

function shortDate(value) {
  if (!value) return "Date unknown";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Date unknown" : date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function safeJobUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function relativeDate(value) {
  if (!value) return "Not yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not yet";
  const days = Math.max(0, Math.floor((Date.now() - date.getTime()) / 86400000));
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  return `${days} days ago`;
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
}

function queryString() {
  const params = new URLSearchParams({
    q: $("#query-input").value.trim(),
    page: String(state.page),
    page_size: String(state.pageSize),
  });
  const location = $("#location-input").value.trim();
  const source = $("#source-filter").value;
  const arrangement = $("#arrangement-filter").value;
  const status = $("#status-filter").value;
  if (location) params.set("location", location);
  if ($("#remote-input").checked) params.set("remote_only", "true");
  if (source) params.set("source", source);
  if (arrangement) params.set("work_arrangement", arrangement);
  if (status) params.set("status", status);
  return params;
}

async function loadStats() {
  const stats = await api("/api/stats");
  state.stats = stats;
  $("#total-jobs").textContent = stats.total_jobs.toLocaleString();
  $("#total-companies").textContent = stats.companies.toLocaleString();
  $("#remote-jobs").textContent = stats.remote_jobs.toLocaleString();
  $("#nav-job-count").textContent = stats.total_jobs > 99 ? "99+" : stats.total_jobs;
  const latest = stats.recent_runs[0];
  $("#last-run").textContent = latest ? relativeDate(latest.finished_at) : "Not yet";
  $("#last-run-detail").textContent = latest
    ? `${latest.jobs_extracted} roles found · ${latest.pages_fetched} pages checked`
    : "Start a crawl to find roles";

  const sourceSelect = $("#source-filter");
  const selected = sourceSelect.value;
  sourceSelect.innerHTML = '<option value="">All sources</option>' + Object.keys(stats.sources)
    .map((source) => `<option value="${escapeHtml(source)}">${escapeHtml(source.replaceAll("_", " "))}</option>`).join("");
  sourceSelect.value = selected;

  const cards = Object.entries(stats.sources);
  $("#source-cards").innerHTML = cards.length
    ? cards.map(([source, count], index) => `<article class="source-card"><span class="source-icon">${escapeHtml(source.slice(0, 1).toUpperCase())}</span><div><div class="source-name">${escapeHtml(source.replaceAll("_", " "))}</div><div class="source-total">${count} ${count === 1 ? "role" : "roles"}</div></div></article>`).join("")
    : '<div class="empty-state"><p>No sources yet. Run a discovery to get started.</p></div>';
}

function jobCard(result, index) {
  const job = result.job;
  const company = job.company || "Company not listed";
  const initials = company.trim().slice(0, 1).toUpperCase() || "?";
  const score = result.score == null ? "" : `<span class="score-chip">${Math.round(result.score)}% match</span>`;
  const tags = [
    job.work_arrangement !== "unknown" ? `<span class="job-tag remote">${escapeHtml(job.work_arrangement)}</span>` : "",
    job.employment_type !== "unknown" ? `<span class="job-tag">${escapeHtml(job.employment_type.replaceAll("_", " "))}</span>` : "",
    job.status === "active" ? '<span class="job-tag remote">Verified active</span>' : job.status === "expired" ? '<span class="job-tag">Expired</span>' : "",
    `<span class="job-tag">${escapeHtml(job.source.replaceAll("_", " "))}</span>`,
  ].filter(Boolean).join("");
  const reasons = result.reasons.length ? `<div class="job-match"><strong>Why it matches:</strong> ${escapeHtml(result.reasons.join(" · "))}</div>` : "";
  const location = job.location || "Location not listed";
  const url = safeJobUrl(job.url);
  return `<article class="job-card">
    <div class="company-mark tone-${index % 4}">${escapeHtml(initials)}</div>
    <div class="job-main">
      <div class="job-title-row"><h3 class="job-title">${escapeHtml(job.title)}</h3>${score}</div>
      <div class="job-company">${escapeHtml(company)}</div>
      <div class="job-meta"><span>⌖ ${escapeHtml(location)}</span><span>◷ Added ${escapeHtml(shortDate(job.discovered_at))}</span></div>
      <div class="job-tags">${tags}</div>${reasons}
    </div>
    <div class="job-actions"><span class="job-date">${escapeHtml(job.posting_date ? `Posted ${shortDate(job.posting_date)}` : `Found ${shortDate(job.discovered_at)}`)}</span>${url ? `<a class="job-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" aria-label="Open ${escapeHtml(job.title)} at ${escapeHtml(company)}">View role ↗</a>` : '<span class="job-date">Link unavailable</span>'}</div>
  </article>`;
}

async function loadJobs() {
  const list = $("#jobs-list");
  list.innerHTML = '<div class="empty-state"><p>Finding the right opportunities…</p></div>';
  try {
    const data = await api(`/api/jobs?${queryString()}`);
    state.total = data.total;
    $("#result-count").textContent = `(${data.total})`;
    $("#pagination-label").textContent = data.total
      ? `Showing ${((data.page - 1) * data.page_size) + 1}–${Math.min(data.page * data.page_size, data.total)} of ${data.total} roles`
      : "No roles found";
    $("#prev-page").disabled = data.page <= 1;
    $("#next-page").disabled = data.page * data.page_size >= data.total;
    $("#sort-label").innerHTML = $("#query-input").value.trim() ? "Best match <span>✦</span>" : "Recently added <span>⌄</span>";
    list.innerHTML = data.jobs.length
      ? data.jobs.map(jobCard).join("")
      : '<div class="empty-state"><div class="empty-icon">⌕</div><h3>No opportunities found</h3><p>Try a different search, or add career pages above to discover new roles.</p></div>';
  } catch (error) {
    list.innerHTML = `<div class="empty-state"><h3>Could not load roles</h3><p>${escapeHtml(error.message)}</p></div>`;
  }
}

async function refreshDashboard() {
  $("#refresh-button").disabled = true;
  try {
    await loadStats();
    await loadJobs();
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    $("#refresh-button").disabled = false;
  }
}

function showNotice(message, isError = false) {
  const notice = $("#crawl-notice");
  notice.textContent = message;
  notice.classList.toggle("error", isError);
  notice.classList.add("visible");
}

async function pollCrawl() {
  try {
    const status = await api("/api/crawl/status");
    if (status.state === "queued" || status.state === "running") {
      showNotice(status.state === "queued" ? "Your discovery is queued…" : "Discovery in progress. You can keep exploring while we check those career pages…");
      window.setTimeout(pollCrawl, 1800);
    } else if (status.state === "completed") {
      showNotice(`Discovery complete — ${status.jobs_found} roles found across ${status.seeds.length} career pages.`);
      $("#crawl-button").disabled = false;
      $("#crawl-button").innerHTML = "<span>↗</span> Start discovery";
      await refreshDashboard();
    } else if (status.state === "failed") {
      showNotice(`Discovery failed: ${status.error || "Unexpected error"}`, true);
      $("#crawl-button").disabled = false;
      $("#crawl-button").innerHTML = "<span>↗</span> Start discovery";
    }
  } catch (error) {
    showNotice(error.message, true);
    $("#crawl-button").disabled = false;
  }
}

$("#refresh-button").addEventListener("click", refreshDashboard);
$("#search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  state.page = 1;
  loadJobs();
});
["source-filter", "arrangement-filter", "status-filter", "remote-input"].forEach((id) => {
  $(`#${id}`).addEventListener("change", () => { state.page = 1; loadJobs(); });
});
$("#prev-page").addEventListener("click", () => { if (state.page > 1) { state.page -= 1; loadJobs(); } });
$("#next-page").addEventListener("click", () => { if (state.page * state.pageSize < state.total) { state.page += 1; loadJobs(); } });
$("#export-button").addEventListener("click", async () => {
  try {
    const params = queryString();
    params.set("page", "1");
    params.set("page_size", "100");
    const results = [];
    let page = 1;
    let total = 0;
    do {
      params.set("page", String(page));
      const data = await api(`/api/jobs?${params}`);
      total = data.total;
      results.push(...data.jobs);
      page += 1;
    } while (results.length < total);
    const columns = ["title", "company", "url", "location", "work_arrangement", "employment_type", "posting_date", "score", "reasons", "status", "source", "discovered_at"];
    const cell = (value) => {
      const text = String(value ?? "");
      const safe = /^[=+\-@\t\r]/.test(text) ? `'${text}` : text;
      return `"${safe.replaceAll('"', '""')}"`;
    };
    const csv = [columns.join(","), ...results.map(({ job, score, reasons }) => [
      job.title, job.company, job.url, job.location, job.work_arrangement,
      job.employment_type, job.posting_date, score, reasons.join("; "), job.status,
      job.source, job.discovered_at,
    ].map(cell).join(","))].join("\r\n");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    link.download = "jobfinder-results.csv";
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  } catch (error) {
    showNotice(`Could not export results: ${error.message}`, true);
  }
});
$("#crawl-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const seeds = $("#seed-urls").value.split(/\r?\n/).map((seed) => seed.trim()).filter(Boolean);
  const button = $("#crawl-button");
  if (!seeds.length) {
    showNotice("Add at least one career-page URL to start a discovery.", true);
    return;
  }
  button.disabled = true;
  button.textContent = "Starting…";
  try {
    await api("/api/crawl", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ seeds }),
    });
    showNotice("Your discovery is queued…");
    pollCrawl();
  } catch (error) {
    showNotice(error.message, true);
    button.disabled = false;
    button.innerHTML = "<span>↗</span> Start discovery";
  }
});

refreshDashboard();
