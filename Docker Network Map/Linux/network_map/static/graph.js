// graph.js
// eslint-disable-next-line no-undef
cytoscape.use(cytoscapeCoseBilkent);

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

  function buildSubgraph(
    host,
    srcTokens,
    dstTokens,
    portMatcher,
    excludePublic,
    ipFilters
  ) {
    const edges = (state.rawData?.edges || []).filter(
      (e) =>
        (e.data.source === host || e.data.target === host) &&
        filters.edgeMatches(
          e.data,
          srcTokens,
          dstTokens,
          portMatcher,
          excludePublic,
          ipFilters
        )
    );

    const ids = new Set([host]);
    edges.forEach((e) => {
      ids.add(e.data.source);
      ids.add(e.data.target);
    });

    const nodes = Array.from(ids)
      .map((id) => (state.rawData?.nodes || []).find((n) => n.data.id === id))
      .filter(Boolean);

    return { nodes, edges };
  }

  function buildGlobalSubgraph(
    srcTokens,
    dstTokens,
    portMatcher,
    excludePublic,
    ipFilters
  ) {
    const edges = (state.rawData?.edges || []).filter((e) =>
      filters.edgeMatches(
        e.data,
        srcTokens,
        dstTokens,
        portMatcher,
        excludePublic,
        ipFilters
      )
    );

    const ids = new Set();
    edges.forEach((e) => {
      ids.add(e.data.source);
      ids.add(e.data.target);
    });

    const nodes = Array.from(ids)
      .map((id) => (state.rawData?.nodes || []).find((n) => n.data.id === id))
      .filter(Boolean);

    return { nodes, edges };
  }

  function drawGraph({ nodes, edges, minSep, sx, sy }) {
    const cyContainer = document.getElementById("cy");
    if (!cyContainer) return;

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
      elements: {
        nodes: nodes.map((n) => ({ data: n.data })),
        edges: edges.map((e) => ({ data: e.data })),
      },
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

      global.addEventListener("resize", () => {
        state.cy.resize();
        state.cy.fit(50);
      });
    });

    state.cy.on("tap", "node", (e) => {
      if (typeof NM.showSummary === "function") {
        NM.showSummary(e.target);
      }
      if (typeof NM.showNetboxInfo === "function") {
        NM.showNetboxInfo(e.target.data("id"));
      }
    });

    state.cy.on("tap", (e) => {
      if (e.target === state.cy) {
        state.cy.elements().removeClass("faded");
        const nbinfo = document.getElementById("nbinfo");
        if (nbinfo) nbinfo.hidden = true;
      }
    });
  }

  NM.buildSubgraph = buildSubgraph;
  NM.buildGlobalSubgraph = buildGlobalSubgraph;
  NM.drawGraph = drawGraph;
})(window);
