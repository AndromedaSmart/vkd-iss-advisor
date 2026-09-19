(function () {
  var GRADE_LEVEL = {
    benign: "none",
    elevated: "watch",
    adverse: "warning",
    insufficient_data: "unknown"
  };
  var DEMOS = {
    storm: { mode: "historical", start_utc: "2024-05-10 08:00", duration_hours: 6, interval_days: 4, search_hours: 12, cutoff_utc: "" },
    quiet: { mode: "historical", start_utc: "2024-06-18 08:00", duration_hours: 6, interval_days: 5, search_hours: 12, cutoff_utc: "" },
    gap: { mode: "historical", start_utc: "2024-06-01 08:00", duration_hours: 6, interval_days: 7, search_hours: 12, cutoff_utc: "" }
  };

  function apiBase() {
    var body = document.body;
    return (body && body.getAttribute("data-api-base")) || "http://46.29.164.87:8000";
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

  function addHours(dt, hours) {
    return new Date(dt.getTime() + hours * 3600 * 1000);
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

  function assessOne(start, duration, mode, asOf) {
    var payload = {
      window_start: toIso(start),
      duration_hours: duration,
      mode: mode,
      search_span_hours: 0,
      disabled_sources: []
    };
    if (asOf) payload.as_of = toIso(asOf);
    return postJson("/api/assess-window", payload);
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
      raw: raw
    };
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
      return "<li><div class=\"kind\">" + esc(ev.provenance || "external_forecast") +
        "</div><strong>" + esc(ev.statement || ev.rule_id || "") + "</strong>" +
        "<div class=\"small\">" + esc(ev.rule_description || "") + "</div>" +
        "<div class=\"src\">" + esc((ev.source_ids || []).join(", ")) + " · " + esc(ev.rule_id || "") + "</div></li>";
    }).join("") + "</ul>";
  }

  function render(windows, comparison, status, form) {
    var root = document.getElementById("results-root");
    if (!root) return;
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
    var table = windows.map(function (w) {
      var when = w.start.toISOString().replace("T", " ").replace(".000Z", " UTC") +
        " — " + w.end.toISOString().replace("T", " ").replace(".000Z", " UTC");
      return "<tr class=\"" + (w.preferred ? "preferred" : "") + "\">" +
        "<td class=\"num\">" + esc(w.start.toISOString().slice(0, 10)) + "</td>" +
        "<td class=\"num\">" + esc(w.id) + (w.requested ? " · запрос" : "") + (w.preferred ? " · выбор" : "") + "</td>" +
        "<td class=\"num\">" + esc(when) + "</td>" +
        "<td><span class=\"cover " + esc(w.tag) + "\">" + esc(w.labels.join(", ") || "дыра") + "</span></td>" +
        "<td>" + pill(w.sepLevel) + "</td>" +
        "<td>" + pill(w.mmodLevel) + "</td>" +
        "<td>" + pill(w.geoLevel) + "</td>" +
        "<td class=\"num\">" + esc(w.adverse) + "</td>" +
        "<td class=\"num\">" + esc(w.completeness) + (w.critical ? " · дыра" : "") + "</td></tr>";
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
    root.innerHTML =
      "<div class=\"meta-row\"><div>онлайн " + esc(apiBase()) + " · " + esc(form.mode) +
      " · окон " + windows.length + "</div></div>" +
      "<div class=\"banner\">Данные: ВКД-планировщик API " + esc(apiBase()) +
      " · overall " + esc((status && status.overall_status) || "—") + "</div>" +
      "<div class=\"decision\"><h2>" + esc(title) + "</h2><p>" + esc(comparison.reason) + "</p></div>" +
      "<section><h2>Сравнение окон по ответу API</h2><div class=\"table-wrap\"><table><thead><tr>" +
      "<th>День</th><th>Окно</th><th>Интервал UTC</th><th>Покрытие</th><th>SEP</th><th>MMOD</th><th>G (отдельно)</th><th>Неблагопр., мин</th><th>Полнота</th>" +
      "</tr></thead><tbody>" + table + "</tbody></table></div>" +
      "<p class=\"small\">Онлайн-стенд ходит в API. G и MMOD не суммируются с SEP.</p></section>" +
      "<section><h2>Доказательства по запрошенному окну</h2><div class=\"grid-2\">" + cards + "</div></section>" +
      "<section><h2>Источники API</h2><table><thead><tr><th>Источник</th><th>ID</th><th>Статус</th><th>Последние данные</th><th>Записей</th><th>Покрытие</th></tr></thead><tbody>" +
      srcRows + "</tbody></table></section>";
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
    var chain = Promise.resolve([]);
    starts.forEach(function (item) {
      chain = chain.then(function (acc) {
        var asOf = mode === "live" ? null : item;
        return assessOne(item, duration, mode, asOf).then(function (raw) {
          acc.push(raw);
          return acc;
        });
      });
    });
    return Promise.all([chain, statusP]).then(function (pair) {
      var assessments = pair[0];
      var status = pair[1];
      var windows = assessments.map(function (raw, idx) { return mapWindow(raw, idx, idx === 0); });
      render(windows, compare(windows), status, fields);
    }).catch(function (err) {
      if (root) root.innerHTML = "";
      if (banner) banner.textContent = "API " + apiBase() + ": " + err.message;
    });
  }

  function boot() {
    var form = document.getElementById("eva-form");
    if (!form || !isStatic()) return;
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      run(form);
    });
    var params = new URLSearchParams(window.location.search);
    var demo = params.get("demo");
    if (demo && DEMOS[demo]) fillForm(form, DEMOS[demo]);
    run(form);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
