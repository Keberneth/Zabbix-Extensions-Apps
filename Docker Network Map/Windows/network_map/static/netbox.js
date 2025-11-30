// netbox.js
(function (global) {
  "use strict";

  const NM = (global.NetworkMap = global.NetworkMap || {});

  function showNetboxInfo(hostname) {
    const nb = document.getElementById("nbinfo");
    const title = document.getElementById("nbTitle");
    const list = document.getElementById("nbDetails");

    if (!nb || !title || !list) return;

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
                  (s.protocol.label ||
                    s.protocol.value ||
                    s.protocol)) ||
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

  NM.showNetboxInfo = showNetboxInfo;
})(window);
