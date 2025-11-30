// report.js
(function (global) {
  "use strict";

  const NM = (global.NetworkMap = global.NetworkMap || {});

  function handleDownloadReports() {
    const btn = document.getElementById("btnDownloadReport");
    const progressBar = document.getElementById("progressBar");
    const btnText = document.getElementById("btnText");
    if (!btn || !progressBar || !btnText) return;

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
        const url = global.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.style.display = "none";
        a.href = url;
        a.download = "network_reports.zip";
        document.body.appendChild(a);
        a.click();
        a.remove();
        global.URL.revokeObjectURL(url);
      })
      .catch((err) => {
        console.error("Report download error:", err);
        alert("Kunde inte ladda ner rapporterna.");
      })
      .finally(() => {
        clearInterval(interval);
        progressBar.style.width = "0%";
        btn.disabled = false;
        btnText.textContent = "Ladda ner Rapport";
      });
  }

  NM.handleDownloadReports = handleDownloadReports;
})(window);
