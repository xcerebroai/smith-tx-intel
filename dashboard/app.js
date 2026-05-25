/* Smith County Distress Intelligence — operator lead board logic.
   Client-side only. Reads dashboard/data.json (or window.LEADS). Operator
   triage flags persist in localStorage; no backend.
   Daily-refresh-aware: surfaces NEW (recorded today) + last-30-days +
   years-delinquent (1/2/3/4/5+) filters atop the legacy v5 controls. */
(function () {
  "use strict";

  // ---------- small helpers ----------
  var $ = function (id) { return document.getElementById(id); };
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function money(v) {
    var n = Number(v);
    return (v == null || v === "" || isNaN(n)) ? "—"
      : "$" + n.toLocaleString("en-US");
  }
  var MONTHS = { jan:0,feb:1,mar:2,apr:3,may:4,jun:5,jul:6,aug:7,sep:8,oct:9,
    nov:10,dec:11 };
  function parseDate(s) {
    if (!s) return null;
    s = String(s).trim();
    var m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (m) return new Date(+m[3], +m[1] - 1, +m[2]);
    m = s.match(/^([A-Za-z]{3,})\.?\s+(\d{1,2}),?\s+(\d{4})$/);
    if (m) {
      var mi = MONTHS[m[1].toLowerCase().slice(0, 3)];
      if (mi != null) return new Date(+m[3], mi, +m[2]);
    }
    m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (m) return new Date(+m[1], +m[2] - 1, +m[3]);
    var d = new Date(s);
    return isNaN(d.getTime()) ? null : d;
  }
  var TODAY = (function () {
    var d = new Date(); d.setHours(0, 0, 0, 0); return d;
  })();
  function daysFromToday(d) {
    return d ? Math.round((d - TODAY) / 86400000) : null;
  }

  // ---------- state ----------
  var DATA = (typeof window !== "undefined" && window.LEADS) || null;
  var records = [];
  // yearsRange — 6 buckets keyed by years_back: 0 (not delinquent), 1, 2, 3,
  // 4, 5 (5-or-more). Default: 3/4/5 + non-delinquent ON; 1/2 OFF so the
  // default view hides the "just late" noise (operator framework decision —
  // 1-year-late is not strong distress).
  var state = {
    search: "", saleWindow: "any", valMin: null, valMax: null,
    signals: {}, owners: {}, absentee: false, oos: false, review: false,
    multiOnly: false, stackedOnly: false, estateOnly: false,
    newOnly: false, last30Only: false,
    yearsRange: { 0: true, 1: false, 2: false, 3: true, 4: true, 5: true },
    qualFilter: null,             // optional qualification_class filter
    // TAX_DEFAULT_LOW_PRIORITY (1yr + <$100) is operator noise; default-hide
    // it independently of the years filter so toggling year=1 ON for the
    // 8,957 legitimate 1-yr QUALIFIED leads doesn't pull the noise in.
    includeLowPriority: false,
    // Default sort: "recent" — newest recorded distress events first. This
    // gives a neutral all-records open view (FC-sweep / lis-pendens / etc.
    // recorded in the last weeks lead), rather than pinning the 949
    // estate-titled rows to the top via the urgency tier as before.
    sort: "recent", shown: 0, preset: "all"
  };
  var PAGE = 60;
  var marked = loadMarked();   // Set of lead_id (localStorage)
  var skipped = {};            // session-only hide
  var filtered = [];
  var io = null;
  var sentinel = null;   // persistent JS node — never lives in index.html

  function loadMarked() {
    try {
      var raw = localStorage.getItem("elp_marked_v5");
      var arr = raw ? JSON.parse(raw) : [];
      var s = {}; arr.forEach(function (x) { s[x] = true; });
      return s;
    } catch (e) { return {}; }
  }
  function saveMarked() {
    try {
      localStorage.setItem("elp_marked_v5",
        JSON.stringify(Object.keys(marked)));
    } catch (e) { /* storage unavailable — non-fatal */ }
  }

  // ---------- preprocessing ----------
  function fclSignal(r) {
    var s = (r.signals || []).filter(function (x) {
      return x.signal_type === "foreclosure_notice";
    });
    return s.length ? s[0] : null;
  }
  function prep(r) {
    r.signal_types = r.signal_types || [];
    r.signals = r.signals || [];
    var fs = fclSignal(r);
    r._fcl = fs;
    r._isFcl = !!fs;
    var sd = fs ? parseDate(fs.sale_date) : null;
    r._saleDate = sd;
    r._days = daysFromToday(sd);
    r._assessed = Number(r.assessed_value) || 0;
    r._review = r.parcel_resolution_status === "REVIEW_REQUIRED";
    r._filed = parseDate(r.latest_event_date);
    // years_back bucket (0/1/2/3/4/5 — 5 catches 5-or-more)
    var yb = Number(r.tax_delinquent_years_back) || 0;
    r._yrsBucket = yb >= 5 ? 5 : yb;
    r._taxHot = !!r.tax_delinquent_hot;
    r._stacked = !!r.stacked_lead;
    r._estate = !!r.estate_titled || r.owner_type === "ESTATE";
    r._isNew = !!r.is_new;
    r._isL30 = !!r.is_last_30_days;
    // Sale-window — forward-looking, distinct from is_last_30_days
    // (which is backward-looking on the RECORDED date). Past sales
    // never trigger the upcoming-sale badge.
    r._isUpcomingSale30 = !!r.is_upcoming_sale_30d;
    r._saleStatus = r.sale_status || null;   // past | today | upcoming_30d | upcoming_later
    r._tier = urgencyTier(r);
    var taxd = r.signal_types.indexOf("state_tax_lien") >= 0 ||
      r.signal_types.indexOf("federal_tax_lien") >= 0 ||
      r.signal_types.indexOf("tax_default") >= 0 ||
      r.signal_types.indexOf("tax_default_low_priority") >= 0 ||
      r.signal_types.indexOf("tax_delinquent") >= 0;  // legacy
    r._taxDelinquent = taxd;
    r._qualClass = r.qualification_class || "";
    r._blob = [r.owner_name, r.property_full_address, r.mailing_full_address,
      r.legal_description, r.filer_entity, r.parcel_id,
      (r.signals || []).map(function (s) {
        return (s.instrument_numbers || []).join(" ");
      }).join(" ")].join(" ").toLowerCase();
  }
  function urgencyTier(r) {
    var d = r._days;
    // Foreclosure-sale-imminent only — these are the genuinely urgent rows
    // (sale within 21/60 days). Estate-titled has been DEMOTED out of the
    // urgency tiers: the operator's lead board must open on ALL records
    // neutrally sorted, not with 949 probate rows pinned to the top. The
    // operator filters TO estate-titled via the dedicated control.
    if (r._isFcl && d != null && d >= 0 && d <= 21) return 1;
    if (r._isFcl && d != null && d > 21 && d <= 60) return 2;
    // tier 3: stacked / multi-signal — strongest combined-evidence class.
    if (r._stacked || (r.signal_count || 0) >= 2) return 3;
    // tier 4: hot tax-delinquent (3+ unpaid years).
    if (r._taxHot) return 4;
    return 5;
  }

  // ---------- boot ----------
  function boot(payload) {
    records = (payload && payload.records) || [];
    records.forEach(prep);

    $("topStats").innerHTML = topStatsHtml(payload);
    // Build-status banner intentionally suppressed — operator does not want
    // PARTIAL_BUILD / SOURCE_LIMITED messaging on the operator board.
    var b = $("banner"); if (b) b.hidden = true;

    buildPresets();
    buildSignalFilter();
    buildOwnerFilter();
    populateYearsCounts();
    wireControls();
    setupObserver();
    render();
    document.documentElement.setAttribute("data-ready", "1");
  }

  function topStatsHtml(p) {
    // Default-view universe = everything EXCEPT TAX_DEFAULT_LOW_PRIORITY.
    // That bucket is operator noise (1yr + <$100) — surfaced only when the
    // "Show low-priority" toggle flips on.
    var defaultViewCount = records.filter(function (r) {
      return r._qualClass !== "TAX_DEFAULT_LOW_PRIORITY";
    }).length;
    var lpCount  = records.length - defaultViewCount;
    var nNew    = records.filter(function (r) { return r._isNew; }).length;
    var nL30    = records.filter(function (r) { return r._isL30; }).length;
    var nStack  = records.filter(function (r) { return r._stacked; }).length;
    var nEstate = records.filter(function (r) { return r._estate; }).length;
    var nHot    = records.filter(function (r) {
      return r._taxHot && r._qualClass !== "TAX_DEFAULT_LOW_PRIORITY";
    }).length;
    function st(n, l, cls) {
      return '<div class="topstat ' + (cls || "") + '"><div class="n">' +
        n.toLocaleString() + '</div><div class="l">' + l + "</div></div>";
    }
    var lpStat = lpCount ? st(lpCount, "low-priority (hidden)") : "";
    return st(defaultViewCount, "leads") +
      st(nNew,    "NEW today",         "urgent") +
      st(nL30,    "last 30 days") +
      st(nStack,  "stacked",           "estate") +
      st(nEstate, "estate-titled",     "estate") +
      st(nHot,    "tax delinq 3+yr",   "urgent") +
      lpStat;
  }
  function populateYearsCounts() {
    var c = {0:0,1:0,2:0,3:0,4:0,5:0};
    records.forEach(function (r) { c[r._yrsBucket]++; });
    for (var k in c) { var el = $("yc" + k); if (el) el.textContent = c[k].toLocaleString(); }
    var lp = records.filter(function (r) {
      return r._qualClass === "TAX_DEFAULT_LOW_PRIORITY";
    }).length;
    var lpEl = $("lpCount"); if (lpEl) lpEl.textContent = lp.toLocaleString();
  }

  // ---------- sidebar ----------
  var PRESETS = [
    { id: "new",     label: "NEW today" },
    { id: "last30",  label: "Last 30 days" },
    { id: "fcl21",   label: "Foreclosures — next 21 days" },
    { id: "taxsale", label: "Tax sale leads (active sale date)" },
    { id: "taxfcl",  label: "Tax foreclosure leads" },
    { id: "estates", label: "Estate-titled (probate)" },
    { id: "stacked", label: "Stacked leads (multi-signal)" },
    { id: "tax5",    label: "Tax default 5+ years" },
    { id: "tax3",    label: "Tax default 3+ years" },
    { id: "oos",     label: "Out-of-state absentees" },
    { id: "all",     label: "Show all" }
  ];
  function buildPresets() {
    var box = $("presets");
    PRESETS.forEach(function (p) {
      var b = document.createElement("button");
      b.className = "preset"; b.textContent = p.label; b.dataset.id = p.id;
      b.addEventListener("click", function () { applyPreset(p.id); });
      box.appendChild(b);
    });
  }
  function markPresetActive(id) {
    state.preset = id;
    Array.prototype.forEach.call($("presets").children, function (b) {
      b.classList.toggle("active", b.dataset.id === id);
    });
  }

  function buildSignalFilter() {
    var counts = {}, labels = {};
    records.forEach(function (r) {
      (r.signals || []).forEach(function (s) {
        counts[s.signal_type] = (counts[s.signal_type] || 0) + 1;
        labels[s.signal_type] = s.signal_label || s.signal_type;
      });
    });
    var box = $("signalFilter");
    Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; })
      .forEach(function (t) {
        state.signals[t] = true;
        var l = document.createElement("label");
        l.className = "chk";
        l.innerHTML = '<input type="checkbox" checked data-sig="' + esc(t) +
          '"> ' + esc(labels[t]) + '<span class="cnt">' + counts[t] + "</span>";
        l.querySelector("input").addEventListener("change", function (e) {
          state.signals[t] = e.target.checked; markPresetActive("");
          render();
        });
        box.appendChild(l);
      });
  }
  function buildOwnerFilter() {
    var counts = {};
    records.forEach(function (r) {
      var o = r.owner_type || "UNKNOWN";
      counts[o] = (counts[o] || 0) + 1;
    });
    var box = $("ownerFilter");
    Object.keys(counts).sort().forEach(function (o) {
      state.owners[o] = true;
      var l = document.createElement("label");
      l.className = "chk";
      l.innerHTML = '<input type="checkbox" checked data-own="' + esc(o) +
        '"> ' + esc(o) + '<span class="cnt">' + counts[o] + "</span>";
      l.querySelector("input").addEventListener("change", function (e) {
        state.owners[o] = e.target.checked; markPresetActive(""); render();
      });
      box.appendChild(l);
    });
  }

  function wireControls() {
    var deb;
    $("search").addEventListener("input", function (e) {
      clearTimeout(deb);
      deb = setTimeout(function () {
        state.search = e.target.value.trim().toLowerCase(); render();
      }, 300);
    });
    $("saleWindow").addEventListener("change", function (e) {
      state.saleWindow = e.target.value; markPresetActive(""); render();
    });
    $("valMin").addEventListener("input", function (e) {
      state.valMin = e.target.value === "" ? null : Number(e.target.value);
      markPresetActive(""); render();
    });
    $("valMax").addEventListener("input", function (e) {
      state.valMax = e.target.value === "" ? null : Number(e.target.value);
      markPresetActive(""); render();
    });
    $("togAbsentee").addEventListener("change", function (e) {
      state.absentee = e.target.checked; markPresetActive(""); render();
    });
    $("togOos").addEventListener("change", function (e) {
      state.oos = e.target.checked; markPresetActive(""); render();
    });
    $("togReview").addEventListener("change", function (e) {
      state.review = e.target.checked; markPresetActive(""); render();
    });
    // New filter wires — added for daily-refresh feature set.
    var togStacked = $("togStacked");
    if (togStacked) togStacked.addEventListener("change", function (e) {
      state.stackedOnly = e.target.checked; markPresetActive(""); render();
    });
    var togEstate = $("togEstate");
    if (togEstate) togEstate.addEventListener("change", function (e) {
      state.estateOnly = e.target.checked; markPresetActive(""); render();
    });
    var togNew = $("togNew");
    if (togNew) togNew.addEventListener("change", function (e) {
      state.newOnly = e.target.checked; markPresetActive(""); render();
    });
    var togL30 = $("togL30");
    if (togL30) togL30.addEventListener("change", function (e) {
      state.last30Only = e.target.checked; markPresetActive(""); render();
    });
    var togLp = $("togLowPri");
    if (togLp) togLp.addEventListener("change", function (e) {
      state.includeLowPriority = e.target.checked;
      markPresetActive(""); render();
    });
    var yf = $("yearsFilter");
    if (yf) {
      yf.querySelectorAll('input[type=checkbox][data-yrs]').forEach(function (cb) {
        var key = Number(cb.dataset.yrs);
        cb.checked = !!state.yearsRange[key];
        cb.addEventListener("change", function (e) {
          state.yearsRange[key] = e.target.checked;
          markPresetActive(""); render();
        });
      });
    }
    $("sortMode").addEventListener("change", function (e) {
      state.sort = e.target.value; render();
    });
    $("resetBtn").addEventListener("click", function () { applyPreset("all"); });
    $("exportFiltered").addEventListener("click", function () {
      exportCsv(filtered, "el_paso_leads_filtered.csv");
    });
    $("exportMarked").addEventListener("click", function () {
      var rows = records.filter(function (r) { return marked[r.lead_id]; });
      if (!rows.length) { alert("No leads marked for review yet."); return; }
      exportCsv(rows, "el_paso_leads_marked.csv");
    });
  }

  function applyPreset(id) {
    // reset everything to defaults first
    state.search = ""; $("search").value = "";
    state.saleWindow = "any"; $("saleWindow").value = "any";
    state.valMin = null; state.valMax = null;
    $("valMin").value = ""; $("valMax").value = "";
    state.absentee = false; $("togAbsentee").checked = false;
    state.oos = false; $("togOos").checked = false;
    state.review = false; $("togReview").checked = false;
    state.multiOnly = false;
    state.stackedOnly = false; if ($("togStacked")) $("togStacked").checked = false;
    state.estateOnly  = false; if ($("togEstate"))  $("togEstate").checked  = false;
    state.newOnly     = false; if ($("togNew"))     $("togNew").checked     = false;
    state.last30Only  = false; if ($("togL30"))     $("togL30").checked     = false;
    state.includeLowPriority = false;
    if ($("togLowPri")) $("togLowPri").checked = false;
    // years filter — default (operator framework decision): 3/4/5 + non-
    // delinquent ON; 1/2 OFF.
    var defaults = { 0: true, 1: false, 2: false, 3: true, 4: true, 5: true };
    Object.keys(defaults).forEach(function (k) { state.yearsRange[k] = defaults[k]; });
    syncYearsCheckboxes();
    setAllChecks("signalFilter", "sig", state.signals, true);
    setAllChecks("ownerFilter", "own", state.owners, true);

    if (id === "fcl21") {
      state.saleWindow = "21"; $("saleWindow").value = "21";
      onlyChecks("signalFilter", "sig", state.signals, ["foreclosure_notice"]);
    } else if (id === "estates") {
      state.estateOnly = true; if ($("togEstate")) $("togEstate").checked = true;
    } else if (id === "oos") {
      state.absentee = true; $("togAbsentee").checked = true;
      state.oos = true; $("togOos").checked = true;
    } else if (id === "stacked") {
      state.stackedOnly = true; if ($("togStacked")) $("togStacked").checked = true;
    } else if (id === "new") {
      state.newOnly = true; if ($("togNew")) $("togNew").checked = true;
    } else if (id === "last30") {
      state.last30Only = true; if ($("togL30")) $("togL30").checked = true;
    } else if (id === "tax5") {
      state.yearsRange = { 0: false, 1: false, 2: false, 3: false, 4: false, 5: true };
      syncYearsCheckboxes();
    } else if (id === "tax3") {
      state.yearsRange = { 0: false, 1: false, 2: false, 3: true, 4: true, 5: true };
      syncYearsCheckboxes();
    } else if (id === "taxsale") {
      onlyChecks("signalFilter", "sig", state.signals,
        ["tax_foreclosure_notice"]);
      state.qualFilter = "TAX_SALE_LEAD";
    } else if (id === "taxfcl") {
      onlyChecks("signalFilter", "sig", state.signals,
        ["tax_foreclosure_notice"]);
      state.qualFilter = "TAX_FORECLOSURE_LEAD";
    }
    if (id !== "taxsale" && id !== "taxfcl") state.qualFilter = null;
    markPresetActive(id);
    render();
  }
  function syncYearsCheckboxes() {
    var yf = $("yearsFilter"); if (!yf) return;
    yf.querySelectorAll('input[type=checkbox][data-yrs]').forEach(function (cb) {
      cb.checked = !!state.yearsRange[Number(cb.dataset.yrs)];
    });
  }
  function setAllChecks(boxId, attr, store, on) {
    $(boxId).querySelectorAll("input[type=checkbox]").forEach(function (c) {
      c.checked = on; store[c.dataset[attr]] = on;
    });
  }
  function onlyChecks(boxId, attr, store, keep) {
    $(boxId).querySelectorAll("input[type=checkbox]").forEach(function (c) {
      var on = keep.indexOf(c.dataset[attr]) >= 0;
      c.checked = on; store[c.dataset[attr]] = on;
    });
  }

  // ---------- filtering + sorting ----------
  function applyFilters() {
    var sigKeys = Object.keys(state.signals);
    var allSig = sigKeys.every(function (k) { return state.signals[k]; });
    var ownKeys = Object.keys(state.owners);
    var allOwn = ownKeys.every(function (k) { return state.owners[k]; });
    var win = state.saleWindow === "any" ? null : Number(state.saleWindow);

    return records.filter(function (r) {
      if (skipped[r.lead_id]) return false;
      if (state.review && !r._review) return false;
      if (state.stackedOnly && !r._stacked) return false;
      if (state.estateOnly && !r._estate) return false;
      if (state.newOnly && !r._isNew) return false;
      if (state.last30Only && !r._isL30) return false;
      if (state.yearsRange && state.yearsRange[r._yrsBucket] === false)
        return false;
      if (!state.includeLowPriority
          && r._qualClass === "TAX_DEFAULT_LOW_PRIORITY") return false;
      if (state.qualFilter && r._qualClass !== state.qualFilter) return false;
      if (!allSig) {
        var hit = (r.signal_types || []).some(function (t) {
          return state.signals[t];
        });
        if (!hit) return false;
      }
      if (!allOwn && !state.owners[r.owner_type || "UNKNOWN"]) return false;
      if (state.absentee && !r.absentee_owner_flag) return false;
      if (state.oos && !r.out_of_state_owner_flag) return false;
      if (state.multiOnly && (r.signal_count || 0) < 2) return false;
      if (win != null) {
        if (!r._isFcl || r._days == null || r._days < 0 || r._days > win)
          return false;
      }
      if (state.valMin != null && r._assessed < state.valMin) return false;
      if (state.valMax != null &&
        (r._assessed > state.valMax || r._assessed === 0)) return false;
      if (state.search && r._blob.indexOf(state.search) < 0) return false;
      return true;
    });
  }
  function sortRows(rows) {
    var c = rows.slice();
    var by = state.sort;
    c.sort(function (a, b) {
      if (by === "sale") {
        var av = a._saleDate ? a._saleDate.getTime() : 8e15;
        var bv = b._saleDate ? b._saleDate.getTime() : 8e15;
        return av - bv;
      }
      if (by === "value") return b._assessed - a._assessed;
      if (by === "recent") {
        // Only PRIMARY-event recorded dates count for recency. Synth
        // (estate / tax_default) rows carry the SFTP drop date as their
        // latest_event_date — that's a scrape artifact, not a county
        // recording date. Treat synth as undated so primary leads
        // dominate the top of the default view; synth fills the body
        // distributed by parcel_id (lexicographic tiebreak, neutral
        // across estate / tax-default / etc — no class is pinned).
        var ap = a.provenance === "primary_event";
        var bp = b.provenance === "primary_event";
        var af = (ap && a._filed) ? a._filed.getTime() : 0;
        var bf = (bp && b._filed) ? b._filed.getTime() : 0;
        if (af !== bf) return bf - af;
        // tied (typically: both synth) → stable parcel_id alpha — distributes
        // estate rows across the synth body rather than bunching them.
        return (a.parcel_id || "") < (b.parcel_id || "") ? -1 : 1;
      }
      if (by === "signals")
        return (b.signal_count || 0) - (a.signal_count || 0);
      // urgency (default): tier asc, then within-tier secondary
      if (a._tier !== b._tier) return a._tier - b._tier;
      if (a._tier <= 2) {            // foreclosure tiers: soonest sale first
        var as = a._saleDate ? a._saleDate.getTime() : 8e15;
        var bs = b._saleDate ? b._saleDate.getTime() : 8e15;
        return as - bs;
      }
      if ((b.signal_count || 0) !== (a.signal_count || 0))
        return (b.signal_count || 0) - (a.signal_count || 0);
      return b._assessed - a._assessed;
    });
    return c;
  }

  // ---------- rendering (UI-7 incremental window) ----------
  function setupObserver() {
    sentinel = document.createElement("div");
    sentinel.className = "sentinel";
    io = new IntersectionObserver(function (entries) {
      if (entries[0].isIntersecting) renderMore();
    }, { root: $("leadList"), rootMargin: "300px" });
  }
  function render() {
    filtered = sortRows(applyFilters());
    state.shown = 0;
    var list = $("leadList");
    io.unobserve(sentinel);
    list.innerHTML = "";               // detaches sentinel — JS ref survives
    // Denominator reflects the EFFECTIVE universe (low-priority excluded
    // unless the operator toggled it on). Total kept visible for context.
    var lpHidden = records.filter(function (r) {
      return r._qualClass === "TAX_DEFAULT_LOW_PRIORITY";
    }).length;
    var universeN = state.includeLowPriority
      ? records.length : records.length - lpHidden;
    var rcLine = filtered.length.toLocaleString() +
      " of " + universeN.toLocaleString() + " leads";
    if (!state.includeLowPriority && lpHidden)
      rcLine += "  (" + lpHidden.toLocaleString() +
        " low-priority hidden — toggle in sidebar)";
    $("rowCount").textContent = rcLine;
    $("markedCount").textContent = Object.keys(marked).length;
    updateFilterSummary();

    var empty = $("emptyMsg");
    if (!filtered.length) {
      empty.hidden = false;
      empty.innerHTML = "<b>No leads match the current filters.</b>" +
        "Try widening the foreclosure sale window, clearing the assessed-" +
        "value range, or re-checking signal/owner types — or hit " +
        "<em>Show all</em>.";
      return;
    }
    empty.hidden = true;
    renderMore();
  }
  function renderMore() {
    var list = $("leadList");
    var end = Math.min(state.shown + PAGE, filtered.length);
    var frag = document.createDocumentFragment();
    for (var i = state.shown; i < end; i++) frag.appendChild(rowEl(filtered[i]));
    list.appendChild(frag);
    list.appendChild(sentinel);        // keep sentinel last
    state.shown = end;
    if (state.shown < filtered.length) io.observe(sentinel);
    else io.unobserve(sentinel);
  }

  function chipHtml(r) {
    return (r.signals || []).map(function (s) {
      var n = s.count || 1;
      var cb = n > 1 ? '<span class="cb">' + n + "</span>" : "";
      var cls = "chip", label = esc(s.signal_label || s.signal_type);
      if (s.signal_type === "foreclosure_notice") {
        cls += " fcl";
        var d = r._days;
        if (d != null && d >= 0 && d <= 21) cls += " soon";
        if (s.sale_date) {
          label = "Foreclosure — Sale " + esc(s.sale_date);
          if (d != null) label += d < 0 ? " (past)"
            : d === 0 ? " (today)" : " (in " + d + "d)";
        }
      } else if (s.signal_type === "estate_titled_property" ||
        s.signal_type === "trust_titled_property") {
        cls += " estate";
      } else if (s.signal_type === "state_tax_lien" ||
        s.signal_type === "federal_tax_lien") {
        cls += " tax";
      }
      return '<span class="' + cls + '">' + label + cb + "</span>";
    }).join("");
  }
  function rowEl(r) {
    var el = document.createElement("div");
    el.className = "lead u-" + r._tier +
      (r._review ? " review" : "") + (marked[r.lead_id] ? " marked" : "");
    el.dataset.id = r.lead_id;

    var addr;
    if (r.property_full_address)
      addr = '<div class="addr">' + esc(r.property_full_address) + "</div>";
    else if (r.legal_description)
      addr = '<div class="addr legal">Legal: ' +
        esc(r.legal_description) + "</div>";
    else if ((r.signal_types || []).indexOf("foreclosure_notice") >= 0) {
      // Foreclosure-specific REVIEW_REQUIRED card line — show doc# +
      // sale-date prominently so the operator has an actionable hook
      // even when the publicsearch FC listing doesn't expose the owner.
      var fs2 = (r.signals || []).filter(function (x) {
        return x.signal_type === "foreclosure_notice";
      })[0] || {};
      var instr = (fs2.instrument_numbers || [])[0] ||
                  (r.lead_id || "").replace(/^lead_unresolved_/, "");
      var saleTxt = fs2.sale_date ? "  ·  Sale " + esc(fs2.sale_date) +
        (r._saleStatus === "past" ? " (past)" :
          r._saleStatus === "today" ? " (today)" :
          r._saleStatus === "upcoming_30d" ? " (upcoming)" : "") : "";
      addr = '<div class="addr none">Doc #' + esc(instr) + saleTxt +
        '  ·  Owner not on filing — clerk doc image required</div>';
    } else
      addr = '<div class="addr none">No property address — skip-trace ' +
        'from owner + instrument</div>';

    var mail = (r.mailing_full_address &&
      r.mailing_full_address !== r.property_full_address)
      ? '<div class="mail">Mailing: ' + esc(r.mailing_full_address) +
        "</div>" : "";
    var filer = r._review && r.filer_entity
      ? '<div class="filer-note">Filed by: ' + esc(r.filer_entity) +
        " — debtor not identified in record</div>" : "";

    var ownCls = "owner" +
      (/unidentified party/i.test(r.owner_name || "") ? " placeholder" : "");
    var badges = badgeHtml(r);
    var av = r._assessed
      ? '<div class="assessed">' + money(r.assessed_value) +
        '<div class="ac">assessed</div></div>' : "";

    el.innerHTML =
      '<div class="lead-main">' +
        '<div class="lead-id">' +
          '<div class="' + ownCls + '">' + esc(r.owner_name || "—") +
            '<span class="otype">' + esc(r.owner_type || "UNKNOWN") +
            "</span></div>" +
          addr + mail + filer +
          '<div class="chips">' + chipHtml(r) + "</div>" +
        "</div>" +
        '<div class="lead-right">' + av +
          '<div class="badges">' + badges + "</div>" +
        "</div>" +
      "</div>" +
      '<div class="detail"></div>';

    el.addEventListener("click", function (ev) {
      if (ev.target.closest(".detail-actions")) return;
      toggleDetail(el, r);
    });
    return el;
  }
  var QUAL_BADGE = {
    "TAX_SALE_LEAD":              { cls: "qsale",  txt: "Tax Sale Lead" },
    "TAX_FORECLOSURE_LEAD":       { cls: "qfcl",   txt: "Tax Foreclosure Lead" },
    "QUALIFIED_TAX_DEFAULT_LEAD": { cls: "qdef",   txt: "Tax Default Lead" },
    "TAX_DEFAULT_LOW_PRIORITY":   { cls: "qlow",   txt: "Tax Default (low priority)" },
    "ESTATE_TITLED_LEAD":         { cls: "estate", txt: "Estate-titled" },
    "REVIEW_REQUIRED":            { cls: "warn",   txt: "Review required" },
    "PRIMARY_EVENT_LEAD":         { cls: "prim",   txt: "Primary event" }
  };
  function badgeHtml(r) {
    var b = [];
    var q = QUAL_BADGE[r._qualClass];
    if (q && r._qualClass !== "PRIMARY_EVENT_LEAD")
      b.push('<span class="badge ' + q.cls + '">' + q.txt + '</span>');
    if (r._isNew)
      b.push('<span class="badge new">NEW</span>');
    if (r._stacked)
      b.push('<span class="badge stack">STACKED · ' +
             esc(r.stack_class || "multi") + '</span>');
    if (r._estate && r._qualClass !== "ESTATE_TITLED_LEAD")
      b.push('<span class="badge estate">Estate-titled</span>');
    if (r._taxHot && r._qualClass !== "TAX_DEFAULT_LOW_PRIORITY")
      b.push('<span class="badge hot">' +
             (r.tax_delinquent_years_back || 0) + 'yr · ' +
             money(r.tax_delinquent_balance) + '</span>');
    else if (r.tax_delinquent && r._qualClass !== "TAX_DEFAULT_LOW_PRIORITY")
      b.push('<span class="badge warm">' +
             (r.tax_delinquent_years_back || 0) + 'yr</span>');
    // Recency: backward-looking, fires only when the COUNTY RECORDED date
    // is within the last 30 days. NEVER fires for past sale dates.
    if (r._isL30 && !r._isNew)
      b.push('<span class="badge l30">Filed ≤30d</span>');
    // Sale-window: forward-looking, fires only when there's an UPCOMING
    // sale in the next 30 days. Past sales get a distinct "Sale past" tag.
    if (r._isUpcomingSale30)
      b.push('<span class="badge sale-soon">Sale ≤30d (upcoming)</span>');
    else if (r._saleStatus === "past")
      b.push('<span class="badge sale-past">Sale past</span>');
    if (r._review)
      b.push('<span class="badge warn">REVIEW REQUIRED</span>');
    if (r.absentee_owner_flag)
      b.push('<span class="badge warn">Absentee</span>');
    if (r.out_of_state_owner_flag)
      b.push('<span class="badge warn">Out-of-state</span>');
    if (r.homestead === "HOMESTEAD")
      b.push('<span class="badge good">Homestead</span>');
    if (r.epcad_enrichment_status === "ENRICHED")
      b.push('<span class="badge">CAD enriched</span>');
    return b.join("");
  }

  // ---------- detail panel (UI-4) ----------
  function toggleDetail(el, r) {
    if (el.classList.contains("open")) {
      el.classList.remove("open"); return;
    }
    var d = el.querySelector(".detail");
    if (!d.dataset.built) { d.innerHTML = detailHtml(r); d.dataset.built = "1"; }
    el.classList.add("open");
    wireDetail(el, d, r);
  }
  function detailHtml(r) {
    var fs = r._fcl;
    var rows = [];
    function add(k, v) { if (v) rows.push([k, v]); }
    add("Resolution", r.parcel_resolution_status +
      (r.epcad_enrichment_status ? " · EPCAD " + r.epcad_enrichment_status : ""));
    if (r.filer_entity) add("Filer entity", esc(r.filer_entity));
    add("Parcel ID", r.parcel_id);
    add("Legal description", esc(r.legal_description));
    add("Mailing address", esc(r.mailing_full_address));
    if (r.assessed_value != null || r.appraised_value != null)
      add("Assessed / Appraised",
        money(r.assessed_value) + " / " + money(r.appraised_value) +
        (r.homestead ? " · " + r.homestead.replace("_", " ").toLowerCase()
          : ""));
    if (fs) {
      add("Foreclosure sale date", esc(fs.sale_date));
      add("DoT document #", esc(fs.dot_document_number));
      add("Lender / beneficiary", esc(fs.lender_beneficiary));
      var legal = ["subdivision", "lot", "block", "unit"].map(function (k) {
        return fs[k] ? k + " " + fs[k] : "";
      }).filter(Boolean).join(", ");
      add("Plat", esc(legal));
    }
    r.signals.forEach(function (s) {
      var ins = (s.instrument_numbers || []).join(", ");
      if (ins) add(s.signal_label + " instr#", esc(ins));
    });
    var urls = (r.source_urls || []).map(function (u) {
      return '<a href="' + esc(u) + '" target="_blank" rel="noopener">' +
        esc(u) + "</a>";
    }).join("<br>");
    if (urls) rows.push(["Source records", urls]);

    var grid = '<dl class="detail-grid">' + rows.map(function (kv) {
      return "<dt>" + kv[0] + "</dt><dd>" + kv[1] + "</dd>";
    }).join("") + "</dl>";
    var mk = marked[r.lead_id];
    return grid +
      '<div class="detail-actions">' +
        '<button class="btn btn-mark act-mark">' +
          (mk ? "✓ Marked for review" : "Mark for review") + "</button>" +
        '<button class="btn act-skip">Skip (hide)</button>' +
        '<button class="btn act-export">Export this lead</button>' +
      "</div>";
  }
  function wireDetail(el, d, r) {
    var mb = d.querySelector(".act-mark");
    mb.onclick = function () {
      if (marked[r.lead_id]) delete marked[r.lead_id];
      else marked[r.lead_id] = true;
      saveMarked();
      el.classList.toggle("marked", !!marked[r.lead_id]);
      mb.textContent = marked[r.lead_id]
        ? "✓ Marked for review" : "Mark for review";
      $("markedCount").textContent = Object.keys(marked).length;
    };
    d.querySelector(".act-skip").onclick = function () {
      skipped[r.lead_id] = true; render();
    };
    d.querySelector(".act-export").onclick = function () {
      exportCsv([r], "el_paso_lead_" + (r.lead_id || "row") + ".csv");
    };
  }

  // ---------- filter summary (UI-5) ----------
  function updateFilterSummary() {
    var parts = [];
    var preset = PRESETS.filter(function (p) {
      return p.id === state.preset && p.id !== "all";
    })[0];
    if (preset) parts.push("<b>" + esc(preset.label) + "</b>");
    if (state.search) parts.push('search "' + esc(state.search) + '"');
    if (state.saleWindow !== "any")
      parts.push("sale &le; " + state.saleWindow + " days");
    var sigOff = Object.keys(state.signals).filter(function (k) {
      return !state.signals[k];
    });
    if (sigOff.length)
      parts.push((Object.keys(state.signals).length - sigOff.length) +
        " signal type(s)");
    var ownOff = Object.keys(state.owners).filter(function (k) {
      return !state.owners[k];
    });
    if (ownOff.length)
      parts.push(Object.keys(state.owners).filter(function (k) {
        return state.owners[k];
      }).join("/"));
    if (state.valMin != null) parts.push("min " + money(state.valMin));
    if (state.valMax != null) parts.push("max " + money(state.valMax));
    if (state.absentee) parts.push("absentee");
    if (state.oos) parts.push("out-of-state");
    if (state.review) parts.push("review-required");
    if (state.multiOnly) parts.push("multi-signal");
    $("filterSummary").innerHTML = parts.length
      ? "Showing: " + parts.join(" · ")
      : "Showing: <b>all leads</b> — sorted by urgency";
  }

  // ---------- CSV (UI-8) ----------
  var CSV_COLS = ["lead_id", "owner_name", "owner_type",
    "parcel_resolution_status", "epcad_enrichment_status", "filer_entity",
    "property_full_address", "property_city", "property_zip",
    "mailing_full_address", "mailing_state", "assessed_value",
    "appraised_value", "homestead", "absentee_owner_flag",
    "out_of_state_owner_flag", "signal_count", "primary_signal",
    "latest_event_date", "legal_description", "parcel_id"];
  function exportCsv(rows, fname) {
    var head = CSV_COLS.concat(["sale_date", "signal_types", "source_urls"]);
    var lines = [head.join(",")];
    rows.forEach(function (r) {
      var cells = CSV_COLS.map(function (c) { return q(r[c]); });
      cells.push(q(r._fcl ? r._fcl.sale_date : ""));
      cells.push(q((r.signal_types || []).join("; ")));
      cells.push(q((r.source_urls || []).join(" ")));
      lines.push(cells.join(","));
    });
    var blob = new Blob([lines.join("\n")], { type: "text/csv" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = fname;
    document.body.appendChild(a); a.click(); a.remove();
  }
  function q(v) {
    if (v == null) v = "";
    return '"' + String(v).replace(/"/g, '""') + '"';
  }

  // ---------- start ----------
  function start() {
    // Canonical data path: <script src="data.js"></script> in index.html
    // sets window.LEADS before app.js runs. A script include cannot return
    // HTML-as-JSON, so a 404 on data.js produces a clean
    // "DATA is null" state we surface via a console message — not a JSON
    // parse error from fetch()ing a 404 HTML page.
    if (DATA) { boot(DATA); return; }
    console.error("data.js did not set window.LEADS — dashboard/data.js is "
                  + "missing or not loaded. Check the deployment.");
    document.documentElement.setAttribute("data-ready", "1");
  }
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", start);
  else start();
})();
