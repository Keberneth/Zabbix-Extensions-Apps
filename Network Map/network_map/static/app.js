// eslint-disable-next-line no-undef
cytoscape.use(cytoscapeCoseBilkent);

(function () {
  "use strict";

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
      // ignore if localStorage is not available
    }
  }

  function applyDarkMode(enabled, controls, summary, nbinfo, cyContainer) {
    if (document.body) {
      document.body.classList.toggle("dark-mode", enabled);
    }
    if (controls) {
      controls.classList.toggle("dark-mode", enabled);
    }
    if (summary) {
      summary.classList.toggle("dark-mode", enabled);
    }
    if (nbinfo) {
      nbinfo.classList.toggle("dark-mode", enabled);
    }
    if (cyContainer) {
      cyContainer.classList.toggle("dark-mode", enabled);
    }
  }

  const state = {
    rawData: null,
    cy: null,
    summaryData: { incoming: [], outgoing: [] },
  };

  document.addEventListener("DOMContentLoaded", init);

  function init() {
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

    // Apply saved dark mode preference on load
    const initialDarkMode = loadDarkModePreference();
    if (initialDarkMode) {
      applyDarkMode(true, controls, summary, nbinfo, cyContainer);
    }

    // Hide host selector row by default (as in original code)
    if (hostFilterRow) {
      hostFilterRow.style.display = "none";
    }

    // Summary filter events
    [sumFsrc, sumFdst, sumFport].forEach((el) => {
      el.addEventListener("input", updateSummaryDisplay);
    });

    closeSummary.onclick = () => {
      document.getElementById("summary").hidden = true;
    };

    minimizeSummary.onclick = () => {
      const filters = document.getElementById("summaryFilters");
      const content = document.getElementById("summaryContent");
      const btn = document.getElementById("minimizeSummary");
      if (filters.style.display === "none") {
        filters.style.display = "block";
        content.style.display = "block";
        btn.textContent = "[–]";
      } else {
        filters.style.display = "none";
        content.style.display = "none";
        btn.textContent = "[+]";
      }
    };

    closeNb.onclick = () => {
      document.getElementById("nbinfo").hidden = true;
    };

    minimizeNb.onclick = function () {
      const c = document.getElementById("nbDetails");
      if (c.style.display === "none") {
        c.style.display = "block";
        this.textContent = "[–]";
      } else {
        c.style.display = "none";
        this.textContent = "[+]";
      }
    };

    btnApply.onclick = () => {
      if (!state.rawData) return;
      const host = hostSelect.value;

      const srcF = document.getElementById("filterSrc").value.trim();
      const dstF = document.getElementById("filterDst").value.trim();
      const portF = parsePortFilter(
        document.getElementById("filterPort").value.trim()
      );
      const excludePublic = document.getElementById("excludePub").checked;
      const ipFilters = parseIpFilters(
        document.getElementById("filterIp").value.trim()
      );
      const minSep =
        parseInt(document.getElementById("minSep").value.trim(), 10) || 50;
      const sx =
        parseFloat(document.getElementById("scaleX").value.trim()) || 1.0;
      const sy =
        parseFloat(document.getElementById("scaleY").value.trim()) || 1.0;

      const sub = host
        ? buildSubgraph(host, srcF, dstF, portF, excludePublic, ipFilters)
        : buildGlobalSubgraph(srcF, dstF, portF, excludePublic, ipFilters);

      drawGraph({
        nodes: sub.nodes,
        edges: sub.edges,
        minSep,
        sx,
        sy,
      });
    };

    btnDownloadReport.onclick = handleDownloadReports;

    toggleDarkMode.onclick = () => {
      const currentlyEnabled = document.body.classList.contains("dark-mode");
      const newEnabled = !currentlyEnabled;
      applyDarkMode(newEnabled, controls, summary, nbinfo, cyContainer);
      saveDarkModePreference(newEnabled);
    };

    fetchNetworkMap();
  }

  // --- Fetch network map data from backend ---

  function fetchNetworkMap() {
    showSpinner(true);
    fetch("/api/network_map")
      .then((r) => (r.ok ? r.json() : Promise.reject("HTTP " + r.status)))
      .then((data) => {
        // sanitize / add edge ids
        data.edges = (data.edges || []).filter(
          (e) => e.data && e.data.source && e.data.target
        );
        data.edges.forEach((e, i) => {
          e.data.id = `${e.data.source}_${e.data.target}_${i}`;
        });
        state.rawData = data;
        populateHostDropdown(data.nodes || []);
      })
      .catch((err) => {
        console.error("Failed to load /api/network_map:", err);
        alert("Kunde inte läsa nätverkskartan: " + err);
      })
      .finally(() => {
        showSpinner(false);
      });
  }

  // --- Host dropdown ---

  function populateHostDropdown(nodes) {
    const sel = document.getElementById("hostSelect");
    sel.innerHTML =
      '<option value="">— Ingen, globalt filter —</option>';
    nodes
      .map((n) => n.data.id)
      .sort()
      .forEach((id) => {
        const o = document.createElement("option");
        o.value = id;
        o.textContent = id;
        sel.appendChild(o);
      });
  }

  // --- IP / port filter helpers ---

  function ipToLong(ip) {
    return ip
      .split(".")
      .reduce((acc, octet) => ((acc << 8) + parseInt(octet, 10)) >>> 0, 0);
  }

  function parseIpFilters(str) {
    if (!str) return [];
    return str
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .map((s) => {
        const range = s.match(/^([\d.]+)\s*-\s*([\d.]+)$/);
        if (range) {
          let a = ipToLong(range[1]);
          let b = ipToLong(range[2]);
          if (a > b) [a, b] = [b, a];
          return { type: "range", start: a, end: b };
        }
        const cidr = s.match(/^([\d.]+)\/(\d+)$/);
        if (cidr) {
          const mask = (~((1 << (32 - +cidr[2])) - 1)) >>> 0;
          const base = ipToLong(cidr[1]) & mask;
          return { type: "cidr", base, mask };
        }
        const v = ipToLong(s);
        if (!Number.isNaN(v)) return { type: "exact", value: v };
        return null;
      })
      .filter(Boolean);
  }

  function matchesIpFilter(ipStr, filters) {
    const num = ipToLong(ipStr);
    return filters.some(
      (f) =>
        (f.type === "exact" && num === f.value) ||
        (f.type === "cidr" && (num & f.mask) === f.base) ||
        (f.type === "range" && num >= f.start && num <= f.end)
    );
  }

  function parsePortFilter(str) {
    if (!str) return null;
    const r = str.match(/^(\d+)\s*-\s*(\d+)$/);
    if (r) return { type: "range", min: +r[1], max: +r[2] };
    const v = parseInt(str, 10);
    return Number.isNaN(v) ? null : { type: "exact", value: v };
  }

  function extractPort(label) {
    if (!label) return NaN;
    const m = label.match(/(\d+)/);
    return m ? +m[1] : NaN;
  }

  function partialMatch(val, filter) {
    if (!filter) return true;
    return val.toLowerCase().includes(filter.toLowerCase());
  }

  // --- Summary token parsing (include/exclude, ranges) ---

  function parseSumTokens(str) {
    if (!str) return [];
    return str
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .map((s) => {
        const exclude = s.startsWith("!");
        const token = exclude ? s.slice(1) : s;
        if (token.includes("-")) {
          const [a, b] = token.split("-").map(Number);
          return {
            range: [Math.min(a, b), Math.max(a, b)],
            exclude,
          };
        }
        return { value: token, exclude };
      });
  }

  function matchPortTokens(portNum, tokens) {
    if (!tokens.length) return true;
    const includes = tokens.filter((t) => !t.exclude);
    const excludes = tokens.filter((t) => t.exclude);

    let ok = true;
    if (includes.length) {
      ok = includes.some((t) =>
        t.range
          ? portNum >= t.range[0] && portNum <= t.range[1]
          : portNum === Number(t.value)
      );
    }
    if (!ok) return false;

    if (
      excludes.length &&
      excludes.some((t) =>
        t.range
          ? portNum >= t.range[0] && portNum <= t.range[1]
          : portNum === Number(t.value)
      )
    ) {
      return false;
    }
    return true;
  }

  function matchTokens(text, tokens) {
    if (!tokens.length) return true;
    const inc = tokens.filter((t) => !t.exclude);
    const exc = tokens.filter((t) => t.exclude);
    const lower = text.toLowerCase();

    let ok = true;
    if (inc.length) {
      ok = inc.some((t) => lower.includes(t.value.toLowerCase()));
    }
    if (!ok) return false;

    if (exc.length && exc.some((t) => lower.includes(t.value.toLowerCase()))) {
      return false;
    }
    return true;
  }

  // --- Edge filters for main graph ---

  function edgeMatches(data, srcF, dstF, portF, excludePublic, ipFilters) {
    if (srcF && !partialMatch(data.source, srcF)) return false;
    if (dstF && !partialMatch(data.target, dstF)) return false;

    const port = extractPort(data.label);
    if (portF) {
      if (portF.type === "exact" && port !== portF.value) return false;
      if (
        portF.type === "range" &&
        (Number.isNaN(port) ||
          port < portF.min ||
          port > portF.max)
      ) {
        return false;
      }
    }

    if (excludePublic && data.isPublic) return false;

    if (ipFilters.length) {
      if (data.srcIp && matchesIpFilter(data.srcIp, ipFilters)) return false;
      if (data.dstIp && matchesIpFilter(data.dstIp, ipFilters)) return false;
    }

    return true;
  }

  function buildSubgraph(host, srcF, dstF, portF, excludePublic, ipFilters) {
    const edges = state.rawData.edges.filter(
      (e) =>
        (e.data.source === host || e.data.target === host) &&
        edgeMatches(e.data, srcF, dstF, portF, excludePublic, ipFilters)
    );
    const ids = new Set([host]);
    edges.forEach((e) => {
      ids.add(e.data.source);
      ids.add(e.data.target);
    });
    const nodes = Array.from(ids).map((id) =>
      state.rawData.nodes.find((n) => n.data.id === id)
    );
    return { nodes, edges };
  }

  function buildGlobalSubgraph(srcF, dstF, portF, excludePublic, ipFilters) {
    const portTokens = parseSumTokens(
      document.getElementById("filterPort").value.trim()
    );
    const edges = state.rawData.edges.filter((e) => {
      const d = e.data;
      const portNum = extractPort(d.label);
      return (
        edgeMatches(d, srcF, dstF, portF, excludePublic, ipFilters) &&
        matchPortTokens(portNum, portTokens)
      );
    });

    const ids = new Set();
    edges.forEach((e) => {
      ids.add(e.data.source);
      ids.add(e.data.target);
    });
    const nodes = Array.from(ids).map((id) =>
      state.rawData.nodes.find((n) => n.data.id === id)
    );
    return { nodes, edges };
  }

  // --- Drawing the graph ---

  function drawGraph({ nodes, edges, minSep, sx, sy }) {
    const cyContainer = document.getElementById("cy");

    if (state.cy) {
      state.cy.destroy();
      state.cy = null;
    }

    if (!nodes.length || !edges.length) {
      alert("Inga kanter matchar filtren.");
      return;
    }

    const degrees = nodes.map((n) => n.data.degree || 0);
    const minD = Math.min(...degrees);
    const maxD = Math.max(...degrees);

    state.cy = cytoscape({
      container: cyContainer,
      elements: { nodes, edges },
      layout: {
        name: "cose-bilkent",
        animate: false,
        fit: false,
        idealEdgeLength: minSep * 1.5,
        nodeSeparation: minSep,
        avoidOverlap: true,
      },
      style: [
        {
          selector: "node",
          style: {
            shape: "ellipse",
            width: `mapData(degree, ${minD}, ${maxD}, 20, 60)`,
            height: `mapData(degree, ${minD}, ${maxD}, 20, 60)`,
            label: "data(label)",
            "background-color": "data(color)",
            color: "#fff",
            "text-valign": "center",
            "text-outline-width": 2,
            "text-outline-color": "#333",
          },
        },
        {
          selector: "edge",
          style: {
            width: 1,
            "line-color": "#999",
            "target-arrow-shape": "triangle",
            "target-arrow-color": "#999",
            "curve-style": "bezier",
            label: "data(label)",
            "font-size": 8,
          },
        },
        {
          selector: ".faded",
          style: {
            opacity: 0.1,
          },
        },
      ],
    });

    state.cy.ready(() => {
      state.cy.nodes().forEach((n) => {
        const p = n.position();
        n.position({ x: p.x * sx, y: p.y * sy });
      });
      state.cy.fit(50);

      window.addEventListener("resize", () => {
        state.cy.resize();
        state.cy.fit(50);
      });
    });

    state.cy.on("tap", "node", (e) => {
      showSummary(e.target);
      showNetboxInfo(e.target.data("id"));
    });

    state.cy.on("tap", (e) => {
      if (e.target === state.cy) {
        state.cy.elements().removeClass("faded");
        document.getElementById("nbinfo").hidden = true;
      }
    });
  }

  // --- Summary panel ---

  function updateSummaryDisplay() {
    const sumFsrc = document.getElementById("sumFilterSrc");
    const sumFdst = document.getElementById("sumFilterDst");
    const sumFport = document.getElementById("sumFilterPort");
    const summaryContent = document.getElementById("summaryContent");

    const fs = parseSumTokens(sumFsrc.value);
    const fd = parseSumTokens(sumFdst.value);
    const fp = parseSumTokens(sumFport.value);

    const lines = [];

    if (state.summaryData.incoming.length) {
      lines.push("Inkommande:");
      state.summaryData.incoming.forEach((e) => {
        const pNum = extractPort(e.port);
        if (
          matchTokens(e.src, fs) &&
          matchTokens(e.dst, fd) &&
          matchPortTokens(pNum, fp)
        ) {
          lines.push(`${e.src}\t${e.dst}\t${e.port}`);
        }
      });
    }

    if (state.summaryData.outgoing.length) {
      if (lines.length) lines.push("");
      lines.push("Utgående:");
      state.summaryData.outgoing.forEach((e) => {
        const pNum = extractPort(e.port);
        if (
          matchTokens(e.src, fs) &&
          matchTokens(e.dst, fd) &&
          matchPortTokens(pNum, fp)
        ) {
          lines.push(`${e.src}\t${e.dst}\t${e.port}`);
        }
      });
    }

    summaryContent.textContent = lines.join("\n");
  }

  function showSummary(node) {
    const summaryBox = document.getElementById("summary");
    const summaryTitle = document.getElementById("summaryTitle");

    state.cy.elements().not(node.closedNeighborhood()).addClass("faded");

    const inc = state.rawData.edges.filter(
      (edge) => edge.data.target === node.id()
    );
    const out = state.rawData.edges.filter(
      (edge) => edge.data.source === node.id()
    );

    state.summaryData = {
      title: `Kommunikation för ${node.data("label")}`,
      incoming: inc.map((e) => ({
        src: e.data.source,
        dst: e.data.target,
        port: e.data.label,
      })),
      outgoing: out.map((e) => ({
        src: e.data.source,
        dst: e.data.target,
        port: e.data.label,
      })),
    };

    summaryTitle.textContent = state.summaryData.title;

    // reset filters and start collapsed, as in original
    document.getElementById("sumFilterSrc").value = "";
    document.getElementById("sumFilterDst").value = "";
    document.getElementById("sumFilterPort").value = "";
    document.getElementById("summaryFilters").style.display = "none";
    document.getElementById("summaryContent").style.display = "none";
    document.getElementById("minimizeSummary").textContent = "[+]";

    summaryBox.hidden = false;
    updateSummaryDisplay();
  }

  // --- NetBox info panel ---

  function showNetboxInfo(hostname) {
    const nb = document.getElementById("nbinfo");
    const title = document.getElementById("nbTitle");
    const list = document.getElementById("nbDetails");

    nb.hidden = false;
    title.textContent = `Info: ${hostname}`;
    list.innerHTML = "<li>Hämtar data från NetBox…</li>";

    const vmUrl = `/api/netbox/vm?name=${encodeURIComponent(hostname)}`;
    const svcsUrl = `/api/netbox/services-by-vm?name=${encodeURIComponent(
      hostname
    )}`;

    Promise.all([fetch(vmUrl), fetch(svcsUrl)])
      .then(([rVm, rSvcs]) => {
        if (!rVm.ok) {
          throw new Error("VM saknas");
        }
        return Promise.all([rVm.json(), rSvcs.json()]);
      })
      .then(([vm, svcs]) => {
        const cf = vm.custom_fields || {};
        const html = [];

        const vcpus = vm.vcpus != null ? vm.vcpus : "–";
        const ramGb =
          vm.memory != null ? (vm.memory / 1024).toFixed(1) + " GB" : "–";
        const diskGb =
          vm.disk != null ? (vm.disk / 1024).toFixed(1) + " GB" : "–";

        html.push(`<li>CPU: ${vcpus} vCPU</li>`);
        html.push(`<li>RAM: ${ramGb}</li>`);
        html.push(`<li>Disk: ${diskGb}</li>`);
        html.push(`<li>Patch-fönster: ${cf.patch_window || "–"}</li>`);
        html.push(`<li>OS: ${cf.operating_system || "–"}</li>`);
        html.push(`<li>EOL: ${cf.operating_system_EOL || "–"}</li>`);

        const roleDisplay =
          (vm.role && (vm.role.display || vm.role.name)) || "–";
        html.push(`<li>Role: <strong>${roleDisplay}</strong></li>`);

        if (Array.isArray(cf.ha_with_server) && cf.ha_with_server.length) {
          const links = cf.ha_with_server.map((h) => {
            const url = h.url || h.display_url || "#";
            const text = h.display || h.name || url;
            return `<a href="${url}" target="_blank" rel="noopener noreferrer">${text}</a>`;
          });
          html.push(`<li>HA: ${links.join(", ")}</li>`);
        }

        if (svcs && svcs.length) {
          const lst = svcs
            .map((s) => {
              const proto =
                (s.protocol &&
                  (s.protocol.label || s.protocol.value || s.protocol)) ||
                "-";
              const ports = Array.isArray(s.ports)
                ? s.ports.join(",")
                : s.ports || "-";
              const name = s.name || s.display || "(okänd tjänst)";
              return `<li>${name} (${proto}/${ports})</li>`;
            })
            .join("");
          html.push(`<li>Tjänster:<ul>${lst}</ul></li>`);
        }

        const vmUrlFull = vm.display_url || vm.url || "#";
        html.push(
          `<li><a href="${vmUrlFull}" target="_blank" rel="noopener noreferrer">Öppna i NetBox</a></li>`
        );

        list.innerHTML = html.join("");
      })
      .catch((err) => {
        list.innerHTML = `<li style="color:red">Fel: ${
          err.message || err
        }</li>`;
      });
  }

  // --- Report download button with progress bar ---

  function handleDownloadReports() {
    const btn = document.getElementById("btnDownloadReport");
    const progressBar = document.getElementById("progressBar");
    const btnText = document.getElementById("btnText");

    btn.disabled = true;
    btnText.textContent = "Downloading...";

    let progress = 0;
    const interval = setInterval(() => {
      progress = (progress + 10) % 100;
      progressBar.style.width = progress + "%";
    }, 200);

    fetch("/api/reports/download_zip")
      .then((response) => {
        if (!response.ok) {
          throw new Error("Network response was not ok");
        }
        return response.blob();
      })
      .then((blob) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.style.display = "none";
        a.href = url;
        a.download = "network_reports.zip";
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      })
      .catch((err) => {
        alert("Failed to download reports: " + err);
      })
      .finally(() => {
        clearInterval(interval);
        progressBar.style.width = "100%";
        setTimeout(() => {
          progressBar.style.width = "0%";
          btn.disabled = false;
          btnText.textContent = "Ladda ner Rapport";
        }, 500);
      });
  }

  // --- Spinner ---

  function showSpinner(show) {
    const spinner = document.getElementById("spinner");
    if (!spinner) return;
    spinner.style.display = show ? "block" : "none";
  }
})();
