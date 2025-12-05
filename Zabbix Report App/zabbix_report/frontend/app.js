// frontend/app.js

let slaChart = null;
let incSeverityChart = null;

const tabLoaded = {
  sla: false,
  availability: false,
  icmp: false,
  email: false,
  incidents: false,
};

function setStatus(text, ok, zabbixUrl) {
  const pill = document.getElementById("status-pill");
  if (!pill) return;

  pill.textContent = text;
  if (ok) {
    pill.className =
      "px-2 py-1 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300 text-xs";
  } else {
    pill.className =
      "px-2 py-1 rounded-full bg-red-100 text-red-800 border border-red-300 text-xs";
  }

  const zbx = document.getElementById("zabbix-url-display");
  if (zbx && zabbixUrl) {
    zbx.textContent = `Zabbix URL: ${zabbixUrl}`;
  }
}

async function fetchJson(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
  }
  return res.json();
}

/* ---------------------- STATUS ---------------------- */

async function loadStatus() {
  try {
    const data = await fetchJson("/api/status");
    setStatus("Backend: OK", true, data.zabbix_url || "");
  } catch (err) {
    console.error("Failed to load status", err);
    setStatus("Backend: ERROR", false);
  }
}

/* ---------------------- SLA / SLI ---------------------- */

function parseSLAData(raw) {
  const rows = [];
  let firstService = null;

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
      '<p class="text-gray-500">No SLA data returned from backend.</p>';
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
      '<p class="text-gray-500">No SLA data returned from backend.</p>';
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

function renderSLAChart(firstService) {
  const canvas = document.getElementById("sla-chart");
  if (!canvas) return;

  if (!firstService || !firstService.monthLabels.length) {
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    return;
  }

  const labels = firstService.monthLabels;
  const dataPoints = firstService.monthlyValues.map((v) => {
    if (v == null) return null;
    const num = parseFloat(String(v).replace("%", ""));
    return Number.isNaN(num) ? null : num;
  });

  if (slaChart) {
    slaChart.destroy();
  }

  const ctx = canvas.getContext("2d");
  slaChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: `${firstService.serviceName} SLI (%)`,
          data: dataPoints,
          tension: 0.25,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true },
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
}

