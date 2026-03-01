(function () {
  "use strict";

  const els = {
    loginCard: document.getElementById("loginCard"),
    loginPassword: document.getElementById("loginPassword"),
    btnLogin: document.getElementById("btnLogin"),
    loginMsg: document.getElementById("loginMsg"),

    btnLogout: document.getElementById("btnLogout"),

    settingsCard: document.getElementById("settingsCard"),
    statusCard: document.getElementById("statusCard"),

    zabbixUrl: document.getElementById("zabbixUrl"),
    zabbixToken: document.getElementById("zabbixToken"),
    clearZabbixToken: document.getElementById("clearZabbixToken"),
    zabbixSync: document.getElementById("zabbixSync"),
    zbxTokenStatus: document.getElementById("zbxTokenStatus"),

    netboxUrl: document.getElementById("netboxUrl"),
    netboxToken: document.getElementById("netboxToken"),
    clearNetboxToken: document.getElementById("clearNetboxToken"),
    enableNetbox: document.getElementById("enableNetbox"),
    netboxSync: document.getElementById("netboxSync"),
    nbxTokenStatus: document.getElementById("nbxTokenStatus"),

    reportSync: document.getElementById("reportSync"),

    btnSave: document.getElementById("btnSave"),
    btnReload: document.getElementById("btnReload"),
    saveMsg: document.getElementById("saveMsg"),

    btnSyncZabbix: document.getElementById("btnSyncZabbix"),
    btnSyncNetbox: document.getElementById("btnSyncNetbox"),
    btnGenerateReport: document.getElementById("btnGenerateReport"),

    btnRefreshStatus: document.getElementById("btnRefreshStatus"),
    statusZabbix: document.getElementById("statusZabbix"),
    statusNetbox: document.getElementById("statusNetbox"),
    statusReport: document.getElementById("statusReport"),
  };

  function api(url, opts) {
    const o = Object.assign({
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
    }, opts || {});
    return fetch(url, o).then(async (r) => {
      const txt = await r.text();
      let data = null;
      try { data = txt ? JSON.parse(txt) : null; } catch (e) { data = { raw: txt }; }
      if (!r.ok) {
        const msg = (data && (data.detail || data.error)) ? (data.detail || data.error) : (r.status + " " + r.statusText);
        throw new Error(msg);
      }
      return data;
    });
  }

  function showAuthedUI() {
    els.loginCard.style.display = "none";
    els.settingsCard.style.display = "block";
    els.statusCard.style.display = "block";
    els.btnLogout.style.display = "inline-block";
  }

  function showLoginUI() {
    els.loginCard.style.display = "block";
    els.settingsCard.style.display = "none";
    els.statusCard.style.display = "none";
    els.btnLogout.style.display = "none";
  }

  function fmtStatus(obj) {
    if (!obj) return "";
    const running = obj.running ? "running" : "idle";
    const ok = obj.last_ok === null || obj.last_ok === undefined ? "n/a" : (obj.last_ok ? "ok" : "fail");
    const lastRun = obj.last_run ? new Date(obj.last_run * 1000).toISOString() : "n/a";
    const err = obj.last_error ? String(obj.last_error) : "";
    return `state=${running}\nlast_run=${lastRun}\nlast_ok=${ok}${err ? "\nerror=" + err : ""}`;
  }

  function loadSettings() {
    els.saveMsg.textContent = "";
    return api("/api/admin/settings")
      .then((s) => {
        els.zabbixUrl.value = s.zabbix_url || "";
        els.netboxUrl.value = s.netbox_url || "";
        els.enableNetbox.checked = !!s.enable_netbox;
        els.zabbixSync.value = s.zabbix_sync_seconds || "";
        els.netboxSync.value = s.netbox_sync_seconds || "";
        els.reportSync.value = s.report_sync_seconds || "";

        els.zbxTokenStatus.textContent = s.zabbix_token_set ? "token: set" : "token: not set";
        els.zbxTokenStatus.className = "badge " + (s.zabbix_token_set ? "text-bg-success" : "text-bg-secondary");

        els.nbxTokenStatus.textContent = s.netbox_token_set ? "token: set" : "token: not set";
        els.nbxTokenStatus.className = "badge " + (s.netbox_token_set ? "text-bg-success" : "text-bg-secondary");

        els.zabbixToken.value = "";
        els.netboxToken.value = "";
        els.clearZabbixToken.checked = false;
        els.clearNetboxToken.checked = false;
      });
  }

  function saveSettings() {
    els.saveMsg.textContent = "Saving...";

    const payload = {
      zabbix_url: els.zabbixUrl.value || "",
      netbox_url: els.netboxUrl.value || "",
      enable_netbox: !!els.enableNetbox.checked,
      zabbix_sync_seconds: parseInt(els.zabbixSync.value || "0", 10) || 1,
      netbox_sync_seconds: parseInt(els.netboxSync.value || "0", 10) || 1,
      report_sync_seconds: parseInt(els.reportSync.value || "0", 10) || 1,
    };

    // Tokens: only send when user typed a new one or wants to clear.
    if (els.clearZabbixToken.checked) {
      payload.zabbix_token = "";
    } else if ((els.zabbixToken.value || "").trim().length > 0) {
      payload.zabbix_token = els.zabbixToken.value;
    }

    if (els.clearNetboxToken.checked) {
      payload.netbox_token = "";
    } else if ((els.netboxToken.value || "").trim().length > 0) {
      payload.netbox_token = els.netboxToken.value;
    }

    return api("/api/admin/settings", { method: "POST", body: JSON.stringify(payload) })
      .then(() => {
        els.saveMsg.textContent = "Saved.";
        return loadSettings();
      })
      .catch((e) => {
        els.saveMsg.textContent = "Save failed: " + (e.message || e);
        throw e;
      });
  }

  function refreshStatus() {
    return api("/api/admin/status")
      .then((s) => {
        els.statusZabbix.textContent = fmtStatus(s.zabbix);
        els.statusNetbox.textContent = fmtStatus(s.netbox);
        els.statusReport.textContent = fmtStatus(s.report);
      })
      .catch((e) => {
        els.statusZabbix.textContent = "";
        els.statusNetbox.textContent = "";
        els.statusReport.textContent = "";
        console.error("status error", e);
      });
  }

  function init() {
    api("/api/admin/me")
      .then((me) => {
        if (me && me.authenticated) {
          showAuthedUI();
          return loadSettings().then(refreshStatus);
        }
        showLoginUI();
      })
      .catch(() => {
        showLoginUI();
      });

    els.btnLogin.addEventListener("click", () => {
      const pwd = (els.loginPassword.value || "").trim();
      els.loginMsg.textContent = "";
      if (!pwd) {
        els.loginMsg.textContent = "Enter password.";
        return;
      }
      api("/api/admin/login", { method: "POST", body: JSON.stringify({ password: pwd }) })
        .then(() => {
          els.loginPassword.value = "";
          showAuthedUI();
          return loadSettings().then(refreshStatus);
        })
        .catch((e) => {
          els.loginMsg.textContent = "Login failed: " + (e.message || e);
        });
    });

    els.btnLogout.addEventListener("click", () => {
      api("/api/admin/logout", { method: "POST", body: "{}" })
        .then(() => {
          showLoginUI();
        })
        .catch(() => {
          showLoginUI();
        });
    });

    els.btnReload.addEventListener("click", () => {
      loadSettings().then(refreshStatus);
    });

    els.btnSave.addEventListener("click", () => {
      saveSettings().then(refreshStatus);
    });

    els.btnSyncZabbix.addEventListener("click", () => {
      api("/api/admin/sync/zabbix", { method: "POST", body: "{}" })
        .then(() => {
          els.saveMsg.textContent = "Zabbix sync triggered.";
          setTimeout(refreshStatus, 1000);
        })
        .catch((e) => { els.saveMsg.textContent = "Zabbix sync failed: " + (e.message || e); });
    });

    els.btnSyncNetbox.addEventListener("click", () => {
      api("/api/admin/sync/netbox", { method: "POST", body: "{}" })
        .then(() => {
          els.saveMsg.textContent = "NetBox sync triggered.";
          setTimeout(refreshStatus, 1000);
        })
        .catch((e) => { els.saveMsg.textContent = "NetBox sync failed: " + (e.message || e); });
    });

    els.btnGenerateReport.addEventListener("click", () => {
      api("/api/admin/report/generate", { method: "POST", body: "{}" })
        .then(() => {
          els.saveMsg.textContent = "Report generation triggered.";
          setTimeout(refreshStatus, 1000);
        })
        .catch((e) => { els.saveMsg.textContent = "Report trigger failed: " + (e.message || e); });
    });

    els.btnRefreshStatus.addEventListener("click", refreshStatus);

    // Auto refresh status every 10s when logged in
    setInterval(() => {
      api("/api/admin/me")
        .then((me) => {
          if (me && me.authenticated) {
            refreshStatus();
          }
        })
        .catch(() => { /* ignore */ });
    }, 10000);
  }

  init();
})();
