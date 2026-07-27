(() => {
  "use strict";

  /* ---------- constants ---------- */

  const PROFILE_KEY = "mortgageDashboard.profile.v1";
  const RATES_KEY = "mortgageDashboard.comparisonRates.v1";
  const BOE_CACHE_KEY = "mortgageDashboard.boeRateCache.v1";

  const BOE_SERIES_CODE = "IUDBEDR"; // Bank of England official Bank Rate
  const BOE_DATABASE_URL = "https://www.bankofengland.co.uk/boeapps/database/";

  const DEFAULT_PROFILE = {
    lender: "Barclays",
    region: "England",
    propertyValue: 465000,
    mortgageLeft: 316000,
    termYears: 36,
  };

  const DEFAULT_RATES = [
    { type: "Two year fixed", rate: "", notes: "" },
    { type: "Three year fixed", rate: "", notes: "" },
    { type: "Five year fixed", rate: "", notes: "" },
    { type: "Variable", rate: "", notes: "" },
  ];

  // Used only if a live fetch has never succeeded and nothing is cached yet.
  const FALLBACK_RATE = {
    rate: 3.75,
    date: "2026-06-17",
    note: "fallback value — could not reach the Bank of England database",
  };

  const gbp = new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    maximumFractionDigits: 0,
  });

  /* ---------- storage helpers ---------- */

  function loadJSON(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return fallback;
      const parsed = JSON.parse(raw);
      return parsed ?? fallback;
    } catch {
      return fallback;
    }
  }

  function saveJSON(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* localStorage unavailable (e.g. private mode quota) — ignore */
    }
  }

  /* =========================================================
     Base rate card
     ========================================================= */

  const rateValueEl = document.getElementById("rate-value");
  const rateDateEl = document.getElementById("rate-date");
  const rateStatusEl = document.getElementById("rate-status");
  const rateRefreshBtn = document.getElementById("rate-refresh");

  function formatDisplayDate(isoDate) {
    const d = new Date(isoDate + "T00:00:00");
    if (Number.isNaN(d.getTime())) return isoDate;
    return d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
  }

  function renderRate({ rate, date }, { fromCache = false, error = null } = {}) {
    rateValueEl.textContent = `${rate.toFixed(2)}%`;
    rateDateEl.textContent = `As of ${formatDisplayDate(date)}`;

    if (error) {
      rateStatusEl.innerHTML =
        `Live fetch failed (${escapeHtml(error)}). Showing ${fromCache ? "last cached" : "a fallback"} value. ` +
        `Check the <a href="${BOE_DATABASE_URL}" target="_blank" rel="noopener">Bank of England database</a> directly.`;
    } else {
      rateStatusEl.textContent = "";
    }
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = String(str);
    return div.innerHTML;
  }

  function ddMonYyyy(date) {
    const day = String(date.getDate()).padStart(2, "0");
    const month = date.toLocaleDateString("en-GB", { month: "short" });
    return `${day}/${month}/${date.getFullYear()}`;
  }

  function buildBoeUrl() {
    const from = new Date();
    from.setFullYear(from.getFullYear() - 3);
    const params = new URLSearchParams({
      "csv.x": "yes",
      Datefrom: ddMonYyyy(from),
      Dateto: "now",
      SeriesCodes: BOE_SERIES_CODE,
      CSVF: "TT",
      UsingCodes: "Y",
      VPD: "Y",
      VFD: "N",
    });
    return `${BOE_DATABASE_URL}_iadb-fromshowcolumns.asp?${params.toString()}`;
  }

  // Parses the BoE IADB "tabular with titles" CSV: a header row followed by
  // "DD Mon YYYY,value" rows for the requested series.
  function parseBoeCsv(text) {
    const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    if (lines.length < 2) throw new Error("empty response");

    const splitCsvLine = (line) => line.split(",").map((cell) => cell.replace(/^"|"$/g, "").trim());

    const header = splitCsvLine(lines[0]);
    let valueCol = header.findIndex((h) => h.toUpperCase() === BOE_SERIES_CODE);
    if (valueCol === -1) valueCol = 1; // best-effort: assume second column
    const dateCol = 0;

    const series = [];
    for (let i = 1; i < lines.length; i++) {
      const cells = splitCsvLine(lines[i]);
      const rawDate = cells[dateCol];
      const rawValue = cells[valueCol];
      if (!rawDate || rawValue === undefined || rawValue === "" || rawValue.toUpperCase() === "ND") continue;
      const value = Number.parseFloat(rawValue);
      const parsedDate = new Date(rawDate);
      if (Number.isNaN(value) || Number.isNaN(parsedDate.getTime())) continue;
      series.push({ date: parsedDate.toISOString().slice(0, 10), rate: value });
    }

    if (series.length === 0) throw new Error("no data rows found");
    series.sort((a, b) => (a.date < b.date ? -1 : 1));
    return series;
  }

  async function fetchBankRate() {
    const res = await fetch(buildBoeUrl(), { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const text = await res.text();
    const series = parseBoeCsv(text);
    return series[series.length - 1];
  }

  async function refreshBankRate() {
    rateRefreshBtn.disabled = true;
    rateDateEl.textContent = "Refreshing…";
    try {
      const latest = await fetchBankRate();
      saveJSON(BOE_CACHE_KEY, latest);
      renderRate(latest);
    } catch (err) {
      const cached = loadJSON(BOE_CACHE_KEY, null);
      if (cached) {
        renderRate(cached, { fromCache: true, error: err.message });
      } else {
        renderRate({ rate: FALLBACK_RATE.rate, date: FALLBACK_RATE.date }, { fromCache: false, error: err.message });
      }
    } finally {
      rateRefreshBtn.disabled = false;
    }
  }

  rateRefreshBtn.addEventListener("click", refreshBankRate);

  // Show cached/fallback instantly, then attempt a live refresh.
  const cachedOnLoad = loadJSON(BOE_CACHE_KEY, null);
  if (cachedOnLoad) {
    renderRate(cachedOnLoad);
  } else {
    renderRate({ rate: FALLBACK_RATE.rate, date: FALLBACK_RATE.date });
  }
  refreshBankRate();

  /* =========================================================
     Mortgage profile + LTV
     ========================================================= */

  const form = document.getElementById("profile-form");
  const lenderInput = document.getElementById("lender");
  const regionInput = document.getElementById("region");
  const propertyValueInput = document.getElementById("propertyValue");
  const mortgageLeftInput = document.getElementById("mortgageLeft");
  const termYearsInput = document.getElementById("termYears");
  const termValueLabel = document.getElementById("termValue");

  const ltvValueEl = document.getElementById("ltv-value");
  const ltvBarFillEl = document.getElementById("ltv-bar-fill");
  const ltvMortgageEl = document.getElementById("ltv-mortgage");
  const ltvPropertyEl = document.getElementById("ltv-property");
  const ltvEquityEl = document.getElementById("ltv-equity");

  function getProfile() {
    return {
      lender: lenderInput.value.trim(),
      region: regionInput.value,
      propertyValue: Number(propertyValueInput.value) || 0,
      mortgageLeft: Number(mortgageLeftInput.value) || 0,
      termYears: Number(termYearsInput.value) || 1,
    };
  }

  function applyProfile(profile) {
    lenderInput.value = profile.lender;
    regionInput.value = profile.region;
    propertyValueInput.value = profile.propertyValue;
    mortgageLeftInput.value = profile.mortgageLeft;
    termYearsInput.value = profile.termYears;
    termValueLabel.textContent = `${profile.termYears} year${profile.termYears === 1 ? "" : "s"}`;
  }

  function updateLtv() {
    const { propertyValue, mortgageLeft } = getProfile();
    const ltv = propertyValue > 0 ? (mortgageLeft / propertyValue) * 100 : 0;
    const clampedForBar = Math.min(Math.max(ltv, 0), 100);

    ltvValueEl.textContent = propertyValue > 0 ? `${ltv.toFixed(1)}%` : "—";
    ltvBarFillEl.style.width = `${clampedForBar}%`;
    ltvMortgageEl.textContent = gbp.format(mortgageLeft);
    ltvPropertyEl.textContent = gbp.format(propertyValue);
    ltvEquityEl.textContent = gbp.format(Math.max(propertyValue - mortgageLeft, 0));
  }

  function persistProfile() {
    saveJSON(PROFILE_KEY, getProfile());
  }

  function onProfileInput() {
    termValueLabel.textContent = `${termYearsInput.value} year${termYearsInput.value === "1" ? "" : "s"}`;
    updateLtv();
    persistProfile();
  }

  form.addEventListener("input", onProfileInput);

  applyProfile(loadJSON(PROFILE_KEY, DEFAULT_PROFILE));
  updateLtv();

  /* =========================================================
     Rate comparison table
     ========================================================= */

  const tbody = document.getElementById("rates-tbody");
  const addRowBtn = document.getElementById("add-row");

  function persistRates() {
    const rows = Array.from(tbody.querySelectorAll("tr")).map((tr) => ({
      type: tr.querySelector(".rate-type").value,
      rate: tr.querySelector(".rate-input").value,
      notes: tr.querySelector(".rate-notes").value,
    }));
    saveJSON(RATES_KEY, rows);
  }

  function createRow({ type = "", rate = "", notes = "" } = {}) {
    const tr = document.createElement("tr");

    const typeTd = document.createElement("td");
    const typeInput = document.createElement("input");
    typeInput.type = "text";
    typeInput.className = "rate-type";
    typeInput.placeholder = "Mortgage type";
    typeInput.value = type;
    typeTd.appendChild(typeInput);

    const rateTd = document.createElement("td");
    rateTd.className = "rate-cell";
    const rateInput = document.createElement("input");
    rateInput.type = "number";
    rateInput.className = "rate-input";
    rateInput.placeholder = "0.00";
    rateInput.step = "0.01";
    rateInput.min = "0";
    rateInput.max = "25";
    rateInput.value = rate;
    rateTd.appendChild(rateInput);

    const notesTd = document.createElement("td");
    const notesInput = document.createElement("input");
    notesInput.type = "text";
    notesInput.className = "rate-notes";
    notesInput.placeholder = "e.g. product fee, source, date checked";
    notesInput.value = notes;
    notesTd.appendChild(notesInput);

    const actionTd = document.createElement("td");
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "row-remove";
    removeBtn.setAttribute("aria-label", "Remove row");
    removeBtn.textContent = "✕";
    removeBtn.addEventListener("click", () => {
      tr.remove();
      persistRates();
    });
    actionTd.appendChild(removeBtn);

    tr.append(typeTd, rateTd, notesTd, actionTd);
    tr.addEventListener("input", persistRates);
    return tr;
  }

  function renderRates(rows) {
    tbody.innerHTML = "";
    rows.forEach((row) => tbody.appendChild(createRow(row)));
  }

  addRowBtn.addEventListener("click", () => {
    tbody.appendChild(createRow());
    persistRates();
  });

  renderRates(loadJSON(RATES_KEY, DEFAULT_RATES));
})();