async function loadSLA() {
  const tableContainer = document.getElementById("sla-table");
  if (tableContainer) {
    tableContainer.innerHTML =
      '<p class="text-xs text-gray-500">Loading SLA data...</p>';
  }

  try {
    const raw = await fetchJson("/api/reports/sla");
    const { rows, firstService } = parseSLAData(raw);
    renderSLATable(rows);
    renderSLASummary(rows);
    renderSLAChart(firstService);
  } catch (err) {
    console.error("Failed to load SLA data", err);
    if (tableContainer) {
      tableContainer.innerHTML = `<p class="text-red-600 text-sm">Failed to load SLA data: ${err.message}</p>`;
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
  const severity = data.severity || {};

  const datasets = Object.entries(severity).map(([sev, counts]) => ({
    label: sev,
    data: counts || [],
  }));

  if (!labels.length || !datasets.length) {
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    return;
  }

  if (incSeverityChart) {
    incSeverityChart.destroy();
  }

  const ctx = canvas.getContext("2d");
  incSeverityChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom" },
      },
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
      '<p class="text-gray-500">No trigger data returned.</p>';
    return;
  }

  let html = `
    <table class="min-w-full divide-y divide-gray-200 text-sm">
      <thead class="bg-gray-50">
        <tr>
          <th class="px-3 py-2 text-left font-semibold text-gray-700">Trigger</th>
          <th class="px-3 py-2 text-right font-semibold text-gray-700">Count</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-100 bg-white">
  `;

  for (const entry of items) {
    // incident_trends.py returns list of [trigger_key, count]
    const triggerKey = Array.isArray(entry) ? entry[0] : entry.trigger || "";
    const count = Array.isArray(entry) ? entry[1] : entry.count || 0;
    html += `
      <tr>
        <td class="px-3 py-1">${triggerKey}</td>
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
      '<p class="text-gray-500">No incidents currently flagged for investigation.</p>';
    return;
  }

  let html = `
    <table class="min-w-full divide-y divide-gray-200 text-sm">
      <thead class="bg-gray-50">
        <tr>
          <th class="px-3 py-2 text-left font-semibold text-gray-700">Key</th>
          <th class="px-3 py-2 text-right font-semibold text-gray-700">Count</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-100 bg-white">
  `;

  for (const entry of items) {
    const key = Array.isArray(entry) ? entry[0] : entry.key || "";
    const count = Array.isArray(entry) ? entry[1] : entry.count || 0;
    html += `
      <tr>
        <td class="px-3 py-1">${key}</td>
        <td class="px-3 py-1 text-right">${count}</td>
      </tr>
    `;
  }

  html += "</tbody></table>";
  container.innerHTML = html;
}

async function loadIncidents() {
  const topContainer = document.getElementById("inc-top-triggers");
  if (topContainer) {
    topContainer.innerHTML =
      '<p class="text-xs text-gray-500">Loading incident data...</p>';
  }

  try {
    const data = await fetchJson("/api/reports/incidents");

    const genElem = document.getElementById("inc-generated");
    if (genElem) {
      genElem.textContent =
        data.generated_at || "Generated time not provided by backend.";
    }

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
  // adjust if backend exposes a different download path
  window.location.href = "/api/reports/incidents/download";
}

/* ---------------------- AVAILABILITY & ICMP (simple stubs) ---------------------- */

async function loadAvailability() {
  const container = document.getElementById("avail-content");
  if (container) {
    container.innerHTML =
      '<p class="text-xs text-gray-500">Loading server availability...</p>';
  }
  try {
    const data = await fetchJson("/api/reports/availability");
    if (container) {
      container.innerHTML =
        "<pre class='text-xs whitespace-pre-wrap break-all'>" +
        JSON.stringify(data, null, 2) +
        "</pre>";
    }
  } catch (err) {
    console.error("Failed to load availability", err);
    if (container) {
      container.innerHTML = `<p class="text-red-600 text-sm">Failed to load availability: ${err.message}</p>`;
    }
  }
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
      method: "POST",
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
  // views
  document.querySelectorAll(".tab-view").forEach((section) => {
    section.classList.add("hidden");
  });
  const activeSection = document.getElementById(`tab-${tabName}`);
  if (activeSection) {
    activeSection.classList.remove("hidden");
  }

  // buttons
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    if (btn.dataset.tab === tabName) {
      btn.classList.remove(
        "border-transparent",
        "text-gray-600",
        "hover:text-gray-900",
        "hover:border-gray-300"
      );
      btn.classList.add("border-blue-600", "text-blue-600");
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

  // lazy-load data per tab
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

document.addEventListener("DOMContentLoaded", () => {
  // buttons
  const btnSlaRefresh = document.getElementById("btn-sla-refresh");
  if (btnSlaRefresh) btnSlaRefresh.addEventListener("click", loadSLA);

  const btnSlaDownload = document.getElementById("btn-sla-download");
  if (btnSlaDownload) btnSlaDownload.addEventListener("click", downloadSLA);

  const btnSlaEmail = document.getElementById("btn-sla-email");
  if (btnSlaEmail) btnSlaEmail.addEventListener("click", sendSLAEmail);

  const btnIncRefresh = document.getElementById("btn-inc-refresh");
  if (btnIncRefresh) btnIncRefresh.addEventListener("click", loadIncidents);

  const btnIncDownload = document.getElementById("btn-inc-download");
  if (btnIncDownload) btnIncDownload.addEventListener("click", downloadIncidents);

  const btnAvailRefresh = document.getElementById("btn-avail-refresh");
  if (btnAvailRefresh) btnAvailRefresh.addEventListener("click", loadAvailability);

  const btnAvailDownload = document.getElementById("btn-avail-download");
  if (btnAvailDownload)
    btnAvailDownload.addEventListener("click", downloadAvailability);

  const btnIcmpRefresh = document.getElementById("btn-icmp-refresh");
  if (btnIcmpRefresh) btnIcmpRefresh.addEventListener("click", loadICMP);

  const btnIcmpDownload = document.getElementById("btn-icmp-download");
  if (btnIcmpDownload) btnIcmpDownload.addEventListener("click", downloadICMP);

  const btnEmailSave = document.getElementById("btn-email-save");
  if (btnEmailSave) btnEmailSave.addEventListener("click", saveEmailSettings);

  setupTabs();
  loadStatus();

  // default tab
  activateTab("sla");
});
