async function loadSLA() {
  const res = await fetch('/api/reports/sla');
  const data = await res.json();
  renderSLAChart(data);
  renderSLATable(data);
}

async function downloadSLA() {
  const res = await fetch('/api/reports/sla/download');
  const blob = await res.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'sla_report.xlsx';
  a.click();
  URL.revokeObjectURL(a.href);
}

async function loadIncidents() {
  const res = await fetch('/api/reports/incidents');
  const data = await res.json();
  renderIncidentSeverityChart(data);
  renderIncidentTables(data);
}

document.getElementById('btn-inc-refresh').onclick = async () => {
  await fetch('/api/reports/incidents/refresh');
  loadIncidents();
};

document.getElementById('btn-inc-download').onclick = async () => {
  const res = await fetch('/api/reports/incidents/download');
  const blob = await res.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'incident_top100.csv';
  a.click();
};

loadIncidents();


document.getElementById('btn-sla-refresh').onclick = loadSLA;
document.getElementById('btn-sla-download').onclick = downloadSLA;

// similar wiring for email + other tabs
loadSLA();
