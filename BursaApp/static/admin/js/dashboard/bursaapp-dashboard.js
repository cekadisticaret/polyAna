(function () {
  "use strict";

  var data = window.__BA_DASHBOARD_CHARTS__;
  if (!data || typeof ApexCharts === "undefined") {
    return;
  }

  var teal = "#0f3d32";
  var sand = "#c9b89a";
  var sandLight = "#e8dfd3";
  var ink = "#111827";
  var muted = "#9ca3af";
  var palette = [teal, sand, "#64748b", "#14b8a6", "#7c3aed", "#f97316", "#ec4899"];

  function mount(el, options) {
    if (!el) return;
    var chart = new ApexCharts(el, options);
    chart.render();
  }

  var grid = { borderColor: "#eef0f3", strokeDashArray: 0, xaxis: { lines: { show: false } } };

  var traffic = data.traffic || {};
  var trafficLabels = traffic.labels || [];
  var trafficVisitors = traffic.visitors || [];
  var trafficPageviews = traffic.pageviews || [];
  mount(document.querySelector("#ba-chart-traffic"), {
    series: [
      { name: "Tekil ziyaretçi", data: trafficVisitors },
      { name: "Sayfa görüntüleme", data: trafficPageviews },
    ],
    chart: {
      height: 280,
      type: "bar",
      toolbar: { show: false },
      fontFamily: "inherit",
      zoom: { enabled: false },
    },
    colors: [teal, sand],
    plotOptions: {
      bar: {
        borderRadius: 6,
        columnWidth: trafficLabels.length > 10 ? "78%" : "62%",
        dataLabels: { position: "top" },
      },
    },
    dataLabels: {
      enabled: trafficLabels.length <= 10,
      offsetY: -14,
      style: { fontSize: "10px", fontWeight: 700, colors: [ink] },
    },
    xaxis: {
      categories: trafficLabels,
      axisBorder: { show: false },
      axisTicks: { show: false },
      labels: { style: { colors: muted, fontSize: "11px" } },
    },
    yaxis: {
      min: 0,
      forceNiceScale: true,
      labels: {
        formatter: function (v) { return Math.round(v); },
        style: { colors: muted, fontSize: "11px" },
      },
    },
    legend: {
      show: true,
      position: "top",
      horizontalAlign: "right",
      fontSize: "12px",
      markers: { width: 10, height: 10, radius: 10 },
    },
    grid: grid,
    tooltip: {
      shared: true,
      intersect: false,
      theme: "light",
      y: {
        formatter: function (v, opts) {
          var n = Math.round(v) || 0;
          if (opts.seriesIndex === 0) return n + " tekil";
          return n + " sayfa";
        },
      },
    },
  });

  var logins = data.logins || {};
  mount(document.querySelector("#ba-chart-logins"), {
    series: [{ name: "Giriş", data: logins.series || [] }],
    chart: {
      type: "bar",
      height: 300,
      toolbar: { show: false },
      fontFamily: "inherit",
    },
    colors: [teal],
    plotOptions: {
      bar: {
        borderRadius: 8,
        columnWidth: "52%",
        dataLabels: { position: "top" },
      },
    },
    dataLabels: {
      enabled: true,
      offsetY: -16,
      style: { fontSize: "11px", fontWeight: 700, colors: [ink] },
    },
    xaxis: {
      categories: logins.labels || [],
      axisBorder: { show: false },
      axisTicks: { show: false },
      labels: { style: { colors: muted, fontSize: "11px" } },
    },
    yaxis: {
      min: 0,
      forceNiceScale: true,
      labels: {
        formatter: function (v) { return Math.round(v); },
        style: { colors: muted, fontSize: "11px" },
      },
    },
    grid: grid,
    tooltip: { y: { formatter: function (v) { return (Math.round(v) || 0) + " giriş"; } } },
  });

  var moderation = data.moderation || {};
  var modSeries = (moderation.series || []).map(function (n) { return Number(n) || 0; });
  var modLabels = moderation.labels || [];
  var modFiltered = modLabels
    .map(function (label, i) { return { label: label, value: modSeries[i] || 0 }; })
    .filter(function (row) { return row.value > 0; });
  if (!modFiltered.length) {
    modFiltered = [{ label: "Kuyruk boş", value: 1 }];
  }
  mount(document.querySelector("#ba-chart-moderation"), {
    series: modFiltered.map(function (row) { return row.value; }),
    chart: { type: "donut", height: 240, fontFamily: "inherit" },
    labels: modFiltered.map(function (row) { return row.label; }),
    colors: palette,
    legend: { position: "bottom", fontSize: "11px" },
    dataLabels: { enabled: false },
    stroke: { width: 0 },
    plotOptions: {
      pie: {
        donut: {
          size: "72%",
          labels: {
            show: true,
            name: { show: false },
            value: { show: true, fontSize: "22px", fontWeight: 700, color: ink },
            total: {
              show: true,
              label: "Kuyruk",
              fontSize: "11px",
              color: muted,
              formatter: function (w) {
                return w.globals.seriesTotals.reduce(function (a, b) { return a + b; }, 0);
              },
            },
          },
        },
      },
    },
  });

  var categories = data.categories || {};
  mount(document.querySelector("#ba-chart-categories"), {
    series: [{ name: "Yer", data: categories.series || [] }],
    chart: { type: "bar", height: 300, toolbar: { show: false }, fontFamily: "inherit" },
    plotOptions: { bar: { borderRadius: 8, columnWidth: "50%", distributed: true } },
    dataLabels: { enabled: false },
    legend: { show: false },
    xaxis: {
      categories: categories.labels || [],
      labels: { rotate: -35, trim: true, style: { colors: muted, fontSize: "10px" } },
    },
    yaxis: { labels: { formatter: function (v) { return Math.round(v); }, style: { colors: muted } } },
    grid: grid,
    colors: palette,
  });

  var topPages = data.top_pages || {};
  mount(document.querySelector("#ba-chart-top-pages"), {
    series: [{ name: "Görüntüleme", data: topPages.series || [] }],
    chart: { type: "bar", height: 320, toolbar: { show: false }, fontFamily: "inherit" },
    plotOptions: { bar: { horizontal: true, borderRadius: 6, barHeight: "62%" } },
    colors: [teal],
    dataLabels: { enabled: true, style: { fontSize: "10px", colors: [ink] } },
    xaxis: { labels: { formatter: function (v) { return Math.round(v); }, style: { colors: muted } } },
    yaxis: { labels: { maxWidth: 180, style: { colors: muted, fontSize: "11px" } } },
    grid: grid,
  });

  var activity = data.activity || {};
  mount(document.querySelector("#ba-chart-activity"), {
    series: [
      { name: "Kayıt", data: activity.register || [] },
      { name: "Giriş", data: activity.login || [] },
      { name: "Yer gönderimi", data: activity.submit || [] },
    ],
    chart: { type: "bar", height: 280, stacked: true, toolbar: { show: false }, fontFamily: "inherit" },
    colors: [sandLight, teal, sand],
    plotOptions: { bar: { borderRadius: 6, columnWidth: "46%" } },
    xaxis: { categories: activity.labels || [], labels: { style: { colors: muted } } },
    yaxis: { labels: { formatter: function (v) { return Math.round(v); }, style: { colors: muted } } },
    legend: { position: "top", horizontalAlign: "right", fontSize: "12px" },
    dataLabels: { enabled: false },
    grid: grid,
  });

  var scroll = data.scroll || {};
  mount(document.querySelector("#ba-chart-scroll"), {
    series: [{ name: "Sayfa", data: scroll.series || [] }],
    chart: { type: "bar", height: 240, toolbar: { show: false }, fontFamily: "inherit" },
    plotOptions: { bar: { borderRadius: 8, columnWidth: "48%", distributed: true } },
    colors: palette,
    dataLabels: { enabled: true, style: { fontSize: "10px", colors: [ink] } },
    legend: { show: false },
    xaxis: { categories: scroll.labels || [], labels: { style: { colors: muted, fontSize: "11px" } } },
    yaxis: { labels: { formatter: function (v) { return Math.round(v); }, style: { colors: muted } } },
    grid: grid,
  });

  var clickKinds = data.click_kinds || {};
  mount(document.querySelector("#ba-chart-clicks"), {
    series: clickKinds.series || [],
    chart: { type: "donut", height: 240, fontFamily: "inherit" },
    labels: clickKinds.labels || [],
    colors: palette,
    legend: { position: "bottom", fontSize: "11px" },
    dataLabels: { enabled: false },
    stroke: { width: 0 },
    plotOptions: {
      pie: {
        donut: {
          size: "68%",
          labels: {
            show: true,
            total: {
              show: true,
              label: "Tık",
              fontSize: "11px",
              color: muted,
              formatter: function (w) {
                return w.globals.seriesTotals.reduce(function (a, b) { return a + b; }, 0);
              },
            },
          },
        },
      },
    },
  });

  var engagement = data.engagement || {};
  mount(document.querySelector("#ba-chart-engage-time"), {
    series: [{ name: "Ort. sn", data: engagement.avg_seconds || [] }],
    chart: { type: "area", height: 220, toolbar: { show: false }, fontFamily: "inherit", sparkline: { enabled: false } },
    colors: [teal],
    stroke: { curve: "smooth", width: 2 },
    fill: { type: "gradient", gradient: { shadeIntensity: 0.2, opacityFrom: 0.35, opacityTo: 0.05 } },
    dataLabels: { enabled: false },
    xaxis: { categories: engagement.labels || [], labels: { style: { colors: muted, fontSize: "11px" } } },
    yaxis: { labels: { formatter: function (v) { return Math.round(v) + " sn"; }, style: { colors: muted } } },
    grid: grid,
  });
})();
