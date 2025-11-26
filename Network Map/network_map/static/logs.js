(function () {
  "use strict";

  let allLines = [];

  document.addEventListener("DOMContentLoaded", () => {
    const logFileSelect = document.getElementById("logFile");
    const filterTextInput = document.getElementById("filterText");
    const filterLevelSelect = document.getElementById("filterLevel");
    const btnReload = document.getElementById("btnReload");
    const btnClear = document.getElementById("btnClearFilter");

    btnReload.addEventListener("click", () => loadLog());
    btnClear.addEventListener("click", () => {
      filterTextInput.value = "";
      filterLevelSelect.value = "";
      applyFilters();
    });

    filterTextInput.addEventListener("input", applyFilters);
    filterLevelSelect.addEventListener("change", applyFilters);
    logFileSelect.addEventListener("change", () => loadLog());

    // initial load
    loadLog();
  });

  function setStatus(msg, isError) {
    const el = document.getElementById("status");
    el.textContent = msg || "";
    el.style.color = isError ? "red" : "#555";
  }

  function loadLog() {
    const logFileSelect = document.getElementById("logFile");
    const fileName = logFileSelect.value || "network_map.log";
    const url = "/logs/" + encodeURIComponent(fileName);

    setStatus("Laddar " + fileName + " …", false);
    const logOutput = document.getElementById("logOutput");
    logOutput.textContent = "";

    fetch(url)
      .then((resp) => {
        if (!resp.ok) {
          throw new Error("HTTP " + resp.status + " " + resp.statusText);
        }
        return resp.text();
      })
      .then((text) => {
        let lines = text.split(/\r?\n/);
        if (lines.length && !lines[lines.length - 1].trim()) {
          lines.pop();
        }

        const MAX_LINES = 5000;
        if (lines.length > MAX_LINES) {
          lines = lines.slice(-MAX_LINES);
        }

        allLines = lines;
        setStatus(
          `Laddade ${lines.length} rader från ${fileName} (visar max ${MAX_LINES})`,
          false
        );
        applyFilters();
      })
      .catch((err) => {
        allLines = [];
        setStatus("Kunde inte läsa loggfilen: " + err.message, true);
      });
  }

  function applyFilters() {
    const filterText = (document.getElementById("filterText").value || "").toLowerCase();
    const filterLevel = document.getElementById("filterLevel").value;
    const logOutput = document.getElementById("logOutput");

    if (!allLines.length) {
      logOutput.textContent = "";
      return;
    }

    const filtered = allLines.filter((line) => {
      if (!line.trim()) return false;

      if (filterLevel) {
        const m = line.match(/\[(\w+)\]/); // e.g. [INFO]
        const level = m ? m[1] : "";
        if (level !== filterLevel) return false;
      }

      if (filterText && !line.toLowerCase().includes(filterText)) {
        return false;
      }

      return true;
    });

    logOutput.textContent = filtered.join("\n");
  }
})();
