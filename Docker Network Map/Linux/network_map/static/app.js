// app.js
(function (global) {
  "use strict";

  const NM = (global.NetworkMap = global.NetworkMap || {});
  const state =
    (global.NMState =
      global.NMState ||
      {
        rawData: null,
        cy: null,
        summaryData: { incoming: [], outgoing: [] },
      });

  const DARK_MODE_KEY = "networkMapDarkMode";

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

  function populateHostSelect(nodes) {
    const sel = document.getElementById("hostSelect");
    if (!sel) return;

    sel.innerHTML = "";

    const optAll = document.createElement("option");
    optAll.value = "";
    optAll.textContent = "Alla värdar";
    sel.appendChild(optAll);

    (nodes || [])
      .map((n) => n.data.id)
      .sort()
      .forEach((id) => {
        const opt = document.createElement("option");
        opt.value = id;
        opt.textContent = id;
        sel.appendChild(opt);
      });
  }

  function fetchNetworkMap() {
    showSpinner(true);
    fetch("/api/network_map")
      .then((r) => {
        if (!r.ok) {
          throw new Error("Failed to fetch /api/network_map");
        }
        return r.json();
      })
      .then((data) => {
        if (!data.nodes) data.nodes = [];
        if (!data.edges) data.edges = [];

        data.edges = data.edges.filter(
          (e) => e.data && e.data.source && e.data.target
        );

        data.edges.forEach((e, idx) => {
          if (!e.data.id) e.data.id = `e${idx}`;
        });

        data.nodes.forEach((n) => {
          if (!n.data.id && n.data.label) {
            n.data.id = n.data.label;
          }
          if (!n.data.label && n.data.id) {
            n.data.label = n.data.id;
          }
        });

        state.rawData = data;
        populateHostSelect(data.nodes);
      })
      .catch((err) => {
        console.error(err);
        alert("Kunde inte läsa nätverksdata: " + err.message);
      })
      .finally(() => {
        showSpinner(false);
      });
  }

  function init() {
    const filters = NM.filters || {};

    const hostSelect = document.getElementById("hostSelect");
    const hostFilterRow = document.getElementById("hostFilterRow");
    const btnApply = document.getElementById("btnApply");
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

    // Summary filter events
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
        const c = document.getElementById("nbDetails");
        if (!c) return;
        if (c.style.display === "none") {
          c.style.display = "block";
          this.textContent = "[–]";
        } else {
          c.style.display = "none";
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
        if (!state.rawData) return;

        const host = hostSelect ? hostSelect.value : "";

        const srcTokens = filters.parseListFilter
          ? filters.parseListFilter(
              document.getElementById("filterSrc").value
            )
          : [];
        const dstTokens = filters.parseListFilter
          ? filters.parseListFilter(
              document.getElementById("filterDst").value
            )
          : [];
        const portMatcher = filters.parsePortFilter
          ? filters.parsePortFilter(
              document.getElementById("filterPort").value.trim()
            )
          : null;
        const excludePublic = document.getElementById("excludePub").checked;
        const ipFilters = filters.parseIpFilters
          ? filters.parseIpFilters(
              document.getElementById("filterIp").value.trim()
            )
          : [];

        const minSep =
          parseInt(
            document.getElementById("minSep").value.trim() || "50",
            10
          ) || 50;
        const sx =
          parseFloat(
            document.getElementById("scaleX").value.trim() || "1.0"
          ) || 1.0;
        const sy =
          parseFloat(
            document.getElementById("scaleY").value.trim() || "1.0"
          ) || 1.0;

        let sub;
        if (host && typeof NM.buildSubgraph === "function") {
          sub = NM.buildSubgraph(
            host,
            srcTokens,
            dstTokens,
            portMatcher,
            excludePublic,
            ipFilters
          );
        } else if (typeof NM.buildGlobalSubgraph === "function") {
          sub = NM.buildGlobalSubgraph(
            srcTokens,
            dstTokens,
            portMatcher,
            excludePublic,
            ipFilters
          );
        } else {
          alert("Filter-funktioner saknas (buildSubgraph / buildGlobalSubgraph).");
          return;
        }

        if (!sub || !Array.isArray(sub.nodes) || !Array.isArray(sub.edges)) {
          alert("Felaktigt subgraph-resultat.");
          return;
        }

        if (typeof NM.drawGraph !== "function") {
          alert("drawGraph saknas (graph.js inte laddad?).");
          return;
        }

        NM.drawGraph({
          nodes: sub.nodes,
          edges: sub.edges,
          minSep,
          sx,
          sy,
        });
      };
    }

    fetchNetworkMap();
  }

  document.addEventListener("DOMContentLoaded", init);
})(window);
