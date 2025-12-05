// frontend/app.js

let slaChart = null;
let incSeverityChart = null;
let availChart = null;

const tabLoaded = {
  sla: false,
  availability: false,
  icmp: false,
  email: false,
  incidents: false,
};

async function fetchJson(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
  }
  return res.json();
}

/* ---------------------- STATUS ---------------------- */

function setStatus(text, ok, zabbixUrl) {
  const pill = document.getElementById("status-pill");
  if (pill) {
    pill.textContent = text;
    if (ok) {
      pill.className =
        "px-3 py-1 rounded-full text-xs border border-emerald-300 bg-emerald-100 text-emerald-800";
    } else {
      pill.className =
        "px-3 py-1 rounded-full text-xs border border-red-300 bg-red-100 text-red-800";
    }
  }

  const zbx = document.getElementById("zabbix-url-display");
  if (zbx) {
    zbx.textContent = zabbixUrl || "—";
  }
}

async function loadStatus() {
  try {
    const data = await fetchJson("/api/status");
    setStatus("Backend: OK", true, data.zabbix_url || "");
  } catch (err) {
    console.error("Failed to load status", err);
    setStatus("Backend: ERROR", false, "");
  }
}

/* ---------------------- SLA / SLI ---------------------- */

function parseSLAData(raw) {
  const rows = [];
  let firstService = null; // kept for backward compatibility if needed

  if (!raw || typeof raw !== "object") {
    return { rows, firstService };
  }

  for (const [slaId, slaObj] of Object.entries(raw)) {
    const slaName = slaObj.sla_name || `SLA ${slaId}`;
    const services = slaObj.service_data || {};

    for (const [svcId, svc] of Object.entries(services)) {
      const name = svc.name || `Service ${svcId}`;
      const slo = svc.slo ?? "";
      const labels = svc.month_labels || [];
      const values = svc.monthly_sli || [];

      const lastIndex = values.length > 0 ? values.length - 1 : -1;
      const latestMonth = lastIndex >= 0 ? labels[lastIndex] : "";
      const latestValue = lastIndex >= 0 ? values[lastIndex] : "";

      const row = {
        slaId,
        slaName,
        serviceId: svcId,
        serviceName: name,
        slo,
        monthLabels: labels,
        monthlyValues: values,
        latestMonth,
        latestValue,
      };

      rows.push(row);

      if (!firstService && labels.length && values.length) {
        firstService = row;
      }
    }
  }

  return { rows, firstService };
}

function renderSLATable(rows) {
  const container = document.getElementById("sla-table");
  if (!container) return;

  if (!rows.length) {
    container.innerHTML =
      '<p class="text-gray-500 text-sm">No SLA data returned from backend.</p>';
    return;
  }

  let html = `
    <table class="min-w-full divide-y divide-gray-200 text-sm">
      <thead class="bg-gray-50">
        <tr>
          <th class="px-3 py-2 text-left font-semibold text-gray-700">SLA</th>
          <th class="px-3 py-2 text-left font-semibold text-gray-700">Service</th>
          <th class="px-3 py-2 text-right font-semibold text-gray-700">SLO</th>
          <th class="px-3 py-2 text-left font-semibold text-gray-700">Latest month</th>
          <th class="px-3 py-2 text-right font-semibold text-gray-700">Latest SLI</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-100 bg-white">
  `;

  for (const row of rows) {
    html += `
      <tr>
        <td class="px-3 py-1 whitespace-nowrap">${row.slaName}</td>
        <td class="px-3 py-1 whitespace-nowrap">${row.serviceName}</td>
        <td class="px-3 py-1 text-right">${row.slo ?? ""}</td>
        <td class="px-3 py-1">${row.latestMonth || ""}</td>
        <td class="px-3 py-1 text-right">${row.latestValue || ""}</td>
      </tr>
    `;
  }

  html += "</tbody></table>";
  container.innerHTML = html;
}

