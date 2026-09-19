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
  var SOURCE_CATALOG = [
    { id: "noaa_swpc", name: "NOAA SWPC Forecasts", role: "прогноз" },
    { id: "nasa_donki", name: "NASA DONKI Notifications", role: "прогноз" },
    { id: "spacetrack_tle", name: "Space-Track ISS TLE", role: "орбита" },
    { id: "goes_sgps", name: "GOES-R SGPS netCDF", role: "наблюдение" },
    { id: "swpc_3day", name: "NOAA SWPC 3-Day Forecast", role: "прогноз" },
    { id: "swpc_geomag", name: "NOAA SWPC Geomag Forecast", role: "прогноз" },
    { id: "donki_notifications", name: "NASA DONKI notifications", role: "прогноз" },
    { id: "donki_cme", name: "NASA DONKI CME analysis", role: "прогноз" },
    { id: "iss_gp_history", name: "Space-Track GP_HISTORY ISS 25544", role: "орбита" },
    { id: "socrates", name: "CelesTrak SOCRATES Plus ISS", role: "сближения" },
    { id: "goes_protons", name: "NOAA SWPC GOES integral protons", role: "наблюдение" },
    { id: "swpc_kp", name: "NOAA SWPC planetary K-index", role: "наблюдение" },
    { id: "noaa_scales", name: "NOAA Scales", role: "наблюдение" },
    { id: "celestrak_iss", name: "CelesTrak GP ISS (25544)", role: "орбита" },
    { id: "local_bundle", name: "Локальный набор data/", role: "каталог" },
    { id: "planner_api", name: "ВКД-планировщик", role: "каталог" }
  ];
  var SOURCE_NAMES = {
    test_swpc: "Тестовый прогноз NOAA SWPC",
    noaa_swpc: "Прогноз NOAA SWPC",
    swpc_3day: "Прогноз NOAA SWPC на трое суток",
    swpc_geomag: "Геомагнитный прогноз NOAA SWPC",
    goes_protons: "Измерения протонов GOES",
    goes_sgps: "Измерения GOES-R",
    swpc_kp: "Индекс Kp NOAA SWPC",
    nasa_donki: "Уведомления NASA DONKI",
    donki_notifications: "Уведомления NASA DONKI",
    donki_cme: "Каталог выбросов NASA DONKI",
    socrates: "Каталог сближений SOCRATES",
    orbit: "Орбита МКС",
    iss_gp_history: "Архив орбиты МКС",
    planner_api: "ВКД-планировщик",
    spacetrack_tle: "Орбита МКС, Space-Track",
    celestrak_iss: "Орбита МКС, CelesTrak"
  };
  var KIND_PLAIN = {
    external_forecast: "Чужой прогноз",
    observation: "Измерение",
    team_calc: "Наш расчёт",
    derived: "Наш расчёт"
  };
  var EVIDENCE_PHRASES = [
    ["протонный флюкс <10 pfu (normal)", "Поток протонов ниже 10 единиц. Это спокойный уровень, не радиационная буря."],
    ["протонный флюкс", "Поток протонов ниже порога бури. Это спокойный уровень."],
    ["протонный поток на нормальном уровне", "Радиация в норме: поток солнечных частиц не повышен."],
    ["прогноз swpc s1 or greater", "Прогноз радиационной бури от NOAA SWPC."],
    ["поток протонов goes", "Измерение потока солнечных частиц со спутника GOES."],
    ["ряд goes не покрывает окно", "Измерений GOES на это окно нет."],
    ["поток выше порога s", "В прогнозе SWPC поток выше спокойного уровня."],
    ["kp / шкала g", "Прогноз геомагнитной обстановки на трое суток."],
    ["текущий estimated kp", "Текущий индекс геомагнитной активности (Kp)."],
    ["socrates отключён", "Каталог сближений в историческом режиме не используется."],
    ["socrates недоступен", "Каталог сближений недоступен."],
    ["сближений iss в окне", "Крупных сближений с МКС в этом окне нет."],
    ["вероятность strong–extreme storm", "Вероятность сильной геомагнитной бури."],
    ["вероятность strong-extreme storm", "Вероятность сильной геомагнитной бури."],
    ["ap из geomag forecast", "Индекс геомагнитной активности из прогноза NOAA SWPC."],
    ["прогноз swpc r3 or greater", "Прогноз сильного радиозатмения от NOAA SWPC."],
    ["прогноз swpc r1", "Прогноз радиозатмения от NOAA SWPC."],
    ["пересечение воздействий с окном", "Насколько окно пересекается с неблагоприятными условиями."],
    ["отсутствие ряда не равно s0", "Нет измерений — это не значит, что радиации нет."],
    ["нет данных ≠ нет сближения", "Нет данных не значит, что сближений нет."],
    ["не складывается с sep", "Отдельный прогноз. Не складывается с радиацией."],
    ["шкала g отдельно от sep", "Геомагнитная шкала показывается отдельно от радиации."],
    ["g3+ на сутки окна", "Сильная буря (G3 и выше) на сутки этого окна."],
    ["это не отсутствие сближений", "Это не значит, что сближений нет. Исторический каталог не подменяется текущим."],
    ["прокси обстановки, не доза", "Это оценка обстановки, не доза в скафандре."]
  ];
  var RULE_PHRASES = [
    ["sep.threshold.normal", "Спокойный уровень радиации"],
    ["sep.threshold.s1", "Порог радиационной бури"],
    ["sep.threshold", "Порог радиации"],
    ["неполнота наблюдения", "Неполное измерение"],
    ["отказ источника не all-clear", "Сбой источника — это не «всё спокойно»"],
    ["t4: не смешивать эпоху каталога", "Нельзя подставлять сегодняшний каталог в прошлое"],
    ["observed s-storm", "В прогнозе отмечена радиационная буря"],
    ["planetary k-index", "Планетарный индекс геомагнитной активности"],
    ["в сводку sep не входит", "В оценку радиации не входит"]
  ];
  var SOURCE_ALIASES = {
    orbit: "iss_gp_history"
  };
  var SKIP_REASONS = { "": 1, ok: 1, "нет": 1, "n/a": 1, "-": 1, none: 1 };
  var REASON_RULES = [
    {
      needle: "протонного потока",
      yes: "Есть прогноз радиации: солнечные частицы (протоны) от NOAA SWPC.",
      no: "Нет прогноза радиации (солнечные частицы) на это окно."
    },
    {
      needle: "есть прогнозы swpc",
      yes: "Есть прогноз радиации от NOAA SWPC.",
      no: ""
    },
    {
      needle: "прогнозы kp",
      yes: "Есть прогноз геомагнитной обстановки (индекс Kp).",
      no: "Нет прогноза геомагнитной обстановки на это окно."
    },
    {
      needle: "метеорн",
      yes: "Есть сведения об обломках и метеорных потоках.",
      no: "Нет сведений об обломках и метеорных потоках."
    },
    {
      needle: "данных sep",
      yes: "Есть данные по радиации.",
      no: "Нет данных по радиации (солнечные частицы)."
    },
    {
      needle: "только внешний прогноз",
      yes: "Оценка только по чужому прогнозу, без измерений.",
      no: ""
    }
  ];

  function plainReason(text) {
    var raw = String(text || "").replace(/\s+/g, " ").trim();
    if (!raw || SKIP_REASONS[raw.toLowerCase()]) return "";
    var key = raw.toLowerCase();
    for (var i = 0; i < REASON_RULES.length; i += 1) {
      var rule = REASON_RULES[i];
      if (key.indexOf(rule.needle) === -1) continue;
      if (rule.no && key.indexOf("нет") === 0) return rule.no;
      return rule.yes;
    }
    if (raw.length <= 80 && (key.indexOf("есть") === 0 || key.indexOf("нет") === 0)) return raw;
    return "";
  }

  function completenessNote(w) {
    var value = Number(w && w.completeness);
    var hole;
    if ((w && w.critical) || !(value > 0)) {
      hole = "Дыра — нет данных по радиации на эти сутки. Пустое место не значит, что безопасно.";
    } else if (value < 1) {
      hole = "Частичная дыра — известны не все данные по радиации и геомагнетизму.";
    } else {
      hole = "Дыры нет: данные по радиации и геомагнетизму на эти сутки есть.";
    }
    var extras = [];
    [w && w.reason, w && w.sep && w.sep.confidence_reason, w && w.geo && w.geo.confidence_reason].forEach(function (item) {
      var plain = plainReason(item);
      if (plain && extras.indexOf(plain) === -1 && hole.indexOf(plain) === -1) extras.push(plain);
    });
    return extras.length ? hole + " " + extras.join(" ") : hole;
  }

  var ROLE_LABEL = {
    catalog: "каталог",
    external_forecast: "прогноз",
    observation: "наблюдение"
  };
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
  var lastAlertedKey = "";
  var probeTimer = null;
  var warningLog = [];
  var LEVEL_WORD = {
    none: "спокойно",
    watch: "нужно внимание",
    warning: "опасно",
    high: "очень опасно",
    unknown: "нет данных"
  };
  var userScenarios = [];
  var SCENARIO_STORE = "vkd-user-scenarios";

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

  function parseWall(text) {
    var match = String(text || "").trim().match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/);
    if (!match) throw new Error("Некорректная дата: " + text);
    return {
      y: Number(match[1]),
      mo: Number(match[2]),
      d: Number(match[3]),
      h: Number(match[4]),
      mi: Number(match[5]),
      s: Number(match[6] || 0)
    };
  }

  function formatWallUtc(dt) {
    return dt.getUTCFullYear() + "-" + pad(dt.getUTCMonth() + 1) + "-" + pad(dt.getUTCDate()) +
      " " + pad(dt.getUTCHours()) + ":" + pad(dt.getUTCMinutes());
  }

  function tzOffsetMs(date, tz) {
    if (!tz || tz === "UTC") return 0;
    var dtf = new Intl.DateTimeFormat("en-US", {
      timeZone: tz,
      hour12: false,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    });
    var map = {};
    dtf.formatToParts(date).forEach(function (part) {
      if (part.type !== "literal") map[part.type] = part.value;
    });
    var hour = Number(map.hour === "24" ? 0 : map.hour);
    var asUTC = Date.UTC(Number(map.year), Number(map.month) - 1, Number(map.day), hour, Number(map.minute), Number(map.second));
    return asUTC - date.getTime();
  }

  function wallToUtc(text, tz) {
    var parts = parseWall(text);
    var guess = Date.UTC(parts.y, parts.mo - 1, parts.d, parts.h, parts.mi, parts.s);
    if (!tz || tz === "UTC") return new Date(guess);
    var i;
    for (i = 0; i < 3; i += 1) {
      guess = Date.UTC(parts.y, parts.mo - 1, parts.d, parts.h, parts.mi, parts.s) - tzOffsetMs(new Date(guess), tz);
    }
    return new Date(guess);
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
      timeline: raw.timeline || [],
      archive: false,
      reason: sep.confidence_reason || geo.confidence_reason || "",
      completeness_note: raw.completeness_note || "",
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
      timeline: w.timeline || [],
      archive: true,
      reason: sep.confidence_reason || "",
      completeness_note: w.completeness_note || "",
      donkiCount: Number((w.donki && w.donki.count) || 0),
      cmeCount: Number((w.cme && w.cme.count) || 0)
    };
  }

  function attachPackTimeline(windows, pack) {
    if (!pack || !pack.windows) return windows;
    var byDay = {};
    pack.windows.forEach(function (item) {
      var key = String(item.start || "").slice(0, 10);
      if (key && item.timeline && item.timeline.length) byDay[key] = item.timeline;
    });
    windows.forEach(function (w) {
      if (w.timeline && w.timeline.length >= 2) return;
      var day = w.start && w.start.toISOString().slice(0, 10);
      if (day && byDay[day]) w.timeline = byDay[day];
    });
    return windows;
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

  function applyPhrases(text, rules) {
    var raw = String(text || "").replace(/\s+/g, " ").trim();
    if (!raw) return "";
    var key = raw.toLowerCase();
    for (var i = 0; i < rules.length; i += 1) {
      if (key.indexOf(rules[i][0]) !== -1) return rules[i][1];
    }
    var kp = raw.match(/kp\s*=\s*([\d.]+)/i);
    if (kp && key.indexOf("g1") !== -1) {
      return "Прогноз геомагнитной активности: Kp " + kp[1] + ", ниже уровня бури.";
    }
    return raw;
  }

  function plainKind(kind) {
    return KIND_PLAIN[String(kind || "").toLowerCase()] || "Чужой прогноз";
  }

  function plainSource(source) {
    return String(source || "").split(/[,;]/).map(function (item) {
      var key = item.replace(/\s+/g, " ").trim();
      return SOURCE_NAMES[key] || SOURCE_NAMES[key.toLowerCase()] || key;
    }).filter(Boolean).join(", ");
  }

  function plainRule(text) {
    var raw = String(text || "").replace(/\s+/g, " ").trim();
    if (!raw) return "";
    var mapped = applyPhrases(raw, RULE_PHRASES);
    if (mapped !== raw) return mapped;
    if (raw.indexOf(".") !== -1 && raw.indexOf(" ") === -1) return "";
    return raw;
  }

  function evidenceHtml(factor) {
    var rows = factor.evidence || [];
    if (!rows.length) return "<p class=\"small\">Нет свидетельств в ответе API.</p>";
    return "<ul class=\"evidence\">" + rows.map(function (ev) {
      var title = applyPhrases(ev.statement || ev.title || "", EVIDENCE_PHRASES) || ev.statement || ev.title || "";
      var detail = applyPhrases(ev.rule_description || ev.detail || "", EVIDENCE_PHRASES);
      var source = plainSource((ev.source_ids || []).join(", ") || ev.source_id || "");
      var rule = plainRule(ev.rule_id || ev.rule || "");
      var srcLine = [source, rule].filter(Boolean).join(" · ");
      return "<li><div class=\"kind\">" + esc(plainKind(ev.provenance || ev.kind)) +
        "</div><strong>" + esc(title) + "</strong>" +
        (detail ? "<div class=\"small\">" + esc(detail) + "</div>" : "") +
        (srcLine ? "<div class=\"src\">" + esc(srcLine) + "</div>" : "") + "</li>";
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

  function downloadBlob(filename, mime, data) {
    var blob = data instanceof Blob ? data : new Blob([data], { type: mime });
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () { URL.revokeObjectURL(url); }, 800);
  }

  var CRC32_TABLE = (function () {
    var table = new Uint32Array(256);
    for (var n = 0; n < 256; n += 1) {
      var c = n;
      for (var k = 0; k < 8; k += 1) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
      table[n] = c >>> 0;
    }
    return table;
  })();

  function crc32(bytes) {
    var c = 0xFFFFFFFF;
    for (var i = 0; i < bytes.length; i += 1) {
      c = CRC32_TABLE[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
    }
    return (c ^ 0xFFFFFFFF) >>> 0;
  }

  function u16(n) {
    return new Uint8Array([n & 0xff, (n >>> 8) & 0xff]);
  }

  function u32(n) {
    return new Uint8Array([n & 0xff, (n >>> 8) & 0xff, (n >>> 16) & 0xff, (n >>> 24) & 0xff]);
  }

  function concatBytes(parts) {
    var total = 0;
    var arrays = parts.map(function (part) {
      return part instanceof Uint8Array ? part : new Uint8Array(part);
    });
    arrays.forEach(function (arr) { total += arr.length; });
    var out = new Uint8Array(total);
    var offset = 0;
    arrays.forEach(function (arr) {
      out.set(arr, offset);
      offset += arr.length;
    });
    return out;
  }

  function zipStore(files) {
    var encoder = new TextEncoder();
    var locals = [];
    var centrals = [];
    var offset = 0;
    files.forEach(function (file) {
      var name = encoder.encode(file.name);
      var data = typeof file.data === "string" ? encoder.encode(file.data) : file.data;
      var crc = crc32(data);
      var local = concatBytes([
        [0x50, 0x4b, 0x03, 0x04],
        [0x14, 0x00],
        [0x00, 0x08],
        [0x00, 0x00],
        [0x00, 0x00, 0x00, 0x00],
        u32(crc),
        u32(data.length),
        u32(data.length),
        u16(name.length),
        [0x00, 0x00],
        name,
        data
      ]);
      var central = concatBytes([
        [0x50, 0x4b, 0x01, 0x02],
        [0x14, 0x00, 0x14, 0x00],
        [0x00, 0x08],
        [0x00, 0x00],
        [0x00, 0x00, 0x00, 0x00],
        u32(crc),
        u32(data.length),
        u32(data.length),
        u16(name.length),
        [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
        [0x00, 0x00],
        [0x00, 0x00],
        [0x00, 0x00, 0x00, 0x00],
        u32(offset),
        name
      ]);
      locals.push(local);
      centrals.push(central);
      offset += local.length;
    });
    var centralSize = 0;
    centrals.forEach(function (part) { centralSize += part.length; });
    var eocd = concatBytes([
      [0x50, 0x4b, 0x05, 0x06],
      [0x00, 0x00, 0x00, 0x00],
      u16(files.length),
      u16(files.length),
      u32(centralSize),
      u32(offset),
      [0x00, 0x00]
    ]);
    return concatBytes(locals.concat(centrals).concat([eocd]));
  }

  function serializeWarning(item) {
    return {
      at: item.at instanceof Date ? formatUtc(item.at) : String(item.at || ""),
      title: item.title || "",
      body: item.body || "",
      radiation_sep: item.sep || "",
      mmod: item.mmod || "",
      geomagnetic: item.geo || ""
    };
  }

  function journalArchiveName() {
    var stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    return "vkd-journal-" + stamp + ".zip";
  }

  function downloadJournalArchive() {
    var rows = warningLog.map(serializeWarning);
    var json = JSON.stringify({
      generated_at: new Date().toISOString(),
      algorithm: algorithm(),
      count: rows.length,
      warnings: rows
    }, null, 2);
    var cols = ["at", "title", "body", "radiation_sep", "mmod", "geomagnetic"];
    var csv = cols.join(",") + "\n" + rows.map(function (row) {
      return cols.map(function (key) { return csvCell(row[key]); }).join(",");
    }).join("\n") + (rows.length ? "\n" : "");
    downloadBlob(journalArchiveName(), "application/zip", zipStore([
      { name: "journal.json", data: json },
      { name: "journal.csv", data: csv }
    ]));
  }

  function bindJournalExport() {
    var btn = document.getElementById("export-journal");
    if (!btn) return;
    btn.onclick = function () {
      downloadJournalArchive();
    };
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

  function formatUtc(dt) {
    return dt.toISOString().replace("T", " ").replace(".000Z", "") + " UTC";
  }

  function windowLabel(idOrWindow) {
    var raw = "";
    if (idOrWindow && typeof idOrWindow === "object") raw = String(idOrWindow.id || idOrWindow.label || "");
    else raw = String(idOrWindow || "");
    if (!raw) return "Вариант";
    var archive = raw.indexOf("A-") === 0;
    var match = raw.match(/W(\d+)$/i);
    var num = match ? match[1] : "";
    if (archive) return num ? "Архив " + num : "Архив";
    if (/^W\d+$/i.test(raw) && num) return "Вариант " + num;
    return raw;
  }

  function thHead(opts) {
    var html = "<th class=\"" + esc(opts.cls || "") + "\">";
    if (opts.abbr) html += "<div class=\"th-abbr\">" + esc(opts.abbr) + "</div>";
    html += "<div class=\"th-word\">" + esc(opts.word) + "</div>";
    if (opts.hint) html += "<div class=\"th-hint\">" + esc(opts.hint) + "</div>";
    return html + "</th>";
  }

  function openPane(id) {
    var panes = document.querySelectorAll(".pane");
    Array.prototype.forEach.call(panes, function (pane) {
      pane.classList.toggle("is-open", pane.id === "pane-" + id);
    });
    var tiles = document.querySelectorAll(".tile");
    Array.prototype.forEach.call(tiles, function (tile) {
      var selected = tile.getAttribute("data-pane") === id;
      tile.classList.toggle("is-selected", selected);
      tile.setAttribute("aria-pressed", selected ? "true" : "false");
    });
  }

  function bindTiles() {
    document.addEventListener("click", function (ev) {
      var tile = ev.target.closest(".tile");
      if (!tile) return;
      ev.preventDefault();
      openPane(tile.getAttribute("data-pane"));
    });
  }

  function sourceKey(row) {
    return String((row && (row.id || row.source_id || row.name)) || "").toLowerCase();
  }

  function normalizeSource(row) {
    row = row || {};
    var id = row.id || row.source_id || "";
    var ok = row.ok;
    if (ok == null && row.status) ok = row.status === "available";
    var status = row.status;
    if (!status) {
      if (ok === true) status = "ok";
      else if (ok === false) status = "ошибка";
      else status = "не получено";
    }
    var role = ROLE_LABEL[row.role] || row.role || "";
    var note = row.notes || row.error || "";
    if (row.record_count != null) {
      var span = ((row.coverage_start || "") + " — " + (row.coverage_end || "")).replace(/^\s*—\s*$/, "");
      var extra = "записей " + row.record_count;
      if (span) extra += "; покрытие " + span;
      note = note ? note + "; " + extra : extra;
    }
    return {
      id: id,
      name: row.name || id || "источник",
      role: role,
      status: status,
      published: row.published_at || row.last_data_time || "",
      fetched: row.fetched_at || "",
      notes: note,
      url: row.url || ""
    };
  }

  function collectSources(status, pack, windows) {
    var byId = {};
    function add(row, overwrite) {
      var item = normalizeSource(row);
      var key = sourceKey(item);
      if (!key) return;
      var prev = byId[key];
      if (!prev) {
        byId[key] = item;
        return;
      }
      if (!overwrite && prev.status !== "не получено") return;
      ["name", "role", "status", "published", "fetched", "notes", "url", "id"].forEach(function (field) {
        if (item[field]) prev[field] = item[field];
      });
    }
    SOURCE_CATALOG.forEach(function (row) {
      add({ id: row.id, name: row.name, role: row.role, status: "не получено" });
    });
    ((pack && pack.sources) || []).forEach(function (row) { add(row, true); });
    ((status && status.sources) || []).forEach(function (row) { add(row, true); });
    (windows || []).forEach(function (w) {
      [w.sep, w.mmod, w.geo].forEach(function (block) {
        ((block && block.evidence) || []).forEach(function (ev) {
          var ids = (ev.source_ids || []).slice();
          if (ev.source_id) ids.unshift(ev.source_id);
          ids.forEach(function (id) {
            if (!id) return;
            var alias = SOURCE_ALIASES[id];
            if (alias && byId[alias.toLowerCase()]) return;
            var key = String(id).toLowerCase();
            if (!byId[key]) {
              add({ id: id, name: SOURCE_NAMES[id] || id, role: "свидетельство", status: "использован" });
            }
          });
        });
      });
    });
    var out = [];
    var seen = {};
    SOURCE_CATALOG.forEach(function (row) {
      var key = row.id.toLowerCase();
      if (byId[key]) {
        out.push(byId[key]);
        seen[key] = true;
      }
    });
    Object.keys(byId).forEach(function (key) {
      if (!seen[key]) out.push(byId[key]);
    });
    return out;
  }

  var DANGER_LINES = [
    { key: "sep", name: "Радиация", color: "#e05d4c" },
    { key: "mmod", name: "Обломки", color: "#5b8def" },
    { key: "geo", name: "Геомагнетизм", color: "#9b7ed9" }
  ];

  function dangerOfLevel(level) {
    if (level === "high") return 4;
    if (level === "warning") return 3;
    if (level === "watch") return 2;
    if (level === "none") return 1;
    return 1.6;
  }

  function pickPreferredWindow(windows, comparison) {
    var id = comparison && comparison.preferred;
    var found = null;
    (windows || []).forEach(function (w) {
      if (!found && id && w.id === id) found = w;
    });
    if (found) return found;
    (windows || []).forEach(function (w) {
      if (!found && w.preferred) found = w;
    });
    if (found) return found;
    (windows || []).forEach(function (w) {
      if (!found && w.requested) found = w;
    });
    return (windows || [])[0] || null;
  }

  function dayBoundsUtc(dt) {
    var start = Date.UTC(dt.getUTCFullYear(), dt.getUTCMonth(), dt.getUTCDate(), 0, 0, 0, 0);
    return { t0: start, t1: start + 24 * 3600 * 1000 };
  }

  function parseTimelinePoint(point) {
    var t = point.t instanceof Date ? point.t.getTime() : Date.parse(point.t);
    if (!isFinite(t)) return null;
    return { t: t, sep: point.sep, mmod: point.mmod, geo: point.geo };
  }

  function intervalBounds(windows, form, pack) {
    var req = (pack && pack.request) || {};
    var range = pack && pack.chart_range;
    if (range && range.start && range.end) {
      var rangeStart = Date.parse(range.start);
      var rangeEnd = Date.parse(range.end);
      if (isFinite(rangeStart) && isFinite(rangeEnd) && rangeEnd > rangeStart) {
        return {
          t0: rangeStart,
          t1: rangeEnd,
          days: Math.max(1, Math.round((rangeEnd - rangeStart) / 86400000))
        };
      }
    }
    var days = Number(req.interval_days || (form && form.interval_days) || 0);
    var start = null;
    if (form && form.start_dt instanceof Date && !isNaN(form.start_dt.getTime())) start = form.start_dt;
    if (!start && req.start) start = new Date(req.start);
    if (!start && windows && windows[0] && windows[0].start) start = windows[0].start;
    if (!start) return null;
    if (!days) {
      var last = windows && windows[windows.length - 1];
      days = last && last.start
        ? Math.round((dayBoundsUtc(last.start).t0 - dayBoundsUtc(start).t0) / 86400000) + 1
        : 1;
    }
    days = Math.max(1, days);
    var t0 = dayBoundsUtc(start).t0;
    return { t0: t0, t1: t0 + days * 86400000, days: days };
  }

  function collectChartPoints(windows, pack) {
    var points = [];
    ((pack && pack.chart_timeline) || []).forEach(function (row) {
      var point = parseTimelinePoint(row);
      if (point) points.push(point);
    });
    if (points.length >= 2) return points;
    (windows || []).forEach(function (w) {
      (w.timeline || []).forEach(function (row) {
        var point = parseTimelinePoint(row);
        if (point) points.push(point);
      });
    });
    if (points.length >= 2) {
      points.sort(function (a, b) { return a.t - b.t; });
      return points;
    }
    (windows || []).forEach(function (w) {
      if (!w.start) return;
      var day = dayBoundsUtc(w.start);
      points.push({ t: day.t0, sep: w.sepLevel, mmod: w.mmodLevel, geo: w.geoLevel });
      points.push({ t: day.t1, sep: w.sepLevel, mmod: w.mmodLevel, geo: w.geoLevel });
    });
    points.sort(function (a, b) { return a.t - b.t; });
    return points;
  }

  function chartTimeLabel(ms, t1, multiDay) {
    var dt = new Date(ms);
    if (t1 && ms >= t1 && dt.getUTCHours() === 0 && dt.getUTCMinutes() === 0) {
      var prev = new Date(ms - 1);
      return multiDay
        ? pad(prev.getUTCMonth() + 1) + "-" + pad(prev.getUTCDate()) + " 24:00"
        : "24:00";
    }
    if (multiDay) {
      var date = pad(dt.getUTCMonth() + 1) + "-" + pad(dt.getUTCDate());
      if (dt.getUTCHours() === 0 && dt.getUTCMinutes() === 0) return date;
      return date + " " + pad(dt.getUTCHours()) + ":" + pad(dt.getUTCMinutes());
    }
    return pad(dt.getUTCHours()) + ":" + pad(dt.getUTCMinutes());
  }

  function chartTimeTicks(t0, t1) {
    var span = t1 - t0;
    var step = 3 * 3600000;
    if (span > 8 * 86400000) step = 2 * 86400000;
    else if (span > 6 * 86400000) step = 86400000;
    else if (span > 36 * 3600000) step = 12 * 3600000;
    else if (span <= 12 * 3600000) step = 60 * 60 * 1000;
    var ticks = [t0];
    var t = t0 + step;
    while (t < t1 - step * 0.2) {
      ticks.push(t);
      t += step;
    }
    ticks.push(t1);
    return ticks;
  }

  function compareChartHtml(windows, comparison, form, meta) {
    var preferred = pickPreferredWindow(windows, comparison);
    if (!preferred) return "";
    var pack = (meta && meta.pack) || {};
    var bounds = intervalBounds(windows, form, pack);
    var series = collectChartPoints(windows, pack);
    if (!bounds || series.length < 2) return "";
    var t0 = bounds.t0;
    var t1 = bounds.t1;
    var multiDay = bounds.days > 1;
    var winStart = preferred.start.getTime();
    var winEnd = preferred.end.getTime();
    var width = 920;
    var height = 400;
    var left = 74;
    var right = 28;
    var top = 28;
    var bottom = 62;
    var plotW = width - left - right;
    var plotH = height - top - bottom;
    var yMin = 0.6;
    var yMax = 4.35;
    function xOf(t) {
      var clamped = Math.max(t0, Math.min(t1, t));
      return left + ((clamped - t0) / Math.max(1, t1 - t0)) * plotW;
    }
    function yOf(v) { return top + (1 - (v - yMin) / (yMax - yMin)) * plotH; }
    var bands = [
      { a: 3, b: 4.35, fill: "rgba(196,92,74,0.20)" },
      { a: 2, b: 3, fill: "rgba(201,132,42,0.12)" },
      { a: 0.6, b: 2, fill: "rgba(125,154,106,0.10)" }
    ];
    var svg = [];
    svg.push("<svg class=\"compare-plot\" viewBox=\"0 0 " + width + " " + height +
      "\" role=\"img\" aria-label=\"Опасности предпочтительного окна\">");
    bands.forEach(function (band) {
      svg.push("<rect x=\"" + left + "\" y=\"" + yOf(band.b) + "\" width=\"" + plotW + "\" height=\"" +
        (yOf(band.a) - yOf(band.b)) + "\" fill=\"" + band.fill + "\" />");
    });
    var bandX = xOf(Math.max(t0, winStart));
    var bandW = xOf(Math.min(t1, winEnd)) - bandX;
    if (bandW > 1) {
      svg.push("<rect x=\"" + bandX.toFixed(1) + "\" y=\"" + top + "\" width=\"" + bandW.toFixed(1) +
        "\" height=\"" + plotH + "\" fill=\"rgba(212,160,23,0.14)\" stroke=\"rgba(212,160,23,0.4)\" />");
      svg.push("<text x=\"" + (bandX + bandW / 2).toFixed(1) + "\" y=\"" + (top + 14) +
        "\" text-anchor=\"middle\" class=\"chart-pref-label\">интервал выхода</text>");
    }
    [1, 2, 3, 4].forEach(function (tick) {
      svg.push("<line x1=\"" + left + "\" y1=\"" + yOf(tick) + "\" x2=\"" + (left + plotW) +
        "\" y2=\"" + yOf(tick) + "\" class=\"chart-grid\" />");
    });
    chartTimeTicks(t0, t1).forEach(function (tick) {
      var gx = xOf(tick);
      svg.push("<line x1=\"" + gx + "\" y1=\"" + top + "\" x2=\"" + gx + "\" y2=\"" + (top + plotH) +
        "\" class=\"chart-grid\" />");
      svg.push("<text x=\"" + gx + "\" y=\"" + (top + plotH + 18) +
        "\" text-anchor=\"middle\" class=\"chart-axis\">" + chartTimeLabel(tick, t1, multiDay) + "</text>");
    });
    svg.push("<line x1=\"" + left + "\" y1=\"" + (top + plotH) + "\" x2=\"" + (left + plotW) +
      "\" y2=\"" + (top + plotH) + "\" class=\"chart-axis-line\" />");
    [[1, "none"], [2, "watch"], [3, "warning"], [4, "high"]].forEach(function (pair) {
      svg.push("<text x=\"" + (left - 8) + "\" y=\"" + (yOf(pair[0]) + 4) +
        "\" text-anchor=\"end\" class=\"chart-axis\">" + pair[1] + "</text>");
    });
    var showDots = series.length <= 16;
    DANGER_LINES.forEach(function (line) {
      var d = series.map(function (point, idx) {
        return (idx ? "L" : "M") + xOf(point.t).toFixed(1) + " " + yOf(dangerOfLevel(point[line.key])).toFixed(1);
      }).join(" ");
      svg.push("<path d=\"" + d + "\" fill=\"none\" stroke=\"" + line.color +
        "\" stroke-width=\"2.2\" stroke-linejoin=\"round\" stroke-linecap=\"round\" />");
      if (showDots) {
        series.forEach(function (point) {
          svg.push("<circle cx=\"" + xOf(point.t).toFixed(1) + "\" cy=\"" +
            yOf(dangerOfLevel(point[line.key])).toFixed(1) + "\" r=\"3\" fill=\"" + line.color + "\" />");
        });
      }
    });
    svg.push("<text x=\"16\" y=\"" + (top + plotH / 2) +
      "\" transform=\"rotate(-90 16 " + (top + plotH / 2) +
      ")\" text-anchor=\"middle\" class=\"chart-title\">Уровень опасности</text>");
    svg.push("</svg>");
    var keys = DANGER_LINES.map(function (line) {
      return "<span class=\"compare-chart-key\"><i style=\"background:" + line.color +
        "\"></i>" + esc(line.name) + "</span>";
    }).join("");
    var startLabel = new Date(t0).toISOString().slice(0, 10);
    var endLabel = new Date(t1 - 1).toISOString().slice(0, 10);
    var rangeLabel = bounds.days + " сут, " + startLabel + " — " + endLabel + " UTC";
    var heading = "Опасности за интервал запроса";
    if (comparison && comparison.decision === "prefer") {
      heading += " · " + windowLabel(preferred);
    }
    return "<figure class=\"compare-chart\">" +
      "<h3>" + esc(heading) + "</h3>" +
      svg.join("") +
      "<div class=\"compare-chart-legend\">" + keys + "</div>" +
      "<p class=\"small compare-chart-note\">Ось X — интервал из Запроса (" + esc(rangeLabel) +
      "). Золотая заливка — выбранный выход. Каждая линия — один вид опасности. G не суммируется с SEP.</p>" +
      "</figure>";
  }

  function render(windows, comparison, status, form, meta) {
    var compareRoot = document.getElementById("compare-root");
    var evidenceRoot = document.getElementById("evidence-root");
    var sourcesRoot = document.getElementById("sources-root");
    if (!compareRoot) return;
    meta = meta || {};
    windows.forEach(function (w) {
      w.preferred = comparison.preferred === w.id;
    });
    var title = comparison.decision === "prefer"
      ? "Предпочтительное окно: " + windowLabel(comparison.preferred)
      : comparison.decision === "equivalent"
        ? "Окна равнозначны"
        : "Недостаточно оснований для рекомендации";
    var sourceList = collectSources(status, meta.pack, windows);
    var srcRows = sourceList.map(function (s) {
      var note = esc(s.notes || "");
      if (s.url && s.url !== "#" && /^https?:/i.test(s.url)) {
        note += (note ? " " : "") + "<a href=\"" + esc(s.url) + "\">ссылка</a>";
      }
      return "<tr><td>" + esc(s.name) + "</td><td>" + esc(s.role || s.id) + "</td><td>" +
        esc(s.status) + "</td><td class=\"num\">" + esc(s.published || "—") +
        "</td><td class=\"num\">" + esc(s.fetched || "—") +
        "</td><td class=\"small\">" + (note || "—") + "</td></tr>";
    }).join("");
    var showDonki = windows.some(function (w) { return Number(w.donkiCount || 0) > 0; });
    var table = windows.map(function (w) {
      var coverLabel = w.labels.join(", ") || "дыра";
      return "<tr class=\"" + (w.preferred ? "preferred" : "") + "\">" +
        "<td class=\"num\">" + esc(w.start.toISOString().slice(0, 10)) + "</td>" +
        "<td class=\"num\">" + esc(windowLabel(w)) + (w.requested ? " · запрос" : "") + (w.preferred ? " · выбор" : "") + "</td>" +
        "<td class=\"num interval-range\"><div>" + esc(formatUtc(w.start)) + "</div><div>" + esc(formatUtc(w.end)) + "</div></td>" +
        "<td><span class=\"cover " + esc(w.tag) + "\">" + esc(coverLabel) + "</span></td>" +
        "<td>" + pill(w.sepLevel) + "</td>" +
        "<td>" + pill(w.mmodLevel) + "</td>" +
        "<td>" + pill(w.geoLevel) + "</td>" +
        (showDonki ? "<td class=\"num\">" + esc(w.donkiCount || 0) + "</td>" : "") +
        "<td class=\"num\">" + esc(w.adverse) + "</td>" +
        "<td class=\"num\">" + esc(w.completeness) + (w.critical ? " · дыра" : "") +
        "<div class=\"small completeness-note\">" + esc(completenessNote(w)) + "</div>" +
        "</td></tr>";
    }).join("");
    var first = windows[0];
    var cards = first ? [
      { title: "Радиация (солнечные частицы)", level: first.sepLevel, block: first.sep },
      { title: "Обломки и метеороиды", level: first.mmodLevel, block: first.mmod },
      { title: "Геомагнитная обстановка (не складывается с радиацией)", level: first.geoLevel, block: first.geo }
    ].map(function (card) {
      return "<div class=\"card\"><header><span>" + esc(card.title) + "</span>" + pill(card.level) +
        "</header><p class=\"small\">" + esc(plainReason(card.block.confidence_reason) || card.block.confidence_reason || "") + "</p>" +
        evidenceHtml(card.block) + "</div>";
    }).join("") : "";
    lastExport = buildExport(windows, comparison, status, form);
    lastWindows = windows;
    if (!meta.preview) {
      maybeAlertWindow(alertTarget(windows));
    }
    compareRoot.innerHTML =
      "<div class=\"meta-row\"><div></div>" +
      "<div class=\"export-actions\">" +
      "<button type=\"button\" class=\"btn ghost\" id=\"export-json\">Выгрузить JSON</button>" +
      "<button type=\"button\" class=\"btn ghost\" id=\"export-csv\">Выгрузить CSV</button>" +
      "</div></div>" +
      "<h2>Сравнение окон для ВКД</h2><div class=\"table-wrap\"><table><thead><tr>" +
      thHead({ cls: "col-day", word: "День" }) +
      thHead({ cls: "col-window", word: "Вариант", hint: "номер сравниваемого выхода" }) +
      thHead({ cls: "col-interval", word: "Интервал", hint: "UTC · ГГГГ-ММ-ДД чч:мм:сс" }) +
      thHead({ cls: "col-coverage", word: "Покрытие" }) +
      thHead({ cls: "col-sep", word: "Радиация", hint: "солнечные энергичные частицы" }) +
      thHead({ cls: "col-mmod", word: "Обломки", hint: "микрометеороиды и орбитальный мусор" }) +
      thHead({ cls: "col-geo", word: "Геомагнетизм", hint: "шкала G, отдельно от радиации" }) +
      (showDonki ? thHead({ cls: "col-donki", word: "DONKI" }) : "") +
      thHead({ cls: "col-adverse", word: "Неблагоприятные минуты", hint: "минуты окна с уровнем warning+" }) +
      thHead({ cls: "col-completeness", word: "Полнота", hint: "есть ли данные; дыра — нет данных, это не спокойно" }) +
      "</tr></thead><tbody>" + table + "</tbody></table></div>" +
      "<div class=\"decision\"><h2>" + esc(title) + "</h2><p>" + esc(comparison.reason) + "</p></div>" +
      compareChartHtml(windows, comparison, form, meta);
    if (evidenceRoot) {
      evidenceRoot.innerHTML = first
        ? "<h2>Доказательства по запрошенному окну</h2><div class=\"grid-2\">" + cards + "</div>"
        : "<p class=\"small\">Доказательства появятся после расчёта.</p>";
    }
    if (sourcesRoot) {
      sourcesRoot.innerHTML = "<h2>Источники</h2><div class=\"table-wrap\"><table><thead><tr>" +
        "<th>Источник</th><th>Роль</th><th>Статус</th><th>Публикация</th><th>Получено</th><th>Примечание</th>" +
        "</tr></thead><tbody>" + srcRows + "</tbody></table></div>";
    }
    bindExport(form);
    openPane("compare");
  }

  function readForm(form) {
    var data = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name) return;
      if (el.type === "checkbox") data[el.name] = el.checked;
      else data[el.name] = el.value;
    });
    data.timezone = data.timezone || "UTC";
    data.start_local = data.start_utc || "";
    try {
      data.start_dt = wallToUtc(data.start_local, data.timezone);
      data.start_utc = formatWallUtc(data.start_dt);
    } catch (err) {
      data.start_dt = null;
    }
    return data;
  }

  function fillForm(form, values) {
    Object.keys(values || {}).forEach(function (key) {
      var el = form.elements[key];
      if (el == null) return;
      if (el.type === "checkbox") {
        el.checked = Boolean(values[key]) && values[key] !== "0" && values[key] !== "";
        return;
      }
      el.value = values[key];
    });
    if (values && values.start_local && form.elements.start_utc) {
      form.elements.start_utc.value = values.start_local;
    }
    if ((!values || !values.timezone) && form.elements.timezone) {
      form.elements.timezone.value = "UTC";
    }
    updateTzPreview(form);
  }

  function updateTzPreview(form) {
    var el = document.getElementById("tz-preview");
    if (!el || !form) return;
    var wall = form.elements.start_utc && form.elements.start_utc.value;
    var tz = (form.elements.timezone && form.elements.timezone.value) || "UTC";
    try {
      el.textContent = "В расчёт уходит " + formatWallUtc(wallToUtc(wall, tz)) + " UTC";
    } catch (err) {
      el.textContent = "";
    }
  }

  function bindTimezone(form) {
    var input = form.elements.start_utc;
    var sel = form.elements.timezone;
    function onChange() {
      updateTzPreview(form);
    }
    if (input) input.addEventListener("input", onChange);
    if (sel) {
      sel.addEventListener("change", function () {
        updateTzPreview(form);
        lastProbedStart = "";
        checkStartDanger(form);
      });
    }
    updateTzPreview(form);
  }

  function loadUserScenarios() {
    try {
      userScenarios = JSON.parse(localStorage.getItem(SCENARIO_STORE) || "[]");
      if (!Array.isArray(userScenarios)) userScenarios = [];
    } catch (err) {
      userScenarios = [];
    }
    return userScenarios;
  }

  function persistUserScenarios() {
    try {
      localStorage.setItem(SCENARIO_STORE, JSON.stringify(userScenarios));
    } catch (err) {}
  }

  function scenarioSignature(form) {
    return [
      form.mode || "",
      form.start_utc || "",
      form.duration_hours || "",
      form.interval_days || "",
      form.search_hours || "",
      form.cutoff_utc || "",
      form.timezone || "UTC"
    ].join("|");
  }

  function scenarioTitle(entry) {
    var form = entry.form || {};
    var mode = form.mode === "current" ? "Текущая" : "История";
    return mode + " · " + (form.start_local || form.start_utc || "—") + " " + (form.timezone || "UTC");
  }

  function rememberScenario(fields, windows, comparison) {
    if (!windows || !windows.length) return;
    var entry = {
      id: "S" + Date.now(),
      at: new Date().toISOString(),
      form: {
        mode: fields.mode || "historical",
        start_utc: fields.start_utc || "",
        start_local: fields.start_local || fields.start_utc || "",
        timezone: fields.timezone || "UTC",
        duration_hours: Number(fields.duration_hours || 6),
        interval_days: Number(fields.interval_days || 1),
        search_hours: Number(fields.search_hours || 12),
        cutoff_utc: fields.cutoff_utc || "",
        refresh: Boolean(fields.refresh),
        freeze: Boolean(fields.freeze)
      },
      preferred: comparison && comparison.preferred || "",
      decision: comparison && comparison.decision || "",
      reason: comparison && comparison.reason || "",
      windows: windows.map(serializeWindow)
    };
    var sig = scenarioSignature(entry.form);
    userScenarios = loadUserScenarios().filter(function (item) {
      return scenarioSignature(item.form || {}) !== sig;
    });
    userScenarios.unshift(entry);
    if (userScenarios.length > 40) userScenarios = userScenarios.slice(0, 40);
    persistUserScenarios();
    renderUserScenarios();
  }

  function hydrateSerialized(row, id) {
    var start = new Date(row.start);
    var end = new Date(row.end);
    var sepLevel = row.sep || "unknown";
    var mmodLevel = row.mmod || "unknown";
    var geoLevel = row.geomagnetic || "unknown";
    return {
      id: id,
      start: start,
      end: end,
      sepLevel: sepLevel,
      mmodLevel: mmodLevel,
      geoLevel: geoLevel,
      sep: (row.factors && row.factors.radiation_sep) || {},
      geo: (row.factors && row.factors.geomagnetic_activity) || {},
      mmod: (row.factors && row.factors.mmod_meteoroid) || {},
      cover: row.critical_missing ? 0 : 1,
      tag: row.coverage_tag || "archive",
      labels: ["архив"],
      adverse: Number(row.adverse_minutes || 0),
      completeness: row.completeness,
      critical: Boolean(row.critical_missing),
      requested: false,
      preferred: false,
      worst: Math.max(rank(sepLevel), rank(mmodLevel), 0),
      archive: true,
      reason: row.reason || "",
      donkiCount: row.donki || 0,
      cmeCount: row.cme || 0
    };
  }

  function mergeUserHistory(windows, fields) {
    var duration = Number(fields.duration_hours || 6);
    var seen = {};
    (windows || []).forEach(function (w) {
      if (w.start) seen[isoOf(w.start)] = true;
    });
    var extra = [];
    loadUserScenarios().forEach(function (item) {
      if (Number((item.form || {}).duration_hours) !== duration) return;
      (item.windows || []).forEach(function (row, idx) {
        var key = row.start;
        if (!key || seen[key]) return;
        seen[key] = true;
        extra.push(hydrateSerialized(row, "A-" + item.id + "-" + (row.id || idx)));
      });
    });
    extra.sort(function (a, b) { return a.start - b.start; });
    return (windows || []).concat(extra);
  }

  function renderUserScenarios() {
    var root = document.getElementById("user-scenarios");
    if (!root) return;
    loadUserScenarios();
    if (!userScenarios.length) {
      root.innerHTML = "<p class=\"small\">Пока нет своих расчётов. Они появятся после «Рассчитать окна» или выбора демо.</p>";
      return;
    }
    root.innerHTML = "<div class=\"scenario-list\">" + userScenarios.map(function (item) {
      var form = item.form || {};
      var meta = Number(form.duration_hours || 6) + " ч · " +
        Number(form.interval_days || 1) + " сут · сдвиг " + Number(form.search_hours || 12) + " ч";
      if (item.preferred) meta += " · предпочтительно " + windowLabel(item.preferred);
      meta += " · окон " + (item.windows || []).length;
      return "<article class=\"scenario-card\" data-id=\"" + esc(item.id) + "\">" +
        "<header><strong>" + esc(scenarioTitle(item)) + "</strong>" +
        "<span class=\"num\">" + esc((item.at || "").replace("T", " ").replace(".000Z", " UTC")) + "</span></header>" +
        "<p class=\"small\">" + esc(meta) + "</p>" +
        "<div class=\"actions\"><button type=\"button\" class=\"btn ghost no-select js-apply-scenario\" data-id=\"" +
        esc(item.id) + "\">Открыть</button></div></article>";
    }).join("") + "</div>";
  }

  function applyScenario(id, form) {
    var entry = null;
    loadUserScenarios().forEach(function (item) {
      if (item.id === id) entry = item;
    });
    if (!entry || !form) return;
    fillForm(form, entry.form);
    var cards = document.querySelectorAll(".scenario-card");
    Array.prototype.forEach.call(cards, function (card) {
      card.classList.toggle("is-selected", card.getAttribute("data-id") === id);
    });
    run(form);
  }

  function scenariosCsv() {
    var cols = ["id", "at", "mode", "start_local", "timezone", "start_utc", "duration_hours", "interval_days", "search_hours", "cutoff_utc", "preferred", "decision", "windows"];
    var lines = [cols.join(",")];
    loadUserScenarios().forEach(function (item) {
      var form = item.form || {};
      var row = {
        id: item.id,
        at: item.at,
        mode: form.mode,
        start_local: form.start_local,
        timezone: form.timezone,
        start_utc: form.start_utc,
        duration_hours: form.duration_hours,
        interval_days: form.interval_days,
        search_hours: form.search_hours,
        cutoff_utc: form.cutoff_utc,
        preferred: item.preferred,
        decision: item.decision,
        windows: (item.windows || []).length
      };
      lines.push(cols.map(function (key) { return csvCell(row[key]); }).join(","));
    });
    return lines.join("\n") + "\n";
  }

  function bindScenarioExport(form) {
    var jsonBtn = document.getElementById("export-scenarios-json");
    var csvBtn = document.getElementById("export-scenarios-csv");
    var zipBtn = document.getElementById("export-scenarios-zip");
    if (jsonBtn) {
      jsonBtn.onclick = function () {
        downloadBlob("vkd-scenarios.json", "application/json;charset=utf-8", JSON.stringify({
          generated_at: new Date().toISOString(),
          algorithm: algorithm(),
          count: loadUserScenarios().length,
          scenarios: userScenarios
        }, null, 2));
      };
    }
    if (csvBtn) {
      csvBtn.onclick = function () {
        downloadBlob("vkd-scenarios.csv", "text/csv;charset=utf-8", scenariosCsv());
      };
    }
    if (zipBtn) {
      zipBtn.onclick = function () {
        loadUserScenarios();
        downloadBlob("vkd-scenarios.zip", "application/zip", zipStore([
          { name: "scenarios.json", data: JSON.stringify({ generated_at: new Date().toISOString(), scenarios: userScenarios }, null, 2) },
          { name: "scenarios.csv", data: scenariosCsv() }
        ]));
      };
    }
    var root = document.getElementById("user-scenarios");
    if (root) {
      root.addEventListener("click", function (ev) {
        var btn = ev.target.closest(".js-apply-scenario");
        if (!btn) return;
        applyScenario(btn.getAttribute("data-id"), form);
      });
    }
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

  function presentWindows(windows, status, fields, meta, remember) {
    var merged = mergeUserHistory(windows, fields);
    if (remember) rememberScenario(fields, windows, compare(windows));
    render(merged, compare(merged), status, fields, meta);
  }

  function run(form) {
    var root = document.getElementById("compare-root");
    var banner = document.getElementById("live-error");
    if (banner) banner.textContent = "";
    openPane("compare");
    if (root) root.innerHTML = "<div class=\"banner\">Запрос данных…</div>";
    var fields = readForm(form);
    var start = fields.start_dt;
    try {
      if (!start) start = parseUtc(fields.start_local || fields.start_utc);
    } catch (err) {
      if (root) root.innerHTML = "<p class=\"small\">Нажмите «Рассчитать окна» в разделе «Запрос».</p>";
      if (banner) banner.textContent = err.message;
      openPane("request");
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
      presentWindows(windows, { sources: [], overall_status: "pending" }, fields, { archive: true, pack: pack, preview: true }, false);
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
        presentWindows(attachPackTimeline(windows, pack), status, fields, { pack: pack }, true);
        return null;
      }
      var filled = attachPackTimeline(mergeArchive(windows, pack), pack);
      presentWindows(filled, status, fields, { archive: Boolean(pack), pack: pack }, true);
    }).catch(function (err) {
      return (fallbackP || loadArchiveFallback(fields)).then(function (pack) {
        if (pack && pack.windows) {
          var windows = pack.windows.map(function (w, idx) { return fromPackWindow(w, idx, idx === 0); });
          presentWindows(windows, { sources: [], overall_status: "unavailable" }, fields, { archive: true, pack: pack }, true);
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

  function needsAlert(window) {
    return Boolean(window) && (isDangerous(window) || window.critical);
  }

  function alertTarget(windows) {
    var list = windows || [];
    var requested = null;
    list.forEach(function (w) {
      if (w.requested && !requested) requested = w;
    });
    if (needsAlert(requested)) return requested;
    var worst = null;
    var worstScore = -1;
    list.forEach(function (w) {
      if (!isDangerous(w)) return;
      var score = rank(w.sepLevel) + rank(w.mmodLevel) + rank(w.geoLevel);
      if (score > worstScore) {
        worst = w;
        worstScore = score;
      }
    });
    return worst || (requested && requested.critical ? requested : null);
  }

  function levelWord(level) {
    return LEVEL_WORD[level] || level || "нет данных";
  }

  function factorLine(window) {
    var parts = [];
    if (rank(window.sepLevel) >= 2) parts.push("радиация — " + levelWord(window.sepLevel));
    if (rank(window.mmodLevel) >= 2) parts.push("обломки — " + levelWord(window.mmodLevel));
    if (rank(window.geoLevel) >= 2) {
      parts.push("геомагнетизм — " + levelWord(window.geoLevel) + " (считается отдельно от радиации)");
    }
    return parts;
  }

  function alertKey(window) {
    if (!window) return "";
    return [isoOf(window.start), window.sepLevel, window.mmodLevel, window.geoLevel, window.critical ? "hole" : "ok"].join("|");
  }

  function buildAlert(window) {
    var when = window && window.start ? formatWallUtc(window.start) + " UTC" : "выбранное время";
    var danger = isDangerous(window);
    var hole = Boolean(window && window.critical);
    var lines = [];
    var title = "Предупреждение";
    if (danger) {
      title = "Выход выглядит опасным";
      if (!window.requested) {
        lines.push("В выбранном интервале есть опасные сутки.");
      }
      lines.push("На время " + when + " выход выглядит опасным.");
      var parts = factorLine(window);
      if (parts.length) lines.push("Неблагоприятно: " + parts.join("; ") + ".");
      lines.push("Это не разрешение на выход. Сравните соседние дни или сдвиньте время.");
    }
    if (hole) {
      if (!danger) title = "Дыра в данных";
      lines.push("На эти сутки нет полных данных по радиации. Пустая оценка не значит, что безопасно.");
    }
    return { title: title, body: lines.join(" "), danger: danger, hole: hole };
  }

  function formatWhen(dt) {
    if (!dt) return "—";
    return formatWallUtc(dt) + " UTC";
  }

  function closeAlert() {
    var modal = document.getElementById("eva-alert");
    if (modal) modal.hidden = true;
  }

  function renderWarningLog() {
    var root = document.getElementById("warning-log");
    var count = document.getElementById("warning-count");
    if (count) {
      count.textContent = warningLog.length ? String(warningLog.length) : "0";
      count.hidden = warningLog.length === 0;
    }
    if (!root) return;
    if (!warningLog.length) {
      root.innerHTML = "<p class=\"small\">Пока нет всплывающих предупреждений. Они появятся после расчёта или смены начала ВКД, если выход выглядит опасным или в данных дыра.</p>";
      return;
    }
    root.innerHTML = "<ol class=\"warning-log\">" + warningLog.map(function (item) {
      var factors = "";
      if (item.sep) factors += "<span class=\"level " + esc(item.sep) + "\">Радиация: " + esc(levelWord(item.sep)) + "</span>";
      if (item.mmod) factors += "<span class=\"level " + esc(item.mmod) + "\">Обломки: " + esc(levelWord(item.mmod)) + "</span>";
      if (item.geo) factors += "<span class=\"level " + esc(item.geo) + "\">Геомагнетизм: " + esc(levelWord(item.geo)) + "</span>";
      return "<li class=\"warning-item\"><header><span class=\"kind\">" + esc(item.title) +
        "</span><span class=\"num\">" + esc(formatUtc(item.at)) + "</span></header><p>" +
        esc(item.body) + "</p>" +
        (factors ? "<div class=\"modal-factors\">" + factors + "</div>" : "") +
        "</li>";
    }).join("") + "</ol>";
  }

  function logWarning(item) {
    var at = item.at || new Date();
    if (at instanceof Date) at.setMilliseconds(0);
    warningLog.unshift({
      at: at,
      title: item.title || "Предупреждение",
      body: item.body || "",
      sep: item.sep || "",
      mmod: item.mmod || "",
      geo: item.geo || ""
    });
    renderWarningLog();
  }

  function showDangerAlert(window) {
    var modal = document.getElementById("eva-alert");
    var titleEl = document.getElementById("eva-alert-title");
    var body = document.getElementById("eva-alert-body");
    var factors = document.getElementById("eva-alert-factors");
    if (!modal || !body || !factors) return;
    var alert = buildAlert(window);
    if (titleEl) titleEl.textContent = alert.title;
    body.textContent = alert.body;
    factors.innerHTML =
      "<span class=\"level " + esc(window.sepLevel) + "\">Радиация: " + esc(levelWord(window.sepLevel)) + "</span>" +
      "<span class=\"level " + esc(window.mmodLevel) + "\">Обломки: " + esc(levelWord(window.mmodLevel)) + "</span>" +
      "<span class=\"level " + esc(window.geoLevel) + "\">Геомагнетизм: " + esc(levelWord(window.geoLevel)) + "</span>";
    logWarning({
      title: alert.title,
      body: alert.body,
      sep: window.sepLevel,
      mmod: window.mmodLevel,
      geo: window.geoLevel
    });
    lastAlertedKey = alertKey(window);
    modal.hidden = false;
    var closeBtn = document.getElementById("eva-alert-close");
    if (closeBtn) closeBtn.focus();
  }

  function maybeAlertWindow(window) {
    if (!needsAlert(window)) {
      closeAlert();
      return;
    }
    if (alertKey(window) === lastAlertedKey) return;
    showDangerAlert(window);
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
    var start = fields.start_dt;
    try {
      if (!start) start = parseUtc(fields.start_local || fields.start_utc);
    } catch (err) {
      return Promise.resolve();
    }
    var known = windowForStart(start);
    if (known) {
      lastAlertedKey = "";
      maybeAlertWindow(known);
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
      lastAlertedKey = "";
      maybeAlertWindow(window);
    });
  }

  function bindStartWatch(form) {
    var input = form.elements.start_utc;
    if (!input) return;
    lastProbedStart = (input.value || "").trim();
    function schedule(immediate) {
      var value = (input.value || "").trim();
      if (value === lastProbedStart) return;
      lastAlertedKey = "";
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
    if (!el || el.classList.contains("tile")) return;
    var nodes = document.querySelectorAll("button.is-selected:not(.tile), a.btn.is-selected");
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
      if (!btn || btn.id === "eva-alert-close" || btn.id === "export-journal" || btn.classList.contains("tile") || btn.classList.contains("no-select")) return;
      selectButton(btn);
    });
  }

  function boot() {
    bindTiles();
    bindAlert();
    bindButtonSelect();
    bindJournalExport();
    highlightCurrentDemo();
    var form = document.getElementById("eva-form");
    loadUserScenarios();
    renderUserScenarios();
    if (!form || !useLiveApi()) {
      if (form) {
        bindTimezone(form);
        bindScenarioExport(form);
      }
      return;
    }
    bindTimezone(form);
    bindScenarioExport(form);
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      run(form);
    });
    var demo = demoFromLocation();
    activeDemo = demo;
    if (DEMOS[demo]) fillForm(form, DEMOS[demo]);
    bindStartWatch(form);
    run(form);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
