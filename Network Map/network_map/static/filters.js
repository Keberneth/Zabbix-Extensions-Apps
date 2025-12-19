// filters.js
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

  // --- IP helpers ---

  function ipToLong(ip) {
    if (!ip) return 0;
    const parts = ip.split(".");
    if (parts.length !== 4) return 0;
    return (
      ((parseInt(parts[0], 10) << 24) |
        (parseInt(parts[1], 10) << 16) |
        (parseInt(parts[2], 10) << 8) |
        parseInt(parts[3], 10)) >>> 0
    );
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

  // --- Port helpers for MAIN filter (multi ports/ranges) ---

  // Returns a matcher function or null
  function parsePortFilter(str) {
    if (!str) return null;

    const tokens = str
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    const rules = [];

    for (const token of tokens) {
      // Single port, e.g. "443"
      if (/^\d+$/.test(token)) {
        const p = parseInt(token, 10);
        if (Number.isFinite(p)) {
          rules.push({ type: "single", port: p });
        }
        continue;
      }

      // Range, e.g. "1000-2000"
      const m = token.match(/^(\d+)\s*-\s*(\d+)$/);
      if (m) {
        let a = parseInt(m[1], 10);
        let b = parseInt(m[2], 10);
        if (!Number.isFinite(a) || !Number.isFinite(b)) continue;
        if (b < a) [a, b] = [b, a]; // normalize
        rules.push({ type: "range", min: a, max: b });
        continue;
      }

      // ignore invalid tokens
    }

    if (rules.length === 0) return null;

    return function matchesPort(port) {
      if (port == null) return false;

      const p =
        typeof port === "string" ? parseInt(port, 10) : Number(port);
      if (!Number.isFinite(p)) return false;

      return rules.some((rule) => {
        if (rule.type === "single") {
          return p === rule.port;
        }
        // range
        return p >= rule.min && p <= rule.max;
      });
    };
  }

  function extractPort(label) {
    if (!label) return NaN;
    const m = label.match(/(\d+)/);
    return m ? +m[1] : NaN;
  }

  // --- Endpoint filters (Source/Dest) ---

  // "srv1,srv2,192.168.1.10" -> ["srv1","srv2","192.168.1.10"]
  function parseListFilter(str) {
    if (!str) return [];
    return str
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0)
      .map((s) => s.toLowerCase());
  }

  // Match tokens against hostname + IP
  function matchesEndpointFilter(tokens, name, ip) {
    if (!tokens || tokens.length === 0) return true;

    const nameLc = (name || "").toLowerCase();
    const ipLc = (ip || "").toLowerCase();

    return tokens.some((tok) => {
      if (!tok) return false;
      return nameLc.includes(tok) || ipLc.includes(tok);
    });
  }

  // --- Summary token helpers (include/exclude) ---

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

  // --- Edge matcher used by subgraph builders ---

  function edgeMatches(
    data,
    srcTokens,
    dstTokens,
    portMatcher,
    excludePublic,
    ipFilters
  ) {
    const srcIp = data.srcIp || data.src_ip || "";
    const dstIp = data.dstIp || data.dst_ip || "";

    if (!matchesEndpointFilter(srcTokens, data.source, srcIp)) return false;
    if (!matchesEndpointFilter(dstTokens, data.target, dstIp)) return false;

    const port = extractPort(data.label);
    if (portMatcher && !portMatcher(port)) return false;

    if (excludePublic && data.isPublic) return false;

    if (ipFilters && ipFilters.length) {
      if (data.srcIp && matchesIpFilter(data.srcIp, ipFilters)) return false;
      if (data.dstIp && matchesIpFilter(data.dstIp, ipFilters)) return false;
    }

    return true;
  }

  NM.filters = {
    ipToLong,
    parseIpFilters,
    matchesIpFilter,
    parsePortFilter,
    extractPort,
    parseListFilter,
    parseSumTokens,
    matchPortTokens,
    matchTokens,
    matchesEndpointFilter,
    edgeMatches,
  };
})(window);