function renderSLASummary(rows) {
  const container = document.getElementById("sla-summary");
  if (!container) return;

  if (!rows.length) {
    container.innerHTML =
      '<p class="text-gray-500 text-sm">No SLA data returned from backend.</p>';
    return;
  }

  const totalServices = rows.length;
  const withTarget = rows.filter(
    (r) => r.latestValue && typeof r.latestValue === "string"
  );
  const okServices = withTarget.filter((r) => {
    const v = parseFloat(String(r.latestValue).replace("%", ""));
    const slo = parseFloat(String(r.slo || "").replace("%", ""));
    if (Number.isNaN(v) || Number.isNaN(slo)) return false;
    return v >= slo;
  });

  container.innerHTML = `
    <p><span class="font-semibold">${totalServices}</span> services with SLA data.</p>
    <p><span class="font-semibold">${okServices.length}</span> services meet or exceed their SLO (based on latest month).</p>
  `;
}

/**
 * New: render all services on the SLA chart.
 * Each service becomes its own dataset with its own color.
 * Clicking the legend entry still hides/shows that service.
 */
function renderSLAChart(rows) {
  const canvas = document.getElementById("sla-chart");
  const statusEl = document.getElementById("sla-trend-status");
  if (!canvas) return;

  if (slaChart) {
    slaChart.destroy();
    slaChart = null;
  }

  if (!rows || !rows.length) {
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (statusEl) statusEl.textContent = "No SLA data to display.";
    return;
  }

  // Use month labels from the first row that has them
  const baseRow =
    rows.find((r) => Array.isArray(r.monthLabels) && r.monthLabels.length) ||
    rows[0];

  const labels = baseRow.monthLabels || [];
  if (!labels.length) {
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (statusEl) statusEl.textContent = "No SLA data to display.";
    return;
  }

  const datasets = rows.map((row) => {
    const indexByMonth = {};
    (row.monthLabels || []).forEach((m, idx) => {
      indexByMonth[m] = idx;
    });

    const dataPoints = labels.map((m) => {
      const idx = indexByMonth[m];
      if (idx === undefined) return null;
      const v = row.monthlyValues[idx];
      if (v == null) return null;
      const num = parseFloat(String(v).replace("%", ""));
      return Number.isNaN(num) ? null : num;
    });

    return {
      label: row.serviceName || `Service ${row.serviceId}`,
      data: dataPoints,
      tension: 0.25,
    };
  });

  const ctx = canvas.getContext("2d");
  slaChart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true }, // clicking legend toggles lines
      },
      scales: {
        y: {
          beginAtZero: true,
          suggestedMax: 100,
          title: { display: true, text: "SLI %" },
        },
      },
    },
  });

  if (statusEl) statusEl.textContent = "";
}

async function loadSLA() {
  const tableContainer = document.getElementById("sla-table");
  const trendContainer = document.getElementById("sla-trend-status");
  if (tableContainer) {
    tableContainer.innerHTML =
      '<p class="text-xs text-gray-500">Loading SLA data...</p>';
  }
  if (trendContainer) {
    trendContainer.textContent = "Loading SLA data...";
  }

  try {
    const raw = await fetchJson("/api/reports/sla");
    const { rows } = parseSLAData(raw);
    renderSLATable(rows);
    renderSLASummary(rows);
    renderSLAChart(rows);

    if (trendContainer) {
      trendContainer.textContent = rows.length
        ? ""
        : "No data returned from backend.";
    }
  } catch (err) {
    console.error("Failed to load SLA data", err);
    if (tableContainer) {
      tableContainer.innerHTML = `<p class="text-red-600 text-sm">Failed to load SLA data: ${err.message}</p>`;
    }
    if (trendContainer) {
      trendContainer.textContent = `Failed to load SLA data: ${err.message}`;
    }
  }
}

function downloadSLA() {
  window.location.href = "/api/reports/sla/download";
}

/* ---------------------- INCIDENTS ---------------------- */

