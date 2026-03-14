// app.js
(function (global) {
  "use strict";

  const NM = (global.NetworkMap = global.NetworkMap || {});
  const state =
    (global.NMState =
      global.NMState ||
      {
        rawData: null,
        rawNodeMap: null,
        currentGraph: { nodes: [], edges: [] },
        cy: null,
        summaryData: { incoming: [], outgoing: [] },
      });

  const DARK_MODE_KEY = "networkMapDarkMode";
  const STATUS_POLL_INTERVAL_MS = 30000;

  function ensureStateDefaults() {
    if (!(state.rawNodeMap instanceof Map)) {
      state.rawNodeMap = new Map();
    }
    if (!state.currentGraph) {
      state.currentGraph = { nodes: [], edges: [] };
    }
    if (!state.summaryData) {
      state.summaryData = { incoming: [], outgoing: [] };
    }
    if (typeof state.lastUpdated !== "number") {
      state.lastUpdated = 0;
    }
    if (typeof state.hasDrawnGraph !== "boolean") {
      state.hasDrawnGraph = false;
    }
    if (!state.pollTimer) {
      state.pollTimer = null;
    }
  }

  function loadDarkModePreference() {
    try {
      return localStorage.getItem(DARK_MODE_KEY) === "1";
    } catch (e) {
      return false;
    }
  }

  function saveDarkModePreference(enabled) {
    try {
      localStorage.setItem(DARK_MODE_KEY, enabled ? "1" : "0");
    } catch (e) {
      // ignore
    }
  }

  function applyDarkMode(enabled, controls, summary, nbinfo, cyContainer) {
    const method = enabled ? "add" : "remove";

    if (enabled === undefined || enabled === null) return;

    if (document.body) {
      document.body.classList[method]("dark-mode");
    }
    if (controls) controls.classList[method]("dark-mode");
    if (summary) summary.classList[method]("dark-mode");
    if (nbinfo) nbinfo.classList[method]("dark-mode");
    if (cyContainer) cyContainer.classList[method]("dark-mode");
  }

  function showSpinner(show) {
    const spinner = document.getElementById("spinner");
    if (!spinner) return;
    spinner.style.display = show ? "block" : "none";
  }

  function buildNodeMap(nodes) {
    const map = new Map();
    (nodes || []).forEach((node) => {
      const id = node && node.data && node.data.id;
      if (id) {
        map.set(id, node);
      }
    });
    return map;
  }

  function sanitizeNetworkMapData(data) {
    const normalized = data || {};
    if (!Array.isArray(normalized.nodes)) normalized.nodes = [];
    if (!Array.isArray(normalized.edges)) normalized.edges = [];

    normalized.edges = normalized.edges.filter(
      (edge) => edge && edge.data && edge.data.source && edge.data.target
    );

    normalized.edges.forEach((edge, idx) => {
      if (!edge.data.id) edge.data.id = `e${idx}`;
    });

    normalized.nodes.forEach((node) => {
      if (!node.data) node.data = {};
      if (!node.data.id && node.data.label) {
        node.data.id = node.data.label;
      }
      if (!node.data.label && node.data.id) {
        node.data.label = node.data.id;
      }
    });

    return normalized;
  }

  function populateHostSelect(nodes) {
    const select = document.getElementById("hostSelect");
    if (!select) return;

    const previousValue = select.value;
    select.innerHTML = "";

    const allOption = document.createElement("option");
    allOption.value = "";
    allOption.textContent = "Alla värdar";
    select.appendChild(allOption);

    (nodes || [])
      .map((node) => node.data.id)
      .sort()
      .forEach((id) => {
        const option = document.createElement("option");
        option.value = id;
        option.textContent = id;
        select.appendChild(option);
      });

    if (previousValue && state.rawNodeMap.has(previousValue)) {
      select.value = previousValue;
    }
  }

  function formatLastUpdated(timestamp) {
    if (!timestamp) return "Ingen uppdatering ännu";

    try {
      return new Date(timestamp * 1000).toLocaleString("sv-SE");
    } catch (e) {
      return String(timestamp);
    }
  }

  function setDataStatus(message) {
    const dataStatus = document.getElementById("dataStatus");
    if (dataStatus) {
      dataStatus.textContent = message;
    }
  }

  function refreshStatus(showErrors = false) {
    return fetch("/api/status")
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to fetch /api/status");
        }
        return response.json();
      })
      .then((status) => {
        const lastUpdated = Number(status.last_updated) || 0;
        const changed = !!lastUpdated && lastUpdated !== state.lastUpdated;
        state.lastUpdated = lastUpdated;
        setDataStatus(`Senast uppdaterad: ${formatLastUpdated(lastUpdated)}`);
        return { changed, lastUpdated };
      })
      .catch((err) => {
        console.error(err);
        if (showErrors) {
          alert("Kunde inte läsa status: " + err.message);
        }
        if (state.lastUpdated) {
          setDataStatus(`Senast uppdaterad: ${formatLastUpdated(state.lastUpdated)}`);
        } else {
          setDataStatus("Kunde inte läsa status.");
        }
        return { changed: false, lastUpdated: state.lastUpdated || 0, error: err };
      });
  }

  function fetchNetworkMap(options = {}) {
    const {
      redrawIfGraphActive = false,
      showBusy = true,
      showErrors = true,
      showNoEdgesAlert = true,
    } = options;

    if (showBusy) {
      showSpinner(true);
    }

    return fetch("/api/network_map")
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to fetch /api/network_map");
        }
        return response.json();
      })
      .then((data) => {
        const normalized = sanitizeNetworkMapData(data);
        state.rawData = normalized;
        state.rawNodeMap = buildNodeMap(normalized.nodes);
        populateHostSelect(normalized.nodes);

        if (redrawIfGraphActive && state.hasDrawnGraph) {
          applyFiltersAndDraw({ showNoEdgesAlert });
        }

        return normalized;
      })
      .catch((err) => {
        console.error(err);
        if (showErrors) {
          alert("Kunde inte läsa nätverksdata: " + err.message);
        }
        throw err;
      })
      .finally(() => {
        if (showBusy) {
          showSpinner(false);
        }
      });
  }

  function readFilterSettings() {
    const filters = NM.filters || {};
    const hostSelect = document.getElementById("hostSelect");

    return {
      host: hostSelect ? hostSelect.value : "",
      srcTokens: filters.parseListFilter
        ? filters.parseListFilter((document.getElementById("filterSrc") || {}).value || "")
        : [],
      dstTokens: filters.parseListFilter
        ? filters.parseListFilter((document.getElementById("filterDst") || {}).value || "")
        : [],
      portMatcher: filters.parsePortFilter
        ? filters.parsePortFilter(((document.getElementById("filterPort") || {}).value || "").trim())
        : null,
      excludePublic: !!(document.getElementById("excludePub") || {}).checked,
      excludeNoisePorts: (document.getElementById("excludeNoisePorts") || {}).checked !== false,
      ipFilters: filters.parseIpFilters
        ? filters.parseIpFilters(((document.getElementById("filterIp") || {}).value || "").trim())
        : [],
      minSep:
        parseInt(((document.getElementById("minSep") || {}).value || "50").trim(), 10) ||
        50,
      sx:
        parseFloat(((document.getElementById("scaleX") || {}).value || "1.0").trim()) ||
        1.0,
      sy:
        parseFloat(((document.getElementById("scaleY") || {}).value || "1.0").trim()) ||
        1.0,
    };
  }

  function applyFiltersAndDraw(options = {}) {
    const { showNoEdgesAlert = true } = options;

    if (!state.rawData) return false;

    const settings = readFilterSettings();
    let subgraph;

    if (settings.host && typeof NM.buildSubgraph === "function") {
      subgraph = NM.buildSubgraph(
        settings.host,
        settings.srcTokens,
        settings.dstTokens,
        settings.portMatcher,
        settings.excludePublic,
        settings.excludeNoisePorts,
        settings.ipFilters
      );
    } else if (typeof NM.buildGlobalSubgraph === "function") {
      subgraph = NM.buildGlobalSubgraph(
        settings.srcTokens,
        settings.dstTokens,
        settings.portMatcher,
        settings.excludePublic,
        settings.excludeNoisePorts,
        settings.ipFilters
      );
    } else {
      alert("Filter-funktioner saknas (buildSubgraph / buildGlobalSubgraph).");
      return false;
    }

    if (!subgraph || !Array.isArray(subgraph.nodes) || !Array.isArray(subgraph.edges)) {
      alert("Felaktigt subgraph-resultat.");
      return false;
    }

    if (typeof NM.drawGraph !== "function") {
      alert("drawGraph saknas (graph.js inte laddad?).");
      return false;
    }

    const drawn = NM.drawGraph({
      nodes: subgraph.nodes,
      edges: subgraph.edges,
      minSep: settings.minSep,
      sx: settings.sx,
      sy: settings.sy,
      showNoEdgesAlert,
    });

    state.hasDrawnGraph = drawn === true;
    return state.hasDrawnGraph;
  }

  function startStatusPolling() {
    if (state.pollTimer) {
      global.clearInterval(state.pollTimer);
    }

    state.pollTimer = global.setInterval(() => {
      refreshStatus(false).then((status) => {
        if (status.changed) {
          fetchNetworkMap({
            redrawIfGraphActive: state.hasDrawnGraph,
            showBusy: false,
            showErrors: false,
            showNoEdgesAlert: false,
          }).catch(() => {
            // handled in fetchNetworkMap
          });
        }
      });
    }, STATUS_POLL_INTERVAL_MS);
  }

  function init() {
    ensureStateDefaults();

    const hostFilterRow = document.getElementById("hostFilterRow");
    const btnApply = document.getElementById("btnApply");
    const btnRefreshData = document.getElementById("btnRefreshData");
    const btnDownloadReport = document.getElementById("btnDownloadReport");
    const toggleDarkMode = document.getElementById("toggleDarkMode");

    const sumFsrc = document.getElementById("sumFilterSrc");
    const sumFdst = document.getElementById("sumFilterDst");
    const sumFport = document.getElementById("sumFilterPort");
    const closeSummary = document.getElementById("closeSummary");
    const minimizeSummary = document.getElementById("minimizeSummary");

    const closeNb = document.getElementById("closeNb");
    const minimizeNb = document.getElementById("minimizeNb");

    const controls = document.getElementById("controls");
    const summary = document.getElementById("summary");
    const nbinfo = document.getElementById("nbinfo");
    const cyContainer = document.getElementById("cy");

    const initialDarkMode = loadDarkModePreference();
    applyDarkMode(initialDarkMode, controls, summary, nbinfo, cyContainer);

    if (hostFilterRow) {
      hostFilterRow.style.display = "none";
    }

    [sumFsrc, sumFdst, sumFport].forEach((el) => {
      if (!el) return;
      el.addEventListener("input", () => {
        if (typeof NM.updateSummaryDisplay === "function") {
          NM.updateSummaryDisplay();
        }
      });
    });

    if (closeSummary) {
      closeSummary.onclick = () => {
        if (summary) summary.hidden = true;
      };
    }

    if (minimizeSummary) {
      minimizeSummary.onclick = () => {
        const filtersDiv = document.getElementById("summaryFilters");
        const content = document.getElementById("summaryContent");
        if (!filtersDiv || !content) return;

        if (filtersDiv.style.display === "none") {
          filtersDiv.style.display = "block";
          content.style.display = "block";
          minimizeSummary.textContent = "[–]";
        } else {
          filtersDiv.style.display = "none";
          content.style.display = "none";
          minimizeSummary.textContent = "[+]";
        }
      };
    }

    if (closeNb) {
      closeNb.onclick = () => {
        if (nbinfo) nbinfo.hidden = true;
      };
    }

    if (minimizeNb) {
      minimizeNb.onclick = function () {
        const details = document.getElementById("nbDetails");
        if (!details) return;
        if (details.style.display === "none") {
          details.style.display = "block";
          this.textContent = "[–]";
        } else {
          details.style.display = "none";
          this.textContent = "[+]";
        }
      };
    }

    if (toggleDarkMode) {
      toggleDarkMode.onclick = () => {
        const currentlyEnabled = document.body.classList.contains("dark-mode");
        const newEnabled = !currentlyEnabled;
        applyDarkMode(newEnabled, controls, summary, nbinfo, cyContainer);
        saveDarkModePreference(newEnabled);
      };
    }

    if (btnDownloadReport && typeof NM.handleDownloadReports === "function") {
      btnDownloadReport.onclick = () => NM.handleDownloadReports();
    }

    if (btnApply) {
      btnApply.onclick = () => {
        applyFiltersAndDraw({ showNoEdgesAlert: true });
      };
    }

    if (btnRefreshData) {
      btnRefreshData.onclick = () => {
        setDataStatus("Uppdaterar data…");
        fetchNetworkMap({
          redrawIfGraphActive: state.hasDrawnGraph,
          showBusy: true,
          showErrors: true,
          showNoEdgesAlert: true,
        })
          .then(() => refreshStatus(false))
          .catch(() => {
            // handled above
          });
      };
    }

    setDataStatus("Laddar data…");
    fetchNetworkMap({ redrawIfGraphActive: false, showBusy: true, showErrors: true })
      .then(() => refreshStatus(false))
      .finally(() => {
        startStatusPolling();
      })
      .catch(() => {
        startStatusPolling();
      });
  }

  document.addEventListener("DOMContentLoaded", init);
})(window);
