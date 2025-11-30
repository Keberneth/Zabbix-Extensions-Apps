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

    if (state.summaryData.incoming.length) {
      lines.push("Inkommande:");
      state.summaryData.incoming.forEach((e) => {
        const pNum = filters.extractPort(e.port);
        if (
          filters.matchTokens(e.src, fs) &&
          filters.matchTokens(e.dst, fd) &&
          filters.matchPortTokens(pNum, fp)
        ) {
          lines.push(`${e.src}\t${e.dst}\t${e.port}`);
        }
      });
      lines.push("");
    }

    if (state.summaryData.outgoing.length) {
      lines.push("Utgående:");
      state.summaryData.outgoing.forEach((e) => {
        const pNum = filters.extractPort(e.port);
        if (
          filters.matchTokens(e.src, fs) &&
          filters.matchTokens(e.dst, fd) &&
          filters.matchPortTokens(pNum, fp)
        ) {
          lines.push(`${e.src}\t${e.dst}\t${e.port}`);
        }
      });
      lines.push("");
    }

    if (!lines.length) {
      lines.push("Ingen trafik matchar filtren.");
    }

    summaryContent.textContent = lines.join("\n");
  }

  function showSummary(node) {
    const summaryBox = document.getElementById("summary");
    const summaryTitle = document.getElementById("summaryTitle");
    if (!summaryBox || !summaryTitle || !state.rawData || !state.cy) return;

    // Grey-out everything except this node and its neighbours
    state.cy.elements().not(node.closedNeighborhood()).addClass("faded");

    const inc = state.rawData.edges.filter(
      (edge) => edge.data.target === node.id()
    );
    const out = state.rawData.edges.filter(
      (edge) => edge.data.source === node.id()
    );

    state.summaryData = {
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

    summaryTitle.textContent = `Kommunikation för ${node.data("label")}`;

    // Reset filters and collapse
    document.getElementById("sumFilterSrc").value = "";
    document.getElementById("sumFilterDst").value = "";
    document.getElementById("sumFilterPort").value = "";
    document.getElementById("summaryFilters").style.display = "none";
    document.getElementById("summaryContent").style.display = "none";
    document.getElementById("minimizeSummary").textContent = "[+]";

    summaryBox.hidden = false;
    updateSummaryDisplay();
  }

  NM.updateSummaryDisplay = updateSummaryDisplay;
  NM.showSummary = showSummary;
})(window);
