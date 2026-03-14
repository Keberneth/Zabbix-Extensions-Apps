// filters.js
(function (global) {
  "use strict";

  const NM = (global.NetworkMap = global.NetworkMap || {});
  const DEFAULT_RPC_PORTS = new Set([111, 135, 593]);
  const DEFAULT_DYNAMIC_PORT_MIN = 49152;

  function normalizePort(port) {
    if (port === null || port === undefined || port === "") {
      return null;
    }

    const value =
      typeof port === "number"
        ? port
        : Number.parseInt(String(port).trim(), 10);

    if (!Number.isInteger(value) || value < 0 || value > 65535) {
      return null;
    }

    return value;
  }

  // --- IP helpers ---

  function ipToLong(ip) {
    if (typeof ip !== "string") return null;

    const parts = ip.trim().split(".");
    if (parts.length !== 4) return null;

    let value = 0;
    for (const part of parts) {
      if (!/^\d+$/.test(part)) return null;
      const octet = Number(part);
      if (!Number.isInteger(octet) || octet < 0 || octet > 255) {
        return null;
      }
      value = (value << 8) | octet;
    }

    return value >>> 0;
  }

  function buildCidrMask(prefix) {
    if (!Number.isInteger(prefix) || prefix < 0 || prefix > 32) {
      return null;
    }

    if (prefix === 0) return 0;
    if (prefix === 32) return 0xffffffff >>> 0;
    return (0xffffffff << (32 - prefix)) >>> 0;
  }

  function parseIpFilters(str) {
    if (!str) return [];

    return str
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .map((token) => {
        const range = token.match(/^([\d.]+)\s*-\s*([\d.]+)$/);
        if (range) {
          let start = ipToLong(range[1]);
          let end = ipToLong(range[2]);
          if (start === null || end === null) return null;
          if (start > end) [start, end] = [end, start];
          return { type: "range", start, end };
        }

        const cidr = token.match(/^([\d.]+)\/(\d{1,2})$/);
        if (cidr) {
          const baseIp = ipToLong(cidr[1]);
          const prefix = Number(cidr[2]);
          const mask = buildCidrMask(prefix);
          if (baseIp === null || mask === null) return null;
          return { type: "cidr", base: baseIp & mask, mask };
        }

        const value = ipToLong(token);
        if (value === null) return null;
        return { type: "exact", value };
      })
      .filter(Boolean);
  }

  function matchesIpFilter(ipStr, filters) {
    const num = ipToLong(ipStr);
    if (num === null) return false;

    return filters.some(
      (f) =>
        (f.type === "exact" && num === f.value) ||
        (f.type === "cidr" && (num & f.mask) === f.base) ||
        (f.type === "range" && num >= f.start && num <= f.end)
    );
  }

  // --- Port helpers for MAIN filter (multi ports/ranges) ---

  function parsePortFilter(str) {
    if (!str) return null;

    const tokens = str
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    const rules = [];

    for (const token of tokens) {
      if (/^\d+$/.test(token)) {
        const port = normalizePort(token);
        if (port !== null) {
          rules.push({ type: "single", port });
        }
        continue;
      }

      const match = token.match(/^(\d+)\s*-\s*(\d+)$/);
      if (match) {
        let min = normalizePort(match[1]);
        let max = normalizePort(match[2]);
        if (min === null || max === null) continue;
        if (max < min) [min, max] = [max, min];
        rules.push({ type: "range", min, max });
      }
    }

    if (rules.length === 0) return null;

    return function matchesPort(port) {
      const value = normalizePort(port);
      if (value === null) return false;

      return rules.some((rule) => {
        if (rule.type === "single") {
          return value === rule.port;
        }
        return value >= rule.min && value <= rule.max;
      });
    };
  }

  function extractPort(value) {
    const direct = normalizePort(value);
    if (direct !== null) return direct;

    if (value === null || value === undefined || value === "") {
      return NaN;
    }

    const match = String(value).match(/(\d{1,5})/);
    const parsed = match ? normalizePort(match[1]) : null;
    return parsed === null ? NaN : parsed;
  }

  function isDefaultHiddenPort(port) {
    const value = normalizePort(port);
    if (value === null) return false;
    return DEFAULT_RPC_PORTS.has(value) || value >= DEFAULT_DYNAMIC_PORT_MIN;
  }

  // --- Endpoint filters (Source/Dest) ---

  function parseListFilter(str) {
    if (!str) return [];
    return str
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0)
      .map((s) => s.toLowerCase());
  }

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
      .map((raw) => {
        const exclude = raw.startsWith("!");
        const token = exclude ? raw.slice(1) : raw;
        const range = token.match(/^(\d+)\s*-\s*(\d+)$/);

        if (range) {
          let a = Number(range[1]);
          let b = Number(range[2]);
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

    const includes = tokens.filter((t) => !t.exclude);
    const excludes = tokens.filter((t) => t.exclude);
    const lower = (text || "").toLowerCase();

    let ok = true;
    if (includes.length) {
      ok = includes.some((t) => lower.includes(String(t.value || "").toLowerCase()));
    }
    if (!ok) return false;

    if (
      excludes.length &&
      excludes.some((t) => lower.includes(String(t.value || "").toLowerCase()))
    ) {
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
    excludeNoisePorts,
    ipFilters
  ) {
    const srcIp = data.srcIp || data.src_ip || "";
    const dstIp = data.dstIp || data.dst_ip || "";

    if (!matchesEndpointFilter(srcTokens, data.source, srcIp)) return false;
    if (!matchesEndpointFilter(dstTokens, data.target, dstIp)) return false;

    const port = extractPort(data.servicePort ?? data.label);
    if (excludeNoisePorts && isDefaultHiddenPort(port)) return false;
    if (portMatcher && !portMatcher(port)) return false;

    if (excludePublic && data.isPublic) return false;

    if (ipFilters && ipFilters.length) {
      if (srcIp && matchesIpFilter(srcIp, ipFilters)) return false;
      if (dstIp && matchesIpFilter(dstIp, ipFilters)) return false;
    }

    return true;
  }

  NM.filters = {
    ipToLong,
    parseIpFilters,
    matchesIpFilter,
    normalizePort,
    parsePortFilter,
    extractPort,
    isDefaultHiddenPort,
    parseListFilter,
    parseSumTokens,
    matchPortTokens,
    matchTokens,
    matchesEndpointFilter,
    edgeMatches,
  };
})(window);