function renderIncidentSeverityChart(data) {
  const canvas = document.getElementById("inc-severity-chart");
  if (!canvas) return;

  const labels = data.month_labels || [];
  const sevObj = data.severity || {};

  if (!labels.length || !Object.keys(sevObj).length) {
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    return;
  }

  const datasets = Object.entries(sevObj).map(([sev, monthMap]) => {
    const arr = labels.map((m) => monthMap[m] ?? 0);
    return { label: sev, data: arr, stack: "incidents" };
  });

  if (incSeverityChart) incSeverityChart.destroy();

  const ctx = canvas.getContext("2d");
  incSeverityChart = new Chart(ctx, {
    type: "bar",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom" } },
      scales: {
        x: { stacked: true },
        y: { stacked: true, beginAtZero: true },
      },
    },
  });
}

function renderIncTopTriggers(data) {
  const container = document.getElementById("inc-top-triggers");
  if (!container) return;

  const items = data.top_100_triggers || [];
  if (!items.length) {
    container.innerHTML =
      '<p class="text-gray-500 text-sm">No trigger data returned.</p>';
    return;
  }

  let html = `
    <table class="min-w-full divide-y divide-gray-200 text-sm">
      <thead class="bg-gray-50">
        <tr>
          <th class="px-3 py-2 text-left font-semibold text-gray-700">Trigger ID</th>
          <th class="px-3 py-2 text-right font-semibold text-gray-700">Count</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-100 bg-white">
  `;

  for (const entry of items) {
    const triggerId = Array.isArray(entry) ? entry[0] : entry.triggerid || "";
    const count = Array.isArray(entry) ? entry[1] : entry.count || 0;
    html += `
      <tr>
        <td class="px-3 py-1">${triggerId}</td>
        <td class="px-3 py-1 text-right">${count}</td>
      </tr>
    `;
  }

  html += "</tbody></table>";
  container.innerHTML = html;
}

function renderIncInvestigate(data) {
  const container = document.getElementById("inc-investigate");
  if (!container) return;

  const items = data.investigate || [];
  if (!items.length) {
    container.innerHTML =
      '<p class="text-gray-500 text-sm">No incidents currently flagged for investigation.</p>';
    return;
  }

  let html = `
    <table class="min-w-full divide-y divide-gray-200 text-sm">
      <thead class="bg-gray-50">
        <tr>
          <th class="px-3 py-2 text-left font-semibold text-gray-700">Trigger</th>
          <th class="px-3 py-2 text-left font-semibold text-gray-700">Severity</th>
          <th class="px-3 py-2 text-right font-semibold text-gray-700">Count (30d)</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-100 bg-white">
  `;

  for (const entry of items) {
    const descr = entry.description || entry.triggerid || "";
    const sev = entry.priority || "";
    const count = entry.count_30d || 0;
    html += `
      <tr>
        <td class="px-3 py-1">${descr}</td>
        <td class="px-3 py-1">${sev}</td>
        <td class="px-3 py-1 text-right">${count}</td>
      </tr>
    `;
  }

  html += "</tbody></table>";
  container.innerHTML = html;
}

function setIncGenerated(ts) {
  const el = document.getElementById("inc-generated");
  if (!el) return;

  if (!ts) {
    el.textContent = "Generated time not provided by backend.";
    return;
  }
  const d = new Date(ts * 1000);
  el.textContent = d.toLocaleString();
}

async function loadIncidents() {
  const topContainer = document.getElementById("inc-top-triggers");
  if (topContainer) {
    topContainer.innerHTML =
      '<p class="text-xs text-gray-500">Loading incident data...</p>';
  }

  try {
    const data = await fetchJson("/api/reports/incidents");
    setIncGenerated(data.generated_at);
    renderIncidentSeverityChart(data);
    renderIncTopTriggers(data);
    renderIncInvestigate(data);
  } catch (err) {
    console.error("Failed to load incidents", err);
    if (topContainer) {
      topContainer.innerHTML = `<p class="text-red-600 text-sm">Failed to load incident data: ${err.message}</p>`;
    }
  }
}

function downloadIncidents() {
  window.location.href = "/api/reports/incidents/download";
}

/* ---------------------- AVAILABILITY ---------------------- */

