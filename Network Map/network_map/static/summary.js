// summary.js
(function (global) {
  "use strict";

  const NM = (global.NetworkMap = global.NetworkMap || {});
  const filters = NM.filters;
  const state =
    (global.NMState =
      global.NMState ||
      {
        rawData: null,
        currentGraph: { nodes: [], edges: [] },
        cy: null,
        summaryData: { incoming: [], outgoing: [] },
      });

  function updateSummaryDisplay() {
    const sumFsrc = document.getElementById("sumFilterSrc");
    const sumFdst = document.getElementById("sumFilterDst");
    const sumFport = document.getElementById("sumFilterPort");
    const summaryContent = document.getElementById("summaryContent");
    if (!sumFsrc || !sumFdst || !sumFport || !summaryContent) return;

    const fs = filters.parseSumTokens(sumFsrc.value);
    const fd = filters.parseSumTokens(sumFdst.value);
    const fp = filters.parseSumTokens(sumFport.value);

    const lines = [];
    let matched = 0;

    function appendSection(title, entries) {
      const sectionLines = [];
      entries.forEach((entry) => {
        const portNum = filters.extractPort(entry.servicePort ?? entry.port);
        if (
          filters.matchTokens(entry.src, fs) &&
          filters.matchTokens(entry.dst, fd) &&
          filters.matchPortTokens(portNum, fp)
        ) {
          sectionLines.push(`${entry.src}	${entry.dst}	${entry.port}`);
          matched += 1;
        }
      });

      if (sectionLines.length) {
        lines.push(title);
        lines.push(...sectionLines);
        lines.push("");
      }
    }

    appendSection("Inkommande:", state.summaryData.incoming || []);
    appendSection("Utgående:", state.summaryData.outgoing || []);

    if (matched === 0) {
      lines.length = 0;
      lines.push("Ingen trafik matchar filtren.");
    } else if (lines.length && lines[lines.length - 1] === "") {
      lines.pop();
    }

    summaryContent.textContent = lines.join("\n");
  }

  function showSummary(node) {
    const summaryBox = document.getElementById("summary");
    const summaryTitle = document.getElementById("summaryTitle");
    if (!summaryBox || !summaryTitle || !state.currentGraph || !state.cy) return;

    state.cy.elements().not(node.closedNeighborhood()).addClass("faded");

    const drawnEdges = state.currentGraph.edges || [];
    const incoming = drawnEdges.filter((edge) => edge.data.target === node.id());
    const outgoing = drawnEdges.filter((edge) => edge.data.source === node.id());

    state.summaryData = {
      incoming: incoming.map((edge) => ({
        src: edge.data.source,
        dst: edge.data.target,
        port: edge.data.label,
        servicePort: edge.data.servicePort,
      })),
      outgoing: outgoing.map((edge) => ({
        src: edge.data.source,
        dst: edge.data.target,
        port: edge.data.label,
        servicePort: edge.data.servicePort,
      })),
    };

    summaryTitle.textContent = `Kommunikation för ${node.data("label")}`;

    const sumFilterSrc = document.getElementById("sumFilterSrc");
    const sumFilterDst = document.getElementById("sumFilterDst");
    const sumFilterPort = document.getElementById("sumFilterPort");
    const summaryFilters = document.getElementById("summaryFilters");
    const summaryContent = document.getElementById("summaryContent");
    const minimizeSummary = document.getElementById("minimizeSummary");

    if (sumFilterSrc) sumFilterSrc.value = "";
    if (sumFilterDst) sumFilterDst.value = "";
    if (sumFilterPort) sumFilterPort.value = "";
    if (summaryFilters) summaryFilters.style.display = "none";
    if (summaryContent) summaryContent.style.display = "none";
    if (minimizeSummary) minimizeSummary.textContent = "[+]";

    summaryBox.hidden = false;
    updateSummaryDisplay();
  }

  NM.updateSummaryDisplay = updateSummaryDisplay;
  NM.showSummary = showSummary;
})(window);
