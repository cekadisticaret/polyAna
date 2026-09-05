(function () {
  "use strict";

  var cfg = window.__NX_NEAR__;
  if (!cfg || typeof L === "undefined") return;

  var pins = cfg.pins || [];
  var center = [cfg.lat, cfg.lng];
  var radiusM = cfg.radiusM || 0;
  var usedFallback = !!cfg.usedFallback;
  var catFilter = cfg.cat || "";

  var catColor = {
    food: "#e11d48",
    cafe: "#16a34a",
    event: "#2563eb",
    visit: "#ca8a04",
    hotel: "#7c3aed",
    concert: "#ea580c",
    vet: "#0d9488",
    hospital: "#dc2626",
    market: "#4f46e5",
    shop: "#9333ea",
    camp: "#65a30d",
    school: "#7c2d12",
  };

  var catEmoji = {
    food: "🍽",
    visit: "🌿",
    hotel: "🏨",
    camp: "⛺",
    shop: "🛍",
    market: "🛒",
    sport: "💪",
    family: "👨‍👩‍👧",
    concert: "🎵",
    theater: "🎭",
    cinema: "🎬",
    fun: "🎳",
    event: "📅",
    hospital: "🏥",
    vet: "🐾",
    school: "🎓",
  };

  function colorFor(p) {
    if ((p.subcategory || "") === "cafe") return catColor.cafe;
    return catColor[p.category] || "#2563eb";
  }

  function fmtDist(m) {
    if (m == null) return "—";
    return m >= 1000 ? (m / 1000).toFixed(1) + " km" : m + " m";
  }

  function priceLabel(band) {
    if (!band) return "";
    if (/^\d+$/.test(band)) return "₺".repeat(Math.min(4, parseInt(band, 10)));
    return band;
  }

  function mapUrl(lat, lng) {
    var q = new URLSearchParams();
    q.set("near", "1");
    if (catFilter) q.set("cat", catFilter);
    if (radiusM) q.set("r", String(radiusM));
    q.set("lat", lat.toFixed(5));
    q.set("lng", lng.toFixed(5));
    return "/harita?" + q.toString();
  }

  var mapEl = document.getElementById("nx-map");
  if (!mapEl) return;

  var stageEl = document.getElementById("nx-stage");
  var mobileMq = window.matchMedia("(max-width: 820px)");
  var isMobile = mobileMq.matches;
  var toggleBtn = document.getElementById("nx-toggle-list");

  function syncMapFocusLayout() {
    if (!stageEl) return;
    isMobile = mobileMq.matches;
    if (isMobile) {
      stageEl.classList.add("is-map-focus");
    } else {
      stageEl.classList.remove("is-map-focus");
    }
    if (toggleBtn) {
      toggleBtn.classList.toggle("on", stageEl.classList.contains("is-map-focus"));
      toggleBtn.setAttribute(
        "title",
        stageEl.classList.contains("is-map-focus") ? "Listeyi göster" : "Haritayı büyüt"
      );
    }
    scheduleMapResize();
  }
  var map;
  var routeLayer;
  var markers = [];

  function resizeMap() {
    if (!map) return;
    map.invalidateSize({ pan: false });
  }

  function scheduleMapResize() {
    resizeMap();
    requestAnimationFrame(resizeMap);
    setTimeout(resizeMap, 120);
    if (isMobile) setTimeout(resizeMap, 420);
  }

  if (toggleBtn && stageEl) {
    toggleBtn.addEventListener("click", function () {
      if (!mobileMq.matches) return;
      stageEl.classList.toggle("is-map-focus");
      toggleBtn.classList.toggle("on", stageEl.classList.contains("is-map-focus"));
      toggleBtn.setAttribute(
        "title",
        stageEl.classList.contains("is-map-focus") ? "Listeyi göster" : "Haritayı büyüt"
      );
      scheduleMapResize();
    });
  }
  syncMapFocusLayout();
  if (mobileMq.addEventListener) {
    mobileMq.addEventListener("change", syncMapFocusLayout);
  } else if (mobileMq.addListener) {
    mobileMq.addListener(syncMapFocusLayout);
  }
  window.addEventListener("resize", scheduleMapResize);
  window.addEventListener("load", scheduleMapResize);
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", scheduleMapResize);
  }

  function bootMap() {
    map = L.map(mapEl, {
      scrollWheelZoom: true,
      zoomControl: false,
    }).setView(center, 14);

    L.control.zoom({ position: "topright" }).addTo(map);

    function addTileLayers(target, layers) {
      (layers || []).forEach(function (layer) {
        var opts = {
          maxZoom: layer.maxZoom || 19,
          attribution: layer.attribution || "",
        };
        if (layer.subdomains) opts.subdomains = layer.subdomains;
        if (layer.opacity != null) opts.opacity = layer.opacity;
        L.tileLayer(layer.url, opts).addTo(target);
      });
    }
    addTileLayers(map, cfg.tiles);

    L.circleMarker(center, {
      radius: 10,
      color: "#fff",
      weight: 3,
      fillColor: "#2563eb",
      fillOpacity: 1,
    }).addTo(map);

    if (radiusM > 0) {
      L.circle(center, {
        radius: radiusM,
        color: "#2563eb",
        weight: 1,
        fillColor: "#2563eb",
        fillOpacity: 0.05,
        dashArray: "4 8",
      }).addTo(map);
    }

    routeLayer = L.layerGroup().addTo(map);
    markers = [];
    var bounds = [center];

    pins.forEach(function (p, idx) {
      if (p.lat == null || p.lng == null) return;
      var m = L.circleMarker([p.lat, p.lng], {
        radius: 8,
        color: "#fff",
        weight: 2,
        fillColor: colorFor(p),
        fillOpacity: 0.95,
      }).addTo(map);
      m._nxIdx = idx;
      m.on("click", function () {
        selectPlace(idx);
      });
      markers.push(m);
      bounds.push([p.lat, p.lng]);
    });

    if (bounds.length > 1) {
      try {
        map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
      } catch (e) {}
    }

    scheduleMapResize();
    finishBoot();
  }

  requestAnimationFrame(function () {
    requestAnimationFrame(bootMap);
  });

  function finishBoot() {
  var detailRail = document.getElementById("nx-detail");
  var detailEmpty = document.getElementById("nx-detail-empty");
  var detailPanel = document.getElementById("nx-detail-panel");
  var detailImg = document.getElementById("nx-detail-img");
  var detailPh = document.getElementById("nx-detail-ph");
  var detailThumbs = document.getElementById("nx-detail-thumbs");
  var detailTitle = document.getElementById("nx-detail-title");
  var detailMeta = document.getElementById("nx-detail-meta");
  var detailBlurb = document.getElementById("nx-detail-blurb");
  var detailLink = document.getElementById("nx-detail-go");
  var factAddress = document.getElementById("nx-fact-address");
  var detailAddress = document.getElementById("nx-detail-address");
  var factHours = document.getElementById("nx-fact-hours");
  var detailHours = document.getElementById("nx-detail-hours");
  var factPhone = document.getElementById("nx-fact-phone");
  var detailPhone = document.getElementById("nx-detail-phone");
  var factWeb = document.getElementById("nx-fact-web");
  var detailWeb = document.getElementById("nx-detail-web");
  var listButtons = document.querySelectorAll(".nx-place");
  var selectedIdx = -1;

  function setFact(row, el, text) {
    if (!row || !el) return;
    if (text) {
      el.textContent = text;
      row.hidden = false;
    } else {
      row.hidden = true;
    }
  }

  function setGallery(gallery, p) {
    if (!detailImg || !detailPh || !detailThumbs) return;
    var urls = (gallery || []).filter(Boolean);
    if (!urls.length && p.img_url) urls = [p.img_url];

    detailThumbs.innerHTML = "";
    if (!urls.length) {
      detailImg.hidden = true;
      detailPh.hidden = false;
      detailPh.textContent = catEmoji[p.category] || "📍";
      detailThumbs.hidden = true;
      return;
    }

    detailImg.hidden = false;
    detailPh.hidden = true;
    detailImg.src = urls[0];
    detailImg.alt = p.title || "Mekan fotoğrafı";

    if (urls.length > 1) {
      detailThumbs.hidden = false;
      urls.forEach(function (url, i) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "nx-detail-thumb" + (i === 0 ? " on" : "");
        btn.setAttribute("aria-label", "Fotoğraf " + (i + 1));
        var im = document.createElement("img");
        im.src = url;
        im.alt = "";
        im.loading = "lazy";
        btn.appendChild(im);
        btn.addEventListener("click", function () {
          detailImg.src = url;
          detailThumbs.querySelectorAll(".nx-detail-thumb").forEach(function (t, j) {
            t.classList.toggle("on", j === i);
          });
        });
        detailThumbs.appendChild(btn);
      });
    } else {
      detailThumbs.hidden = true;
    }
  }

  function showDetailPanel(show) {
    if (detailRail) detailRail.classList.toggle("is-empty", !show);
    if (detailEmpty) detailEmpty.hidden = show;
    if (detailPanel) detailPanel.hidden = !show;
    if (stageEl) stageEl.classList.toggle("has-detail", show && isMobile);
    if (show && isMobile) scheduleMapResize();
  }

  function clearSelection() {
    selectedIdx = -1;
    showDetailPanel(false);
    routeLayer.clearLayers();
    listButtons.forEach(function (btn) {
      btn.classList.remove("on");
    });
    markers.forEach(function (m) {
      m.setRadius(8);
    });
  }

  function selectPlace(idx) {
    var p = pins[idx];
    if (!p) return;
    selectedIdx = idx;

    listButtons.forEach(function (btn) {
      btn.classList.toggle("on", Number(btn.getAttribute("data-idx")) === idx);
    });
    markers.forEach(function (m) {
      if (m._nxIdx === idx) {
        m.setRadius(11);
        m.bringToFront();
      } else {
        m.setRadius(8);
      }
    });

    routeLayer.clearLayers();
    if (p.lat != null && p.lng != null) {
      L.polyline([center, [p.lat, p.lng]], {
        color: "#2563eb",
        weight: 3,
        opacity: 0.55,
        dashArray: "6 10",
      }).addTo(routeLayer);
    }

    showDetailPanel(true);

    if (detailTitle) detailTitle.textContent = p.title || "Mekan";

    if (detailMeta) {
      var bits = [fmtDist(p.distance_m)];
      var catBits = [p.category_label || p.category || ""];
      if (p.subcategory_label) catBits.push(p.subcategory_label);
      bits.push(catBits.filter(Boolean).join(" · "));
      if (p.rating) bits.push("★ " + Number(p.rating).toFixed(1));
      var price = priceLabel(p.price_band);
      if (price) bits.push(price);
      detailMeta.textContent = bits.filter(Boolean).join(" · ");
    }

    if (detailBlurb) {
      if (p.blurb) {
        detailBlurb.textContent = p.blurb;
        detailBlurb.hidden = false;
      } else {
        detailBlurb.hidden = true;
      }
    }

    setGallery(p.gallery, p);

    var addrParts = [];
    if (p.address) addrParts.push(p.address);
    if (p.ilce) addrParts.push(p.ilce);
    setFact(factAddress, detailAddress, addrParts.join(", "));

    setFact(factHours, detailHours, p.hours_text || "");

    if (factPhone && detailPhone) {
      if (p.phone) {
        detailPhone.textContent = p.phone;
        detailPhone.href = "tel:" + p.phone.replace(/\s/g, "");
        factPhone.hidden = false;
      } else {
        factPhone.hidden = true;
      }
    }

    if (factWeb && detailWeb) {
      if (p.web) {
        var web = p.web;
        if (!/^https?:\/\//i.test(web)) web = "https://" + web;
        detailWeb.href = web;
        try {
          detailWeb.textContent = new URL(web).hostname.replace(/^www\./, "");
        } catch (e) {
          detailWeb.textContent = p.web;
        }
        factWeb.hidden = false;
      } else {
        factWeb.hidden = true;
      }
    }

    if (detailLink) {
      detailLink.href = p.path || (p.slug ? "/yer/" + p.slug : "#");
    }

    if (p.lat != null && p.lng != null) {
      map.panTo([p.lat, p.lng], { animate: true, duration: 0.4 });
      if (isMobile) {
        setTimeout(function () {
          map.panBy([0, 90], { animate: true });
        }, 120);
      }
    }
  }

  listButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      selectPlace(Number(btn.getAttribute("data-idx")));
    });
  });

  document.getElementById("nx-detail-close")?.addEventListener("click", clearSelection);

  function goGeo() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        location.href = mapUrl(pos.coords.latitude, pos.coords.longitude);
      },
      function () {
        var el = document.getElementById("nx-loc-banner");
        if (el) {
          el.textContent = "Konum alınamadı — Bursa merkezi gösteriliyor.";
        }
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 }
    );
  }

  document.querySelectorAll("[data-nx-geo]").forEach(function (el) {
    el.addEventListener("click", goGeo);
  });

  if (usedFallback) goGeo();

  if (pins.length && listButtons.length && !isMobile) {
    selectPlace(0);
  } else {
    clearSelection();
  }
  }
})();