function normalizeAvailabilityValue(row) {
  const raw = row.availability;
  if (raw === null || raw === undefined) return null;

  if (typeof raw === "number") {
    return Number.isNaN(raw) ? null : raw;
  }

  const s = String(raw).trim();
  if (!s || s.toLowerCase() === "no data") return null;

  const cleaned = s.replace("%", "").trim();
  const num = Number(cleaned);
  return Number.isNaN(num) ? null : num;
}

function buildAvailabilityBuckets(rows) {
  const buckets = {};
  let noDataCount = 0;

  rows.forEach((row) => {
    const num = normalizeAvailabilityValue(row);
    if (num === null) {
      noDataCount += 1;
      return;
    }

    const rounded = Math.round(num * 10) / 10;
    const label = `${rounded.toFixed(1)}%`;
    buckets[label] = (buckets[label] || 0) + 1;
  });

  const labels = Object.keys(buckets).sort(
    (a, b) => parseFloat(b) - parseFloat(a)
  );
  const counts = labels.map((l) => buckets[l]);

  return { labels, counts, noDataCount };
}

function renderAvailabilityChart(rows) {
  const canvas = document.getElementById("avail-chart");
  if (!canvas) return;

  if (availChart) {
    availChart.destroy();
    availChart = null;
  }

  const { labels, counts } = buildAvailabilityBuckets(rows);

  if (!labels.length) {
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    return;
  }

  const ctx = canvas.getContext("2d");
  availChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Number of servers",
          data: counts,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
      },
      scales: {
        y: {
          beginAtZero: true,
          title: { display: true, text: "Servers" },
        },
        x: {
          title: { display: true, text: "Availability (%)" },
        },
      },
    },
  });
}

function renderAvailabilitySummary(rows) {
  const el = document.getElementById("avail-summary");
  if (!el) return;

  if (!rows.length) {
    el.textContent = "No availability data returned from backend.";
    return;
  }

  let withData = 0;
  let noData = 0;
  rows.forEach((row) => {
    const num = normalizeAvailabilityValue(row);
    if (num === null) noData += 1;
    else withData += 1;
  });

  el.textContent = `${withData} servers with availability data, ${noData} servers with no data.`;
}

function renderAvailabilityTable(rows) {
  const container = document.getElementById("avail-table");
  if (!container) return;

  if (!rows.length) {
    container.innerHTML =
      '<p class="text-gray-500 text-sm">No availability data returned from backend.</p>';
    return;
  }

  const sorted = [...rows].sort((a, b) => {
    const avA = normalizeAvailabilityValue(a);
    const avB = normalizeAvailabilityValue(b);
    if (avA === null && avB === null) return 0;
    if (avA === null) return 1;
    if (avB === null) return -1;
    return avB - avA;
  });

  let html = `
    <table class="min-w-full divide-y divide-gray-200 text-sm">
      <thead class="bg-gray-50">
        <tr>
          <th class="px-3 py-2 text-left font-semibold text-gray-700">Host</th>
          <th class="px-3 py-2 text-right font-semibold text-gray-700">Availability</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-100 bg-white">
  `;

  sorted.forEach((row) => {
    const host = row.host || "";
    const num = normalizeAvailabilityValue(row);
    const display = num === null ? "No data" : `${num.toFixed(1)}%`;

    html += `
      <tr>
        <td class="px-3 py-1 whitespace-nowrap">${host}</td>
        <td class="px-3 py-1 text-right">${display}</td>
      </tr>
    `;
  });

  html += "</tbody></table>";
  container.innerHTML = html;
}

/* ---------------------- AVAILABILITY & ICMP ---------------------- */

async function loadAvailability() {
  const summaryEl = document.getElementById("avail-summary");
  const tableEl = document.getElementById("avail-table");

  if (summaryEl) {
    summaryEl.textContent = "Loading server availability...";
  }
  if (tableEl) {
    tableEl.innerHTML =
      '<p class="text-xs text-gray-500">Loading server availability...</p>';
  }

  try {
    const data = await fetchJson("/api/reports/availability");
    renderAvailabilityChart(data);
    renderAvailabilitySummary(data);
    renderAvailabilityTable(data);
  } catch (err) {
    console.error("Failed to load availability", err);
    if (summaryEl) {
      summaryEl.textContent = `Failed to load availability: ${err.message}`;
    }
    if (tableEl) {
      tableEl.innerHTML = `<p class="text-red-600 text-sm">Failed to load availability: ${err.message}</p>`;
    }
  }
}

