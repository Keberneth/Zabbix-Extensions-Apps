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
        rawNodeMap: null,
        currentGraph: { nodes: [], edges: [] },
        cy: null,
        resizeHandler: null,
        summaryData: { incoming: [], outgoing: [] },
      });

  function getRawNodeMap() {
    if (state.rawNodeMap instanceof Map) {
      return state.rawNodeMap;
    }

    const map = new Map();
    (state.rawData?.nodes || []).forEach((node) => {
      const id = node && node.data && node.data.id;
      if (id) {
        map.set(id, node);
      }
    });
    state.rawNodeMap = map;
    return map;
  }

  function setCurrentGraph(nodes, edges) {
    state.currentGraph = {
      nodes: Array.isArray(nodes) ? nodes.slice() : [],
      edges: Array.isArray(edges) ? edges.slice() : [],
    };
  }

  function removeResizeHandler() {
    if (state.resizeHandler) {
      global.removeEventListener("resize", state.resizeHandler);
      state.resizeHandler = null;
    }
  }

  function hideDetailPanels() {
    const summary = document.getElementById("summary");
    const nbinfo = document.getElementById("nbinfo");
    if (summary) summary.hidden = true;
    if (nbinfo) nbinfo.hidden = true;
  }

  function buildSubgraph(
    host,
    srcTokens,
    dstTokens,
    portMatcher,
    excludePublic,
    excludeNoisePorts,
    ipFilters
  ) {
    const edges = (state.rawData?.edges || []).filter(
      (edge) =>
        (edge.data.source === host || edge.data.target === host) &&
        filters.edgeMatches(
          edge.data,
          srcTokens,
          dstTokens,
          portMatcher,
          excludePublic,
          excludeNoisePorts,
          ipFilters
        )
    );

    const ids = new Set([host]);
    edges.forEach((edge) => {
      ids.add(edge.data.source);
      ids.add(edge.data.target);
    });

    const nodeMap = getRawNodeMap();
    const nodes = Array.from(ids)
      .map((id) => nodeMap.get(id))
      .filter(Boolean);

    return { nodes, edges };
  }

  function buildGlobalSubgraph(
    srcTokens,
    dstTokens,
    portMatcher,
    excludePublic,
    excludeNoisePorts,
    ipFilters
  ) {
    const edges = (state.rawData?.edges || []).filter((edge) =>
      filters.edgeMatches(
        edge.data,
        srcTokens,
        dstTokens,
        portMatcher,
        excludePublic,
        excludeNoisePorts,
        ipFilters
      )
    );

    const ids = new Set();
    edges.forEach((edge) => {
      ids.add(edge.data.source);
      ids.add(edge.data.target);
    });

    const nodeMap = getRawNodeMap();
    const nodes = Array.from(ids)
      .map((id) => nodeMap.get(id))
      .filter(Boolean);

    return { nodes, edges };
  }

  function drawGraph({
    nodes,
    edges,
    minSep,
    sx,
    sy,
    showNoEdgesAlert = true,
  }) {
    const cyContainer = document.getElementById("cy");
    if (!cyContainer) return false;

    removeResizeHandler();

    if (state.cy) {
      state.cy.destroy();
      state.cy = null;
    }

    if (!Array.isArray(nodes) || !Array.isArray(edges) || !nodes.length || !edges.length) {
      setCurrentGraph([], []);
      state.summaryData = { incoming: [], outgoing: [] };
      hideDetailPanels();
      if (showNoEdgesAlert) {
        alert("Inga kanter matchar filtren.");
      }
      return false;
    }

    setCurrentGraph(nodes, edges);

    const degrees = nodes.map((node) => node.data.degree || 0);
    const minD = Math.min(...degrees);
    const maxD = Math.max(...degrees);
    const nodeSize = minD === maxD ? 40 : `mapData(degree, ${minD}, ${maxD}, 20, 60)`;

    state.cy = cytoscape({
      container: cyContainer,
      elements: {
        nodes: nodes.map((node) => ({ data: node.data })),
        edges: edges.map((edge) => ({ data: edge.data })),
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
            width: nodeSize,
            height: nodeSize,
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
      state.cy.nodes().forEach((node) => {
        const position = node.position();
        node.position({ x: position.x * sx, y: position.y * sy });
      });
      state.cy.fit(50);

      state.resizeHandler = () => {
        if (!state.cy) return;
        state.cy.resize();
        state.cy.fit(50);
      };
      global.addEventListener("resize", state.resizeHandler);
    });

    state.cy.on("tap", "node", (event) => {
      if (typeof NM.showSummary === "function") {
        NM.showSummary(event.target);
      }
      if (typeof NM.showNetboxInfo === "function") {
        NM.showNetboxInfo(event.target.data("id"));
      }
    });

    state.cy.on("tap", (event) => {
      if (event.target === state.cy) {
        state.cy.elements().removeClass("faded");
        const nbinfo = document.getElementById("nbinfo");
        if (nbinfo) nbinfo.hidden = true;
      }
    });

    return true;
  }

  NM.buildSubgraph = buildSubgraph;
  NM.buildGlobalSubgraph = buildGlobalSubgraph;
  NM.drawGraph = drawGraph;
})(window);
