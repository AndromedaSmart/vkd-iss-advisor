(function () {
  var GRADE_LEVEL = {
    benign: "none",
    elevated: "watch",
    adverse: "warning",
    insufficient_data: "unknown"
  };
  var CSV_COLUMNS = [
    "id", "day", "start", "end", "requested", "preferred", "coverage",
    "sep", "mmod", "geomagnetic", "donki", "cme", "adverse_minutes",
    "completeness", "critical_missing"
  ];
  var DEMOS = (function () {
    try {
      return JSON.parse(document.body.getAttribute("data-demos") || "{}");
    } catch (err) {
      return {};
    }
  })();
  var activeDemo = null;
  var lastExport = null;
  var lastWindows = null;
  var lastProbedStart = null;
  var probeTimer = null;

  function apiBase() {
    var body = document.body;
    return (body && body.getAttribute("data-api-base")) || "http://46.29.164.87:8000";
  }

  function algorithm() {
    return (document.body && document.body.getAttribute("data-algorithm")) || "";
  }

  function demoFromLocation() {
    var attr = document.body && document.body.getAttribute("data-demo");
    if (attr && DEMOS[attr]) return attr;
    var params = new URLSearchParams(window.location.search);
    var query = params.get("demo");
    if (query && DEMOS[query]) return query;
    var path = (window.location.pathname || "").toLowerCase();
    var keys = Object.keys(DEMOS);
    for (var i = 0; i < keys.length; i += 1) {
      var key = keys[i];
      if (path.indexOf("/demo/" + key) !== -1) return key;
      var slug = "demo-" + key.replace(/_/g, "-") + ".html";
      if (path.indexOf(slug) !== -1) return key;
    }
    return "storm";
  }

  function isStatic() {
    return document.body && document.body.getAttribute("data-static") === "true";
  }

  function pad(n) {
    return n < 10 ? "0" + n : String(n);
  }

  function toIso(dt) {
    return dt.getUTCFullYear() + "-" + pad(dt.getUTCMonth() + 1) + "-" + pad(dt.getUTCDate()) +
      "T" + pad(dt.getUTCHours()) + ":" + pad(dt.getUTCMinutes()) + ":" + pad(dt.getUTCSeconds()) + "Z";
  }

  function parseUtc(text) {
    var raw = (text || "").trim().replace(" ", "T");
    if (!/Z$/.test(raw) && raw.indexOf("+") === -1) raw += "Z";
    var dt = new Date(raw);
    if (isNaN(dt.getTime())) throw new Error("Некорректная дата: " + text);
    return dt;
  }

  function candidateStarts(start, intervalDays) {
    var out = [];
    var days = Math.max(1, intervalDays || 1);
    for (var i = 0; i < days; i += 1) {
      out.push(new Date(start.getTime() + i * 24 * 3600 * 1000));
    }
    return out;
  }

  function levelFromGrade(grade) {
    return GRADE_LEVEL[grade] || "unknown";
  }

  function pickFactor(factors, id) {
    for (var i = 0; i < (factors || []).length; i += 1) {
      if (factors[i].factor_id === id) return factors[i];
    }
    return { factor_id: id, grade: "insufficient_data", coverage: 0, adverse_minutes: 0, evidence: [], confidence_reason: "" };
  }

  function rank(level) {
    if (level === "high") return 3;
    if (level === "warning") return 2;
    if (level === "watch") return 1;
    if (level === "none") return 0;
    return -1;
  }

  function esc(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function pill(level) {
    return '<span class="level ' + esc(level) + '">' + esc(level) + "</span>";
  }

  function postJson(path, payload) {
    return fetch(apiBase() + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (resp) {
      return resp.text().then(function (text) {
        var data = {};
        try { data = text ? JSON.parse(text) : {}; } catch (err) { data = { detail: text }; }
        if (!resp.ok) {
          var detail = data.detail || text || resp.status;
          if (typeof detail !== "string") detail = JSON.stringify(detail);
          throw new Error(detail);
        }
        return data;
      });
    });
  }

  function getJson(path) {
    return fetch(apiBase() + path).then(function (resp) {
      if (!resp.ok) throw new Error("status " + resp.status);
      return resp.json();
    });
  }

  function fetchJson(url) {
    return fetch(url).then(function (resp) {
      if (!resp.ok) throw new Error("status " + resp.status);
      return resp.json();
    });
  }

  function assessOne(start, duration, asOf) {
    var payload = {
      window_start: toIso(start),
      duration_hours: duration
    };
    if (asOf) payload.as_of = toIso(asOf);
    return postJson("/api/assess-window", payload);
  }

  function apiWindowEmpty(w) {
    return w.sepLevel === "unknown" && (w.cover || 0) === 0;
  }

  function factorView(block) {
    block = block || {};
    return {
      factor_id: block.factor_id || block.mechanism,
      grade: block.grade,
      coverage: block.coverage,
      adverse_minutes: block.overlap_minutes || block.adverse_minutes || 0,
      evidence: block.evidence || [],
      confidence_reason: block.confidence_reason || block.confidence || "",
      limitations: block.limitations || []
    };
  }

  function mapWindow(raw, idx, requested) {
    var start = new Date(raw.window_start);
    var end = new Date(raw.window_end);
    var sep = pickFactor(raw.factors, "radiation_sep");
    var geo = pickFactor(raw.factors, "geomagnetic_activity");
    var mmod = pickFactor(raw.factors, "mmod_meteoroid");
    var sepLevel = levelFromGrade(sep.grade);
    var geoLevel = levelFromGrade(geo.grade);
    var mmodLevel = levelFromGrade(mmod.grade);
    var cover = Math.max(sep.coverage || 0, geo.coverage || 0, mmod.coverage || 0);
    var tag = cover >= 0.8 ? "ncei" : cover > 0 ? "donki" : "gap";
    var labels = cover > 0 ? ["API"] : [];
    var adverse = 0;
    if (sepLevel === "warning" || sepLevel === "high") adverse += Number(sep.adverse_minutes || 0);
    if (mmodLevel === "warning" || mmodLevel === "high") adverse += Number(mmod.adverse_minutes || 0);
    var complete = ((sepLevel === "unknown" ? 0 : 1) + (geoLevel === "unknown" ? 0 : 1)) / 2;
    return {
      id: "W" + (idx + 1),
      start: start,
      end: end,
      sepLevel: sepLevel,
      geoLevel: geoLevel,
      mmodLevel: mmodLevel,
      sep: sep,
      geo: geo,
      mmod: mmod,
      cover: cover,
      tag: tag,
      labels: labels,
      adverse: adverse,
      completeness: complete.toFixed(2),
      critical: sepLevel === "unknown",
      requested: requested,
      worst: Math.max(rank(sepLevel), rank(mmodLevel), 0),
      raw: raw,
      archive: false,
      reason: sep.confidence_reason || geo.confidence_reason || "",
      donkiCount: 0,
      cmeCount: 0
    };
  }

  function packLevel(block, fallback) {
    if (block && block.grade) return levelFromGrade(block.grade);
    return (fallback && fallback.level) || "unknown";
  }

  function fromPackWindow(w, idx, requested) {
    var start = new Date(w.start);
    var end = new Date(w.end);
    var sep = factorView(w.sep);
    var geo = factorView(w.geomagnetic);
    var mmod = factorView(w.conjunction);
    var sepLevel = packLevel(sep, w.sep);
    var geoLevel = packLevel(geo, w.geomagnetic);
    var mmodLevel = packLevel(mmod, w.conjunction);
    var coverage = w.coverage || {};
    var tag = coverage.tag || "gap";
    var labels = (coverage.labels || []).slice();
    if (labels.indexOf("архив") === -1) labels.unshift("архив");
    var cover = tag === "ncei" ? 1 : tag === "donki" ? 0.5 : 0;
    return {
      id: w.id || ("W" + (idx + 1)),
      start: start,
      end: end,
      sepLevel: sepLevel,
      geoLevel: geoLevel,
      mmodLevel: mmodLevel,
      sep: sep,
      geo: geo,
      mmod: mmod,
      cover: cover,
      tag: tag === "gap" ? "archive" : tag,
      labels: labels,
      adverse: Number(w.adverse_minutes || 0),
      completeness: Number(w.completeness || 0).toFixed(2),
      critical: Boolean(w.critical_missing),
      requested: requested,
      worst: Math.max(rank(sepLevel), rank(mmodLevel), 0),
      raw: w,
      archive: true,
      reason: sep.confidence_reason || "",
      donkiCount: Number((w.donki && w.donki.count) || 0),
      cmeCount: Number((w.cme && w.cme.count) || 0)
    };
  }

  function mergeArchive(windows, pack) {
    if (!pack || !pack.windows) return windows;
    var byDay = {};
    pack.windows.forEach(function (item) {
      var key = String(item.start || "").slice(0, 10);
      if (key) byDay[key] = item;
    });
    return windows.map(function (w, idx) {
      if (!apiWindowEmpty(w)) return w;
      var day = w.start.toISOString().slice(0, 10);
      var local = byDay[day];
      if (!local) return w;
      var mapped = fromPackWindow(local, idx, w.requested);
      mapped.id = w.id;
      mapped.requested = w.requested;
      return mapped;
    });
  }

  function compare(windows) {
    var usable = windows.filter(function (w) { return !w.critical; });
    if (!usable.length) {
      return { decision: "insufficient", preferred: null, reason: "Недостаточно данных по критичному механизму. Это не спокойная обстановка." };
    }
    usable.sort(function (a, b) {
      if (a.worst !== b.worst) return a.worst - b.worst;
      if (a.adverse !== b.adverse) return a.adverse - b.adverse;
      return Number(b.completeness) - Number(a.completeness);
    });
    var best = usable[0];
    var tied = usable.filter(function (w) { return w.worst === best.worst && w.adverse === best.adverse; });
    if (tied.length > 1) {
      return { decision: "equivalent", preferred: null, reason: "Окна не различаются по худшему уровню и неблагоприятным минутам." };
    }
    return { decision: "prefer", preferred: best.id, reason: "Меньше пересечения с уровнем warning+ при сопоставимой полноте. G не суммировалась с SEP." };
  }

  function evidenceHtml(factor) {
    var rows = factor.evidence || [];
    if (!rows.length) return "<p class=\"small\">Нет свидетельств в ответе API.</p>";
    return "<ul class=\"evidence\">" + rows.map(function (ev) {
      return "<li><div class=\"kind\">" + esc(ev.provenance || ev.kind || "external_forecast") +
        "</div><strong>" + esc(ev.statement || ev.title || ev.rule_id || "") + "</strong>" +
        "<div class=\"small\">" + esc(ev.rule_description || ev.detail || "") + "</div>" +
        "<div class=\"src\">" + esc((ev.source_ids || []).join(", ") || ev.source_id || "") +
        " · " + esc(ev.rule_id || ev.rule || "") + "</div></li>";
    }).join("") + "</ul>";
  }

  function isoOf(dt) {
    if (!dt) return "";
    if (typeof dt === "string") return dt;
    return dt.toISOString();
  }

  function csvCell(value) {
    var text = value == null ? "" : String(value);
    if (/[",\n]/.test(text)) return '"' + text.replace(/"/g, '""') + '"';
    return text;
  }

  function exportFilename(form, ext) {
    var start = String((form && form.start_utc) || "windows").replace(/[:\s]/g, "-");
    var days = (form && form.interval_days) || 1;
    return "vkd-" + start + "-" + days + "d." + ext;
  }

  function serializeWindow(w) {
    return {
      id: w.id,
      day: w.start ? isoOf(w.start).slice(0, 10) : "",
      start: isoOf(w.start),
      end: isoOf(w.end),
      requested: Boolean(w.requested),
      preferred: Boolean(w.preferred),
      coverage: (w.labels || []).join(", ") || w.tag || "",
      coverage_tag: w.tag || "",
      sep: w.sepLevel,
      mmod: w.mmodLevel,
      geomagnetic: w.geoLevel,
      donki: w.donkiCount || 0,
      cme: w.cmeCount || 0,
      adverse_minutes: w.adverse,
      completeness: w.completeness,
      critical_missing: Boolean(w.critical),
      archive: Boolean(w.archive),
      reason: w.reason || "",
      factors: {
        radiation_sep: w.sep,
        mmod_meteoroid: w.mmod,
        geomagnetic_activity: w.geo
      }
    };
  }

  function buildExport(windows, comparison, status, form) {
    var rows = windows.map(serializeWindow);
    return {
      json: {
        generated_at: new Date().toISOString(),
        algorithm: algorithm(),
        api_base: apiBase(),
        form: form || {},
        comparison: comparison || {},
        sources: (status && status.sources) || [],
        overall_status: (status && status.overall_status) || "",
        windows: rows
      },
      csv: (function () {
        var lines = [CSV_COLUMNS.join(",")];
        rows.forEach(function (row) {
          lines.push(CSV_COLUMNS.map(function (key) {
            var value = row[key];
            if (typeof value === "boolean") value = value ? "1" : "0";
            return csvCell(value);
          }).join(","));
        });
        return lines.join("\n") + "\n";
      })()
    };
  }

  function downloadBlob(filename, mime, text) {
    var blob = new Blob([text], { type: mime });
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () { URL.revokeObjectURL(url); }, 800);
  }

  function bindExport(form) {
    var jsonBtn = document.getElementById("export-json");
    var csvBtn = document.getElementById("export-csv");
    if (jsonBtn) {
      jsonBtn.onclick = function () {
        if (!lastExport) return;
        downloadBlob(exportFilename(form, "json"), "application/json;charset=utf-8", JSON.stringify(lastExport.json, null, 2));
      };
    }
    if (csvBtn) {
      csvBtn.onclick = function () {
        if (!lastExport) return;
        downloadBlob(exportFilename(form, "csv"), "text/csv;charset=utf-8", lastExport.csv);
      };
    }
  }

  function emptyReason(windows) {
    for (var i = 0; i < windows.length; i += 1) {
      if (windows[i].reason) return windows[i].reason;
    }
    return "Нет прогнозов протонного потока в период окна";
  }

  function render(windows, comparison, status, form, meta) {
    var root = document.getElementById("results-root");
    if (!root) return;
    meta = meta || {};
    windows.forEach(function (w) {
      w.preferred = comparison.preferred === w.id;
    });
    var title = comparison.decision === "prefer"
      ? "Предпочтительное окно: " + comparison.preferred
      : comparison.decision === "equivalent"
        ? "Окна равнозначны"
        : "Недостаточно оснований для рекомендации";
    var srcRows = ((status && status.sources) || []).map(function (s) {
      return "<tr><td>" + esc(s.name) + "</td><td>" + esc(s.source_id) + "</td><td>" +
        esc(s.status) + "</td><td class=\"num\">" + esc(s.last_data_time || "—") +
        "</td><td class=\"num\">" + esc(s.record_count) + "</td><td class=\"small\">" +
        esc((s.coverage_start || "") + " — " + (s.coverage_end || "")) + "</td></tr>";
    }).join("");
    var showDonki = windows.some(function (w) { return Number(w.donkiCount || 0) > 0; });
    var table = windows.map(function (w) {
      var when = w.start.toISOString().replace("T", " ").replace(".000Z", " UTC") +
        " — " + w.end.toISOString().replace("T", " ").replace(".000Z", " UTC");
      var coverLabel = w.labels.join(", ") || "дыра";
      return "<tr class=\"" + (w.preferred ? "preferred" : "") + "\">" +
        "<td class=\"num\">" + esc(w.start.toISOString().slice(0, 10)) + "</td>" +
        "<td class=\"num\">" + esc(w.id) + (w.requested ? " · запрос" : "") + (w.preferred ? " · выбор" : "") + "</td>" +
        "<td class=\"num\">" + esc(when) + "</td>" +
        "<td><span class=\"cover " + esc(w.tag) + "\">" + esc(coverLabel) + "</span></td>" +
        "<td>" + pill(w.sepLevel) + "</td>" +
        "<td>" + pill(w.mmodLevel) + "</td>" +
        "<td>" + pill(w.geoLevel) + "</td>" +
        (showDonki ? "<td class=\"num\">" + esc(w.donkiCount || 0) + "</td>" : "") +
        "<td class=\"num\">" + esc(w.adverse) + "</td>" +
        "<td class=\"num\">" + esc(w.completeness) + (w.critical ? " · дыра" : "") +
        (w.reason && !w.archive ? "<div class=\"small\">" + esc(w.reason) + "</div>" : "") +
        "</td></tr>";
    }).join("");
    var first = windows[0];
    var cards = first ? [
      { title: "Солнечные энергичные частицы", level: first.sepLevel, block: first.sep },
      { title: "MMOD / метеорная обстановка", level: first.mmodLevel, block: first.mmod },
      { title: "Геомагнитная обстановка (не суммируется с SEP)", level: first.geoLevel, block: first.geo }
    ].map(function (card) {
      return "<div class=\"card\"><header><span>" + esc(card.title) + "</span>" + pill(card.level) +
        "</header><p class=\"small\">" + esc(card.block.confidence_reason || "") + "</p>" +
        evidenceHtml(card.block) + "</div>";
    }).join("") : "";
    var emptyApi = windows.some(apiWindowEmpty);
    var usedArchive = windows.some(function (w) { return w.archive; });
    var banners = "<div class=\"banner\">Данные: ВКД-планировщик API " + esc(apiBase()) +
      " · overall " + esc((status && status.overall_status) || "—") + "</div>";
    if (emptyApi || usedArchive) {
      banners += "<div class=\"banner warn\">Планировщик v0.2.0 отдаёт SWPC только на пример 2024-05-10 08:00 UTC (источник test_swpc). " +
        (usedArchive
          ? "Для остальных суток подставлен локальный архив NCEI/DONKI — это не all-clear хоста."
          : emptyReason(windows) + ". Статус источников (89 записей NOAA) не совпадает с assess-window.") +
        "</div>";
    }
    lastExport = buildExport(windows, comparison, status, form);
    lastWindows = windows;
    root.innerHTML =
      "<div class=\"meta-row\"><div>онлайн " + esc(apiBase()) + " · " + esc(form.mode) +
      " · окон " + windows.length + (usedArchive ? " · архив для пустых ответов API" : "") + "</div>" +
      "<div class=\"export-actions\">" +
      "<button type=\"button\" class=\"btn ghost\" id=\"export-json\">Выгрузить JSON</button>" +
      "<button type=\"button\" class=\"btn ghost\" id=\"export-csv\">Выгрузить CSV</button>" +
      "</div></div>" +
      banners +
      "<div class=\"decision\"><h2>" + esc(title) + "</h2><p>" + esc(comparison.reason) + "</p></div>" +
      "<section><h2>Сравнение окон по ответу API</h2><div class=\"table-wrap\"><table><thead><tr>" +
      "<th>День</th><th>Окно</th><th>Интервал UTC</th><th>Покрытие</th><th>SEP</th><th>MMOD</th><th>G (отдельно)</th>" +
      (showDonki ? "<th>DONKI</th>" : "") +
      "<th>Неблагопр., мин</th><th>Полнота</th>" +
      "</tr></thead><tbody>" + table + "</tbody></table></div>" +
      "<p class=\"small\">Онлайн-стенд ходит в API. G и MMOD не суммируются с SEP.</p></section>" +
      "<section><h2>Доказательства по запрошенному окну</h2><div class=\"grid-2\">" + cards + "</div></section>" +
      "<section><h2>Источники API</h2><table><thead><tr><th>Источник</th><th>ID</th><th>Статус</th><th>Последние данные</th><th>Записей</th><th>Покрытие</th></tr></thead><tbody>" +
      srcRows + "</tbody></table></section>";
    bindExport(form);
  }

  function readForm(form) {
    var data = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name) return;
      if (el.type === "checkbox") data[el.name] = el.checked;
      else data[el.name] = el.value;
    });
    return data;
  }

  function fillForm(form, values) {
    Object.keys(values).forEach(function (key) {
      if (form.elements[key] != null) form.elements[key].value = values[key];
    });
  }

  function fallbackAsset(demo) {
    var script = document.querySelector("script[src*=\"stand.js\"]");
    var src = (script && script.getAttribute("src")) || "static/stand.js";
    return src.replace(/stand\.js(\?.*)?$/, "fallback-" + demo + ".json");
  }

  function loadArchiveFallback(fields) {
    var qs = new URLSearchParams({
      mode: fields.mode || "historical",
      start_utc: fields.start_utc || "",
      duration_hours: String(fields.duration_hours || 6),
      interval_days: String(fields.interval_days || 1),
      search_hours: String(fields.search_hours || 12),
      cutoff_utc: fields.cutoff_utc || "",
      offline: "on"
    });
    var localUrl = "/api/evaluate?" + qs.toString();
    var tryLocal = !isStatic() && /^https?:$/.test(window.location.protocol);
    var chain = tryLocal
      ? fetchJson(localUrl).catch(function () { return null; })
      : Promise.resolve(null);
    return chain.then(function (pack) {
      if (pack && pack.windows && !pack.error) return pack;
      if (!activeDemo) return null;
      return fetchJson(fallbackAsset(activeDemo)).catch(function () { return null; });
    });
  }

  function run(form) {
    var root = document.getElementById("results-root");
    var banner = document.getElementById("live-error");
    if (banner) banner.textContent = "";
    if (root) root.innerHTML = "<div class=\"banner\">Запрос к " + esc(apiBase()) + "…</div>";
    var fields = readForm(form);
    var start;
    try {
      start = parseUtc(fields.start_utc);
    } catch (err) {
      if (root) root.innerHTML = "";
      if (banner) banner.textContent = err.message;
      return Promise.resolve();
    }
    var duration = Number(fields.duration_hours || 6);
    var interval = Number(fields.interval_days || 1);
    var mode = fields.mode === "current" ? "live" : "historical_review";
    var starts = candidateStarts(start, interval);
    var statusP = getJson("/api/data-sources-status").catch(function () { return { sources: [], overall_status: "unavailable" }; });
    var fallbackP = loadArchiveFallback(fields);
    fallbackP.then(function (pack) {
      if (!pack || !pack.windows) return;
      var windows = pack.windows.map(function (w, idx) { return fromPackWindow(w, idx, idx === 0); });
      render(windows, compare(windows), { sources: [], overall_status: "pending" }, fields, { archive: true });
    });
    var chain = Promise.resolve([]);
    starts.forEach(function (item) {
      chain = chain.then(function (acc) {
        var asOf = mode === "live" ? null : item;
        return assessOne(item, duration, asOf).then(function (raw) {
          acc.push(raw);
          return acc;
        });
      });
    });
    return Promise.all([chain, statusP, fallbackP]).then(function (pair) {
      var assessments = pair[0];
      var status = pair[1];
      var pack = pair[2];
      var windows = assessments.map(function (raw, idx) { return mapWindow(raw, idx, idx === 0); });
      if (!windows.some(apiWindowEmpty)) {
        render(windows, compare(windows), status, fields);
        return null;
      }
      var merged = mergeArchive(windows, pack);
      render(merged, compare(merged), status, fields, { archive: Boolean(pack) });
    }).catch(function (err) {
      return (fallbackP || loadArchiveFallback(fields)).then(function (pack) {
        if (pack && pack.windows) {
          var windows = pack.windows.map(function (w, idx) { return fromPackWindow(w, idx, idx === 0); });
          render(windows, compare(windows), { sources: [], overall_status: "unavailable" }, fields, { archive: true });
          if (banner) banner.textContent = "API " + apiBase() + " недоступен, показан архив: " + err.message;
          return;
        }
        if (root) root.innerHTML = "";
        if (banner) banner.textContent = "API " + apiBase() + ": " + err.message;
      });
    });
  }

  function useLiveApi() {
    return isStatic() || (document.body && document.body.getAttribute("data-live-api") === "true");
  }

  function isDangerous(window) {
    if (!window) return false;
    return rank(window.sepLevel) >= 2 || rank(window.mmodLevel) >= 2 || rank(window.geoLevel) >= 2;
  }

  function formatWhen(dt) {
    if (!dt) return "—";
    return dt.toISOString().replace("T", " ").replace(".000Z", " UTC");
  }

  function closeAlert() {
    var modal = document.getElementById("eva-alert");
    if (modal) modal.hidden = true;
  }

  function showDangerAlert(window, fields) {
    var modal = document.getElementById("eva-alert");
    var body = document.getElementById("eva-alert-body");
    var factors = document.getElementById("eva-alert-factors");
    if (!modal || !body || !factors) return;
    var bits = [];
    if (rank(window.sepLevel) >= 2) bits.push("радиационная обстановка SEP на уровне " + window.sepLevel);
    if (rank(window.mmodLevel) >= 2) bits.push("MMOD на уровне " + window.mmodLevel);
    if (rank(window.geoLevel) >= 2) bits.push("геомагнитная шкала G на уровне " + window.geoLevel + " (показывается отдельно и не суммируется с SEP)");
    body.textContent = "Для начала ВКД " + formatWhen(window.start) +
      " окно выглядит неблагоприятным для выхода: " + bits.join("; ") +
      ". Это не допуск к выходу. Сравните соседние сутки или сдвиньте время.";
    factors.innerHTML = pill(window.sepLevel) + " SEP " +
      pill(window.mmodLevel) + " MMOD " +
      pill(window.geoLevel) + " G";
    modal.hidden = false;
    var closeBtn = document.getElementById("eva-alert-close");
    if (closeBtn) closeBtn.focus();
  }

  function windowForStart(start) {
    if (!lastWindows || !start) return null;
    var t = start.getTime();
    for (var i = 0; i < lastWindows.length; i += 1) {
      if (lastWindows[i].start && lastWindows[i].start.getTime() === t) return lastWindows[i];
    }
    var day = start.toISOString().slice(0, 10);
    for (var j = 0; j < lastWindows.length; j += 1) {
      if (lastWindows[j].start && lastWindows[j].start.toISOString().slice(0, 10) === day) return lastWindows[j];
    }
    return null;
  }

  function packWindowForStart(pack, start) {
    if (!pack || !pack.windows || !start) return null;
    var day = start.toISOString().slice(0, 10);
    for (var i = 0; i < pack.windows.length; i += 1) {
      if (String(pack.windows[i].start || "").slice(0, 10) === day) {
        return fromPackWindow(pack.windows[i], 0, true);
      }
    }
    return null;
  }

  function checkStartDanger(form) {
    var fields = readForm(form);
    var start;
    try {
      start = parseUtc(fields.start_utc);
    } catch (err) {
      return Promise.resolve();
    }
    var known = windowForStart(start);
    if (known) {
      if (isDangerous(known)) showDangerAlert(known, fields);
      else closeAlert();
      return Promise.resolve();
    }
    var duration = Number(fields.duration_hours || 6);
    var asOf = fields.mode === "current" ? null : start;
    var fallbackP = loadArchiveFallback(fields);
    return assessOne(start, duration, asOf).then(function (raw) {
      var mapped = mapWindow(raw, 0, true);
      if (!apiWindowEmpty(mapped)) return mapped;
      return fallbackP.then(function (pack) { return packWindowForStart(pack, start) || mapped; });
    }).catch(function () {
      return fallbackP.then(function (pack) { return packWindowForStart(pack, start); });
    }).then(function (window) {
      if (!window) return;
      if (isDangerous(window)) showDangerAlert(window, fields);
      else closeAlert();
    });
  }

  function bindStartWatch(form) {
    var input = form.elements.start_utc;
    if (!input) return;
    lastProbedStart = (input.value || "").trim();
    function schedule(immediate) {
      var value = (input.value || "").trim();
      if (value === lastProbedStart) return;
      clearTimeout(probeTimer);
      probeTimer = setTimeout(function () {
        var current = (input.value || "").trim();
        if (current !== value) return;
        lastProbedStart = current;
        checkStartDanger(form);
      }, immediate ? 40 : 650);
    }
    input.addEventListener("input", function () { schedule(false); });
    input.addEventListener("change", function () { schedule(true); });
    input.addEventListener("blur", function () { schedule(true); });
  }

  function bindAlert() {
    var modal = document.getElementById("eva-alert");
    var closeBtn = document.getElementById("eva-alert-close");
    if (closeBtn) closeBtn.addEventListener("click", closeAlert);
    if (modal) {
      modal.addEventListener("click", function (ev) {
        if (ev.target === modal) closeAlert();
      });
    }
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") closeAlert();
    });
  }

  function selectButton(el) {
    if (!el) return;
    var nodes = document.querySelectorAll("button.is-selected, a.btn.is-selected");
    Array.prototype.forEach.call(nodes, function (node) {
      node.classList.remove("is-selected");
      node.removeAttribute("aria-pressed");
    });
    el.classList.add("is-selected");
    el.setAttribute("aria-pressed", "true");
  }

  function buttonMatchesDemo(link, demo) {
    var href = (link.getAttribute("href") || "").toLowerCase();
    var key = String(demo || "").toLowerCase();
    if (!key) return false;
    return href.indexOf("demo=" + key) !== -1 || href.indexOf("/demo/" + key) !== -1;
  }

  function highlightCurrentDemo() {
    var demo = demoFromLocation();
    var links = document.querySelectorAll("a.btn");
    var matched = null;
    Array.prototype.forEach.call(links, function (link) {
      if (buttonMatchesDemo(link, demo)) matched = link;
    });
    if (matched) selectButton(matched);
  }

  function bindButtonSelect() {
    document.addEventListener("click", function (ev) {
      var btn = ev.target.closest("button, a.btn");
      if (!btn || btn.id === "eva-alert-close") return;
      selectButton(btn);
    });
  }

  function boot() {
    var form = document.getElementById("eva-form");
    if (!form || !useLiveApi()) return;
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      run(form);
    });
    var demo = demoFromLocation();
    activeDemo = demo;
    if (DEMOS[demo]) fillForm(form, DEMOS[demo]);
    bindAlert();
    bindStartWatch(form);
    bindButtonSelect();
    highlightCurrentDemo();
    run(form);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