/* ---------------------- MONTHLY REPORT ---------------------- */

async function updateMonthlyReport() {
  try {
    await fetchJson("/api/reports/monthly/refresh", { method: "POST" });
    console.log("Monthly report refreshed.");
  } catch (err) {
    console.error("Failed to refresh monthly report", err);
    alert("Failed to update monthly report: " + err.message);
  }
}

function downloadMonthlyReport() {
  window.location.href = "/api/reports/monthly/download";
}

function downloadAvailability() {
  window.location.href = "/api/reports/availability/download";
}

async function loadICMP() {
  const container = document.getElementById("icmp-content");
  if (container) {
    container.innerHTML =
      '<p class="text-xs text-gray-500">Loading ICMP report...</p>';
  }
  try {
    const data = await fetchJson("/api/reports/icmp");
    if (container) {
      container.innerHTML =
        "<pre class='text-xs whitespace-pre-wrap break-all'>" +
        JSON.stringify(data, null, 2) +
        "</pre>";
    }
  } catch (err) {
    console.error("Failed to load ICMP", err);
    if (container) {
      container.innerHTML = `<p class="text-red-600 text-sm">Failed to load ICMP: ${err.message}</p>`;
    }
  }
}

function downloadICMP() {
  window.location.href = "/api/reports/icmp/download";
}

/* ---------------------- EMAIL SETTINGS ---------------------- */

async function loadEmailSettings() {
  const msg = document.getElementById("email-settings-message");
  if (msg) {
    msg.textContent = "Loading settings...";
    msg.className = "text-xs text-gray-500";
  }
  try {
    const data = await fetchJson("/api/email/settings");
    document.getElementById("smtp-host").value = data.smtp_host || "";
    document.getElementById("smtp-port").value = data.smtp_port || "";
    document.getElementById("smtp-from").value = data.from_addr || "";
    document.getElementById("smtp-to").value = (data.to_addr || []).join(", ");
    document.getElementById("smtp-use-tls").checked = !!data.use_tls;
    document.getElementById("smtp-use-auth").checked = !!data.use_auth;
    document.getElementById("smtp-username").value = data.username || "";
    document.getElementById("smtp-password").value = data.password || "";

    if (msg) {
      msg.textContent = "Settings loaded.";
      msg.className = "text-xs text-emerald-600";
    }
  } catch (err) {
    console.error("Failed to load email settings", err);
    if (msg) {
      msg.textContent = `Failed to load settings: ${err.message}`;
      msg.className = "text-xs text-red-600";
    }
  }
}

async function saveEmailSettings() {
  const msg = document.getElementById("email-settings-message");
  if (msg) {
    msg.textContent = "Saving settings...";
    msg.className = "text-xs text-gray-500";
  }

  try {
    const payload = {
      smtp_host: document.getElementById("smtp-host").value || "",
      smtp_port: Number(document.getElementById("smtp-port").value) || 0,
      from_addr: document.getElementById("smtp-from").value || "",
      to_addr: (document.getElementById("smtp-to").value || "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      use_tls: document.getElementById("smtp-use-tls").checked,
      use_auth: document.getElementById("smtp-use-auth").checked,
      username: document.getElementById("smtp-username").value || "",
      password: document.getElementById("smtp-password").value || "",
    };

    await fetchJson("/api/email/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (msg) {
      msg.textContent = "Settings saved.";
      msg.className = "text-xs text-emerald-600";
    }
  } catch (err) {
    console.error("Failed to save email settings", err);
    if (msg) {
      msg.textContent = `Failed to save settings: ${err.message}`;
      msg.className = "text-xs text-red-600";
    }
  }
}

/* ---------------------- EMAIL: SEND SLA REPORT ---------------------- */

async function sendSLAEmail() {
  try {
    await fetchJson("/api/email/send-sla", { method: "POST" });
    alert("SLA report email triggered.");
  } catch (err) {
    console.error("Failed to send SLA email", err);
    alert(`Failed to send SLA email: ${err.message}`);
  }
}

/* ---------------------- TABS ---------------------- */

function activateTab(tabName) {
  document.querySelectorAll(".tab-view").forEach((section) => {
    section.classList.add("hidden");
  });
  const activeSection = document.getElementById(`tab-${tabName}`);
  if (activeSection) {
    activeSection.classList.remove("hidden");
  }

  document.querySelectorAll(".tab-btn").forEach((btn) => {
    if (btn.dataset.tab === tabName) {
      btn.classList.add("border-blue-600", "text-blue-600");
      btn.classList.remove(
        "border-transparent",
        "text-gray-600",
        "hover:text-gray-900",
        "hover:border-gray-300"
      );
    } else {
      btn.classList.remove("border-blue-600", "text-blue-600");
      btn.classList.add(
        "border-transparent",
        "text-gray-600",
        "hover:text-gray-900",
        "hover:border-gray-300"
      );
    }
  });

  if (!tabLoaded[tabName]) {
    tabLoaded[tabName] = true;
    if (tabName === "sla") loadSLA();
    else if (tabName === "availability") loadAvailability();
    else if (tabName === "icmp") loadICMP();
    else if (tabName === "email") loadEmailSettings();
    else if (tabName === "incidents") loadIncidents();
  }
}

function setupTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      if (tab) activateTab(tab);
    });
  });
}

/* ---------------------- WIRE UP ---------------------- */

// frontend/app.js (bottom of file) 
document.addEventListener("DOMContentLoaded", () => {
  // Buttons
  const btnSlaRefresh = document.getElementById("btn-sla-refresh");
  if (btnSlaRefresh) btnSlaRefresh.addEventListener("click", loadSLA);

  const btnSlaDownload = document.getElementById("btn-sla-download");
  if (btnSlaDownload) btnSlaDownload.addEventListener("click", downloadSLA);

  const btnSlaEmail = document.getElementById("btn-sla-email");
  if (btnSlaEmail) btnSlaEmail.addEventListener("click", sendSLAEmail);

  const btnIncRefresh = document.getElementById("btn-inc-refresh");
  if (btnIncRefresh) btnIncRefresh.addEventListener("click", loadIncidents);

  const btnIncDownload = document.getElementById("btn-inc-download");
  if (btnIncDownload)
    btnIncDownload.addEventListener("click", downloadIncidents);

  const btnAvailRefresh = document.getElementById("btn-avail-refresh");
  if (btnAvailRefresh)
    btnAvailRefresh.addEventListener("click", loadAvailability);

  const btnAvailDownload = document.getElementById("btn-avail-download");
  if (btnAvailDownload)
    btnAvailDownload.addEventListener("click", downloadAvailability);

  const btnIcmpRefresh = document.getElementById("btn-icmp-refresh");
  if (btnIcmpRefresh) btnIcmpRefresh.addEventListener("click", loadICMP);

  const btnIcmpDownload = document.getElementById("btn-icmp-download");
  if (btnIcmpDownload)
    btnIcmpDownload.addEventListener("click", downloadICMP);

  const btnEmailSave = document.getElementById("btn-email-save");
  if (btnEmailSave) btnEmailSave.addEventListener("click", saveEmailSettings);

  // Monthly report buttons
  const btnMonthlyRefresh = document.getElementById("btn-monthly-refresh");
  if (btnMonthlyRefresh)
    btnMonthlyRefresh.addEventListener("click", updateMonthlyReport);

  const btnMonthlyDownload = document.getElementById("btn-monthly-download");
  if (btnMonthlyDownload)
    btnMonthlyDownload.addEventListener("click", downloadMonthlyReport);

  setupTabs();
  loadStatus();
  activateTab("sla");

  // Removed automatic updateMonthlyReport() call to avoid 504 popups at startup
});

