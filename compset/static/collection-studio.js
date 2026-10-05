"use strict";

(() => {
  const root = document.getElementById("collection-studio");
  const ratesRoot = document.getElementById("rates-workspace");
  if (!root || !ratesRoot) return;

  const state = {
    status: null, rows: [], total: 0, statusRevision: null, listingRevision: null, offset: 0, query: "", bedrooms: "",
    selected: null, calendar: null, calendarStart: today(), statusController: null,
    listingsController: null, mapController: null, calendarController: null, profileController: null, searchTimer: null, lastCounts: null,
    map: null, markers: [], mapPoints: [], mapRevision: null, mapGeneration: 0, mounted: false, busy: false, ownerSession: false, sessionReady: null,
  };

  function today() {
    const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Dubai", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
    const value = Object.fromEntries(parts.map(part => [part.type, part.value]));
    return `${value.year}-${value.month}-${value.day}`;
  }

  function node(tag, className, value) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (value !== undefined && value !== null) item.textContent = String(value);
    return item;
  }

  function add(parent, ...children) { children.filter(Boolean).forEach(child => parent.appendChild(child)); return parent; }
  function button(label, className, action, ariaLabel) {
    const item = node("button", className, label); item.type = "button";
    if (ariaLabel) item.setAttribute("aria-label", ariaLabel);
    item.addEventListener("click", action); return item;
  }
  function value(item, fallback = "—") { return item === undefined || item === null || item === "" ? fallback : String(item); }
  function count(item) { return Number.isFinite(Number(item)) && item !== null ? new Intl.NumberFormat().format(Number(item)) : "—"; }
  function stamp(item) {
    if (!item) return "Not observed yet";
    const date = new Date(item);
    return Number.isNaN(date.getTime()) ? String(item) : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  }
  function statusLabel(item) { return value(item, "waiting").replaceAll("_", " "); }
  function notify(message, tone = "info") {
    const live = root.querySelector("[data-live]");
    if (!live) return;
    live.textContent = message || "";
    live.dataset.tone = tone;
  }
  function activeTab() { return !document.hidden && !ratesRoot.hidden && !root.hidden; }
  function appendMetric(parent, label, metric, note, className = "") {
    const card = node("article", `cs-metric ${className}`.trim());
    add(card, node("span", "cs-label", label), node("strong", "cs-value", metric), node("span", "cs-note", note));
    parent.appendChild(card);
  }

  function mount() {
    if (state.mounted) return;
    state.mounted = true;
    root.className = "cs-shell";

    const header = node("header", "cs-header");
    const title = add(node("div", "cs-title"), node("p", "cs-eyebrow", "LIVE COLLECTION · DUBAI"), node("h2", "", "Profiles and calendars"), node("p", "cs-subtitle", "A local view of observed listings, job progress, source health and daily availability."));
    const actions = node("div", "cs-actions");
    const badge = node("span", "cs-status"); badge.dataset.status = "idle";
    const badgeDot = node("i", "cs-status-dot"); badgeDot.setAttribute("aria-hidden", "true");
    add(badge, badgeDot, node("span", "cs-status-label", "Waiting for status"));
    const refresh = button("Refresh Dubai", "cs-primary", startRefresh);
    refresh.dataset.refresh = "true";
    refresh.setAttribute("aria-describedby", "cs-refresh-help");
    const viewTabs = node("div", "cs-view-tabs"); viewTabs.setAttribute("role", "group"); viewTabs.setAttribute("aria-label", "Collection view");
    const dubaiTab = button("Dubai library", "cs-view-tab is-active", () => selectView("dubai")); dubaiTab.setAttribute("aria-pressed", "true");
    const hotelsTab = button("Hotel research", "cs-view-tab", () => selectView("hotels")); hotelsTab.setAttribute("aria-pressed", "false");
    add(viewTabs, dubaiTab, hotelsTab);
    add(actions, viewTabs, badge, refresh);
    add(header, title, actions);

    const refreshHelp = node("p", "cs-refresh-help", "Public view · refresh needs an owner link."); refreshHelp.id = "cs-refresh-help"; refreshHelp.dataset.ownerHelp = "true";
    const live = node("p", "cs-live"); live.dataset.live = "true"; live.setAttribute("role", "status"); live.setAttribute("aria-live", "polite");

    const metrics = node("div", "cs-metrics"); metrics.dataset.metrics = "true";
    const progress = node("section", "cs-progress-card"); progress.dataset.progress = "true";
    const middle = node("div", "cs-workspace");
    const library = node("section", "cs-library"); library.setAttribute("aria-labelledby", "cs-library-title");
    const libraryTitle = node("h3", "", "Dubai listings"); libraryTitle.id = "cs-library-title";
    const columnsLink = node("a", "cs-columns-link", "Column headings ↓"); columnsLink.href = "/exports/collection-columns.csv"; columnsLink.download = "collection-columns.csv";
    const filters = node("div", "cs-filters");
    const searchLabel = node("label", "cs-field");
    add(searchLabel, node("span", "", "Search listings"));
    const search = node("input", ""); search.type = "search"; search.placeholder = "Name or listing ID"; search.autocomplete = "off"; search.setAttribute("aria-label", "Search Dubai listings");
    search.addEventListener("input", () => { state.query = search.value.trim(); state.offset = 0; cancelMapLoad(); debounceListings(); });
    add(searchLabel, search);
    const bedroomsLabel = node("label", "cs-field"); add(bedroomsLabel, node("span", "", "Bedrooms"));
    const bedrooms = node("select", ""); bedrooms.setAttribute("aria-label", "Filter Dubai listings by bedrooms");
    for (const [key, label] of [["", "Any"], ["0", "Studio"], ["1", "1 bedroom"], ["2", "2 bedrooms"], ["3", "3 bedrooms"], ["4", "4 bedrooms"], ["5", "5 bedrooms"], ["6", "6 bedrooms"], ["7", "7 bedrooms"]]) {
      const option = node("option", "", label); option.value = key; bedrooms.appendChild(option);
    }
    bedrooms.addEventListener("change", () => { state.bedrooms = bedrooms.value; state.offset = 0; cancelMapLoad(); loadListings(); loadMapPoints(true); });
    add(bedroomsLabel, bedrooms);
    add(filters, searchLabel, bedroomsLabel);

    const libraryMeta = node("div", "cs-list-meta"); libraryMeta.dataset.listmeta = "true";
    const list = node("div", "cs-list"); list.dataset.list = "true"; list.setAttribute("aria-live", "polite");
    const pager = node("div", "cs-pager");
    const previous = button("←", "cs-page-button", () => { state.offset = Math.max(0, state.offset - 50); loadListings(); }, "Previous listings");
    const pageLabel = node("span", ""); pageLabel.dataset.page = "true";
    const next = button("→", "cs-page-button", () => { if (state.offset + 50 < state.total) { state.offset += 50; loadListings(); } }, "Next listings");
    add(pager, previous, pageLabel, next);
    pager.dataset.pager = "true";
    add(library, libraryTitle, columnsLink, filters, libraryMeta, list, pager);

    const mapPanel = node("section", "cs-map-panel"); mapPanel.setAttribute("aria-label", "Map of observed Dubai listings");
    const mapHeading = node("div", "cs-map-heading");
    const mapHeadingTitle = node("div", "cs-map-title");
    mapHeadingTitle.appendChild(node("strong", "", "Observed locations"));
    const mapMeta = node("span", "cs-map-meta"); mapMeta.dataset.mapmeta = "true"; mapMeta.textContent = "Loading saved locations…";
    const mapActions = node("div", "cs-map-actions");
    const fitMap = button("Fit results", "cs-fit-map", fitMapResults, "Fit all matching saved listings on the map"); fitMap.dataset.fitmap = "true";
    add(mapHeadingTitle, mapMeta); add(mapActions, fitMap); add(mapHeading, mapHeadingTitle, mapActions);
    const map = node("div", "cs-map"); map.id = "cs-map"; map.setAttribute("role", "region"); map.setAttribute("aria-label", "Map of all matching saved Dubai listings");
    add(mapPanel, mapHeading, map);
    add(middle, library, mapPanel);

    const calendarPanel = node("section", "cs-calendar-panel"); calendarPanel.setAttribute("aria-labelledby", "cs-calendar-title");
    const calendarHeading = node("div", "cs-calendar-heading");
    const calendarTitle = node("h3", "", "Daily calendar"); calendarTitle.id = "cs-calendar-title";
    const calendarMeta = node("span", "cs-calendar-meta"); calendarMeta.dataset.calmeta = "true";
    const calendarActions = node("div", "cs-calendar-actions");
    const priorDays = button("←", "cs-page-button", () => moveCalendar(-31), "Previous 31 calendar days");
    const nextDays = button("→", "cs-page-button", () => moveCalendar(31), "Next 31 calendar days");
    add(calendarActions, priorDays, nextDays); add(calendarHeading, calendarTitle, calendarMeta, calendarActions);
    const calendar = node("div", "cs-calendar"); calendar.dataset.calendar = "true";
    const calendarFoot = node("p", "cs-calendar-foot", "Availability, check-in and check-out restrictions come from the recorded source. Nightly prices may be unknown.");
    add(calendarPanel, calendarHeading, calendar, calendarFoot);

    const details = node("details", "cs-details");
    const summary = node("summary", "", "Job, sources, errors and repairs");
    const drawer = node("div", "cs-drawer"); drawer.dataset.drawer = "true";
    add(details, summary, drawer);
    const profileDialog = node("dialog", "cs-profile-dialog");
    profileDialog.setAttribute("aria-labelledby", "cs-profile-title");
    const profileHeading = node("div", "cs-profile-heading");
    const profileTitle = node("h3", "", "Listing details"); profileTitle.id = "cs-profile-title";
    const profileClose = button("Close", "cs-profile-close", () => profileDialog.close(), "Close listing details");
    add(profileHeading, profileTitle, profileClose);
    const profileContent = node("div", "cs-profile-content"); profileContent.dataset.profile = "true";
    add(profileDialog, profileHeading, profileContent);
    const hotelView = buildHotelView();
    add(root, header, refreshHelp, live, metrics, progress, middle, calendarPanel, hotelView, details, profileDialog);

    state.nodes = { badge, refresh, metrics, progress, list, libraryMeta, pageLabel, previous, next, map, mapMeta, fitMap, calendar, calendarMeta, drawer, ratesRoot, middle, calendarPanel, hotelView, dubaiTab, hotelsTab, profileDialog, profileContent };
    initializeMap();
    state.visibilityObserver = new MutationObserver(syncVisibility);
    state.visibilityObserver.observe(ratesRoot, { attributes: true, attributeFilter: ["hidden"] });
    syncVisibility();
    state.sessionReady = restoreOwnerSession();
    loadStatus(); loadListings(); loadMapPoints(true);
    state.timer = window.setInterval(() => { if (activeTab()) loadStatus(); }, 10000);
    document.addEventListener("visibilitychange", () => { if (activeTab()) { loadStatus(); if (!state.rows.length) loadListings(); } });
    window.addEventListener("beforeunload", () => { window.clearInterval(state.timer); state.visibilityObserver.disconnect(); cancelMapLoad(); });
  }

  function syncVisibility() { root.hidden = ratesRoot.hidden; }
  function initializeMap() {
    const mapNode = state.nodes.map;
    if (!window.L || typeof window.L.map !== "function") { mapNode.textContent = "Map library is unavailable. The listing library remains usable."; return; }
    try {
      state.map = window.L.map(mapNode, { scrollWheelZoom: false, tap: true }).setView([25.2048, 55.2708], 10);
      if (typeof window.L.canvas === "function") state.canvasRenderer = window.L.canvas({ padding: 0.5 });
      window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).addTo(state.map);
    } catch (_) { mapNode.textContent = "Map could not initialize. The listing library remains usable."; state.map = null; }
  }

  async function jsonFetch(url, options = {}, controllerKey) {
    if (controllerKey && state[controllerKey]) state[controllerKey].abort();
    const controller = new AbortController();
    if (controllerKey) state[controllerKey] = controller;
    const response = await fetch(url, { cache: "no-store", ...options, signal: controller.signal });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) { const error = new Error(value(data.error || data.message, `Request failed (${response.status})`)); error.status = response.status; throw error; }
    return data;
  }

  function stripControlFragment() {
    window.history.replaceState(window.history.state, "", `${window.location.pathname}${window.location.search}`);
  }

  async function exchangeOwnerLink() {
    const fragment = window.location.hash;
    if (!fragment.startsWith("#control=")) return false;
    let token;
    try { token = decodeURIComponent(fragment.slice("#control=".length)); }
    catch (_) { stripControlFragment(); return false; }
    if (!token) { stripControlFragment(); return false; }
    try {
      const response = await fetch("/api/collection/session", {
        method: "POST", cache: "no-store", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CompSet-Request": "dashboard-v1" },
        body: JSON.stringify({ token }),
      });
      const result = await response.json().catch(() => ({}));
      state.ownerSession = response.ok && result.state !== "denied";
      const help = root.querySelector("[data-owner-help]");
      if (help && state.ownerSession) help.textContent = "Owner access ready · refresh uses the active collection worker.";
      else if (help) help.textContent = "Owner link could not be verified. Refresh remains locked.";
      return state.ownerSession;
    } catch (_) {
      state.ownerSession = false;
      const help = root.querySelector("[data-owner-help]");
      if (help) help.textContent = "Owner link could not be verified. Refresh remains locked.";
      return false;
    } finally { stripControlFragment(); }
  }

  async function restoreOwnerSession() {
    if (window.location.hash.startsWith("#control=")) {
      const exchanged = await exchangeOwnerLink();
      if (exchanged) return true;
    }
    try {
      const response = await fetch("/api/collection/session", {
        method: "GET", cache: "no-store", credentials: "same-origin",
        headers: { "X-CompSet-Request": "dashboard-v1" },
      });
      const result = await response.json().catch(() => ({}));
      state.ownerSession = response.ok && result.owner === true;
    } catch (_) { state.ownerSession = false; }
    const help = root.querySelector("[data-owner-help]");
    if (help) help.textContent = state.ownerSession
      ? "Owner access ready · refresh uses the active collection worker."
      : "Public view · refresh needs an owner link.";
    return state.ownerSession;
  }

  function selectView(view) {
    const hotels = view === "hotels";
    state.nodes.middle.hidden = hotels;
    state.nodes.calendarPanel.hidden = hotels;
    state.nodes.hotelView.hidden = !hotels;
    state.nodes.dubaiTab.classList.toggle("is-active", !hotels);
    state.nodes.hotelsTab.classList.toggle("is-active", hotels);
    state.nodes.dubaiTab.setAttribute("aria-pressed", String(!hotels));
    state.nodes.hotelsTab.setAttribute("aria-pressed", String(hotels));
    if (hotels && !state.hotelsLoaded) loadHotels();
    if (state.map && !hotels) window.setTimeout(() => state.map.invalidateSize(), 0);
  }

  function buildHotelView() {
    const panel = node("section", "cs-hotel-view"); panel.hidden = true; panel.setAttribute("aria-labelledby", "cs-hotels-title");
    const heading = node("div", "cs-hotel-header");
    const title = node("div", "");
    add(title, node("h3", "", "Saved 17 hotels"), node("p", "cs-hotel-note", "Hotel identity and saved rate evidence remain separate from Airbnb calendars."));
    const coverage = node("span", "cs-hotel-coverage"); coverage.dataset.hotelcoverage = "true";
    add(heading, title, coverage);
    const controls = node("div", "cs-hotel-controls");
    const searchLabel = node("label", "cs-field"); add(searchLabel, node("span", "", "Find a hotel"));
    const search = node("input", ""); search.type = "search"; search.placeholder = "Hotel name"; search.autocomplete = "off"; search.setAttribute("aria-label", "Search saved hotels");
    search.addEventListener("input", () => { state.hotelQuery = search.value.trim(); state.hotelOffset = 0; window.clearTimeout(state.hotelSearchTimer); state.hotelSearchTimer = window.setTimeout(loadHotels, 250); });
    add(searchLabel, search);
    const dateLabel = node("label", "cs-field"); add(dateLabel, node("span", "", "Check-in date"));
    const date = node("input", ""); date.type = "date"; date.value = today(); date.setAttribute("aria-label", "Select hotel price check-in date");
    date.addEventListener("change", () => { state.hotelDate = date.value || today(); if (state.selectedHotel) loadHotelRates(); });
    add(dateLabel, date); add(controls, searchLabel, dateLabel);
    const columns = node("div", "cs-hotel-columns");
    const hotelList = node("div", "cs-hotel-list"); hotelList.dataset.hotelList = "true"; hotelList.setAttribute("aria-label", "Saved hotel profiles");
    const ratePanel = node("section", "cs-hotel-rates"); ratePanel.setAttribute("aria-labelledby", "cs-hotels-title");
    const rateTitle = node("div", "cs-hotel-rate-title");
    const selected = node("strong", "", "Choose a saved hotel"); selected.dataset.selectedhotel = "true";
    const rateMeta = node("span", "", "Rates stay separated by source, date, currency and precision."); rateMeta.dataset.ratemeta = "true";
    add(rateTitle, selected, rateMeta);
    const rateList = node("div", "cs-hotel-rate-list"); rateList.dataset.hotelRates = "true";
    add(ratePanel, rateTitle, rateList); add(columns, hotelList, ratePanel);
    add(panel, heading, controls, columns);
    state.hotelNodes = { panel, search, date, coverage, hotelList, selected, rateMeta, rateList };
    return panel;
  }

  async function loadHotels() {
    const params = new URLSearchParams({ offset: String(state.hotelOffset || 0), limit: "50", query: state.hotelQuery || "" });
    try {
      const result = await jsonFetch(`/api/collection/hotels?${params}`, {}, "hotelsController");
      state.hotels = Array.isArray(result.hotels) ? result.hotels : [];
      state.hotelTotal = Number.isFinite(Number(result.total)) ? Number(result.total) : 0;
      state.hotelRevision = result.revision;
      state.hotelCoverage = result.coverage || {};
      state.hotelsLoaded = true;
      renderHotels();
    } catch (error) {
      if (error.name === "AbortError") return;
      state.hotelNodes.hotelList.replaceChildren(node("p", "cs-empty", `Hotel data is unavailable: ${error.message}`));
    }
  }

  function renderHotels() {
    const ui = state.hotelNodes;
    ui.coverage.textContent = `${count(state.hotelCoverage.saved_hotels)} saved · ${count(state.hotelCoverage.public_all_in_cells)} public all-in rate cells`;
    ui.hotelList.replaceChildren();
    const rows = state.hotels || [];
    if (!rows.length) ui.hotelList.appendChild(node("p", "cs-empty", "No saved hotels match this search."));
    for (const hotel of rows) {
      const selected = state.selectedHotel && String(state.selectedHotel.hotel_id) === String(hotel.hotel_id);
      const card = button("", `cs-hotel-card${selected ? " is-selected" : ""}`, () => selectHotel(hotel));
      card.setAttribute("aria-pressed", String(Boolean(selected)));
      const name = node("strong", "", value(hotel.name, `Hotel ${hotel.hotel_id}`));
      const info = node("span", "", `${count(hotel.saved_rate_observations)} saved rate observations · ${statusLabel(hotel.price_status || "unknown_all_in")}`);
      const membership = node("span", "cs-member-badge", "Saved 17 member");
      add(card, name, info, membership); ui.hotelList.appendChild(card);
    }
    if (!rows.length) { ui.selected.textContent = "Choose a saved hotel"; ui.rateMeta.textContent = "No hotel selected."; }
  }

  async function selectHotel(hotel) {
    state.selectedHotel = hotel;
    state.hotelRates = null;
    state.hotelDate = state.hotelNodes.date.value || today();
    state.hotelNodes.selected.textContent = value(hotel.name, `Hotel ${hotel.hotel_id}`);
    state.hotelNodes.rateMeta.textContent = "Loading saved prices…";
    state.hotelNodes.rateList.replaceChildren(node("p", "cs-empty", "Loading stored rate evidence…"));
    renderHotels();
    await loadHotelRates();
  }

  async function loadHotelRates() {
    if (!state.selectedHotel) return;
    const params = new URLSearchParams({ hotel_id: String(state.selectedHotel.hotel_id), start: state.hotelDate || today(), days: "30" });
    try {
      state.hotelRates = await jsonFetch(`/api/collection/hotels?${params}`, {}, "hotelRatesController");
      renderHotelRates();
    } catch (error) {
      if (error.name === "AbortError") return;
      state.hotelNodes.rateList.replaceChildren(node("p", "cs-empty", `Hotel rates are unavailable: ${error.message}`));
    }
  }

  function renderHotelRates() {
    const data = state.hotelRates || {}, rows = Array.isArray(data.rates) ? data.rates : [], ui = state.hotelNodes;
    const context = data.rate_context || {};
    ui.rateMeta.textContent = `${count(data.rate_count)} source records · ${value(context.currency, "Currency unknown")} · ${value(context.start, state.hotelDate)} for ${value(context.days, "30")} days`;
    ui.rateList.replaceChildren();
    if (!rows.length) { ui.rateList.appendChild(node("p", "cs-empty", "No saved price observation for this hotel and date range.")); return; }
    for (const row of rows) ui.rateList.appendChild(hotelRateCard(row));
    ui.rateList.appendChild(node("p", "cs-rate-caveat", "Rates are shown per source and stay context. No lowest or all-in total is inferred."));
  }

  function hotelRateCard(row) {
    const card = node("article", "cs-hotel-rate");
    const heading = node("div", "cs-hotel-rate-head");
    add(heading, node("strong", "", value(row.provider, "Source unknown")), node("span", "cs-price-state", statusLabel(row.price_status || row.precision || "unknown")));
    const dates = `${value(row.checkin)} → ${value(row.checkout)}`;
    const amount = row.price_status === "public_all_in" && row.comparable_public_total === true && row.amount !== null && row.amount !== undefined
      ? `Public all-in total · ${value(row.currency, "Currency unknown")} ${row.amount}`
      : row.price_status === "approximate" && row.approximate_amount !== null && row.approximate_amount !== undefined
        ? `Approximate amount · ${value(row.currency, "Currency unknown")} ${row.approximate_amount}`
        : row.amount !== null && row.amount !== undefined
          ? `${statusLabel(row.price_status || "source amount")} · ${value(row.currency, "Currency unknown")} ${row.amount}`
          : "Price unknown";
    const detail = node("p", "", `${value(row.channel, "Channel unknown")} · ${dates} · ${value(row.precision, "Precision unknown")} · ${value(row.availability, "Availability unknown")}`);
    const context = node("p", "cs-hotel-rate-context", `${amount} · ${stamp(row.observed_at)}${row.room_name ? ` · ${String(row.room_name)}` : ""}`);
    const evidence = [];
    if (row.identity_verified === true) evidence.push("identity verified");
    if (row.context_verified === true) evidence.push("stay context verified");
    if (row.taxes_included === true) evidence.push("taxes included");
    if (row.mandatory_fees_included === true) evidence.push("mandatory fees included");
    if (row.public_eligibility_verified === true) evidence.push("public eligibility verified");
    if (row.price_status === "public_all_in" && row.comparable_public_total !== true) evidence.push("all-in comparison not verified");
    add(card, heading, detail, context, node("p", "cs-hotel-rate-evidence", evidence.length ? evidence.join(" · ") : "Price basis and eligibility are not fully verified."));
    return card;
  }

  async function loadStatus() {
    if (!activeTab()) return;
    try {
      const result = await jsonFetch("/api/collection/status", {}, "statusController");
      const changed = state.status && ((result.revision !== undefined && result.revision !== state.statusRevision) || JSON.stringify(result.counts) !== state.lastCounts);
      state.status = result;
      state.statusRevision = result.revision;
      state.lastCounts = JSON.stringify(result.counts || {});
      renderStatus();
      if (changed) { loadListings(true); loadMapPoints(false); if (state.selected) loadCalendar(); }
    } catch (error) {
      if (error.name === "AbortError") return;
      notify(`Collection status is unavailable: ${error.message}`, "error");
      if (!state.status) renderStatusError();
    }
  }

  function renderStatusError() {
    const badge = state.nodes.badge; badge.dataset.status = "unknown";
    badge.querySelector(".cs-status-label").textContent = "Status unavailable";
    state.nodes.metrics.replaceChildren();
    appendMetric(state.nodes.metrics, "Profiles", "—", "Waiting for local service");
    appendMetric(state.nodes.metrics, "Calendars", "—", "Waiting for local service");
    appendMetric(state.nodes.metrics, "Daily price rows", "—", "Waiting for local service");
    appendMetric(state.nodes.metrics, "Validated this hour", "—", "Provider limit not measured");
  }

  function renderStatus() {
    const data = state.status || {}, counts = data.counts || {}, progress = data.progress || {}, pool = data.proxy_pool || {}, rate = data.rate || {};
    const badge = state.nodes.badge; badge.dataset.status = String(data.state || "unknown");
    badge.querySelector(".cs-status-label").textContent = statusLabel(data.state);
    state.nodes.metrics.replaceChildren();
    appendMetric(state.nodes.metrics, "Profiles", count(counts.profiles), "Observed listings");
    appendMetric(state.nodes.metrics, "Calendars", count(counts.calendars), `${count(counts.calendar_rows)} recorded date rows`);
    appendMetric(state.nodes.metrics, "Daily prices", count(counts.daily_prices), "Saved daily price observations");
    appendMetric(state.nodes.metrics, "Validated this hour", count(rate.validated_last_hour), `Configured ceiling ${count(rate.configured_hourly_limit)} · provider capacity not measured`);
    const quality = data.provider_proxy_quality || {};
    appendMetric(state.nodes.metrics, "Proxy pool", `${count(pool.distinct_ipv4)} neutral-tested IPv4s`, `${quality.fresh ? count(quality.validated_ipv4) : "Unknown"} recently Airbnb-validated · ${count(pool.healthy)} endpoints`);
    renderProgress(progress, data);
    renderDrawer(data);
    state.nodes.refresh.disabled = state.busy;
    state.nodes.refresh.textContent = state.busy ? "Requesting refresh…" : "Refresh Dubai";
  }

  function renderProgress(progress, data) {
    const completed = Number(progress.completed), total = Number(progress.total), quarantined = Number(progress.quarantined || 0);
    const known = Number.isFinite(completed) && Number.isFinite(total) && total > 0;
    const percent = known ? Math.max(0, Math.min(100, Math.round(completed / total * 100))) : 0;
    const bar = node("div", "cs-progress-track"); bar.setAttribute("role", "progressbar"); bar.setAttribute("aria-label", "Collection job progress");
    bar.setAttribute("aria-valuemin", "0"); bar.setAttribute("aria-valuemax", "100"); bar.setAttribute("aria-valuenow", String(percent));
    const fill = node("span", "cs-progress-fill"); fill.style.width = `${percent}%`; bar.appendChild(fill);
    const row = node("div", "cs-progress-row");
    add(row, node("strong", "", known ? `${count(completed)} of ${count(total)} complete` : "Progress not reported"), node("span", "", `${count(quarantined)} quarantined · updated ${stamp(data.updated_at)}`));
    const refresh = data.refresh || {};
    const message = node("p", "cs-progress-message", value(refresh.message || data.message, "No collection is running."));
    const refreshState = refresh.state ? ` · refresh ${statusLabel(refresh.state)}` : "";
    state.nodes.progress.replaceChildren(add(node("div", "cs-progress-top"), node("div", "", "Current collection"), node("span", "", `${statusLabel(data.state)}${data.process_alive === true ? " · worker active" : ""}${refreshState}`)), row, bar, message);
  }

  function renderDrawer(data) {
    const drawer = state.nodes.drawer; drawer.replaceChildren();
    const rate = data.rate || {}, proxy = data.proxy_pool || {};
    const facts = node("div", "cs-drawer-facts");
    add(facts, node("p", "", `Last updated: ${stamp(data.updated_at)}`), node("p", "", `Worker process: ${data.process_alive === true ? "active" : data.process_alive === false ? "not active" : "unknown"}`), node("p", "", `Proxy pool: ${count(proxy.healthy)} healthy · ${count(proxy.distinct_ipv4)} distinct IPv4s`), node("p", "", `Configured hourly limit: ${count(rate.configured_hourly_limit)} · measured provider limit: ${value(rate.measured_provider_limit, "Not measured")}`));
    const quality = data.provider_proxy_quality || {};
    facts.appendChild(node("p", "", `Recently Airbnb-validated IPv4s: ${quality.fresh ? count(quality.validated_ipv4) : "Unknown or stale"} · useful collection requests provide validation; no separate test traffic.`));
    drawer.appendChild(facts);
    appendCollectionList(drawer, "Sources", data.sources, item => `${value(item.name)} · ${statusLabel(item.state)}${item.note ? ` — ${String(item.note)}` : ""}`);
    appendCollectionList(drawer, "Recorded errors", data.errors, item => `${stamp(item.at)} · ${value(item.listing_id)} · ${value(item.kind)} · ${statusLabel(item.category)} · ${statusLabel(item.state)}${item.reason ? ` · ${String(item.reason).slice(0, 180)}` : ""}`);
    appendCollectionList(drawer, "Repair history", data.repairs, item => `${statusLabel(item.state)} · ${value(item.model, "Model unknown")} · ${repairSummary(item.summary)}${item.started_at ? ` · ${stamp(item.started_at)}` : ""}${item.finished_at ? `–${stamp(item.finished_at)}` : ""}`);
  }

  function repairSummary(value_) {
    const summary = String(value_ || "No summary");
    if (/[A-Za-z]:[\\/]|\\\\|\/(?:[A-Za-z0-9_.-]+\/){2,}/.test(summary)) return "Repair details omitted from dashboard view.";
    return summary.slice(0, 180);
  }

  function appendCollectionList(parent, title, entries, label) {
    const section = node("section", "cs-drawer-section"); section.appendChild(node("h4", "", `${title} (${Array.isArray(entries) ? entries.length : 0})`));
    const list = node("ul", "");
    if (!Array.isArray(entries) || entries.length === 0) list.appendChild(node("li", "cs-muted", `No ${title.toLowerCase()} recorded.`));
    else for (const entry of entries) list.appendChild(node("li", "", label(entry)));
    add(section, list); parent.appendChild(section);
  }

  function debounceListings() {
    window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(() => { loadListings(); loadMapPoints(true); }, 250);
  }
  function cancelMapLoad() {
    state.mapGeneration += 1;
    if (state.mapController) state.mapController.abort();
  }
  async function loadMapPoints(fitAfterLoad = false) {
    if (!activeTab() || !state.map) return;
    const generation = ++state.mapGeneration;
    const query = state.query, bedrooms = state.bedrooms;
    const gathered = [];
    let offset = 0, total = 0, mappedTotal = 0, unmappedTotal = 0, revision;
    let firstPage = true;
    state.nodes.mapMeta.textContent = "Loading all matching saved locations…";
    try {
      while (true) {
        const params = new URLSearchParams({ offset: String(offset), limit: "2000", query, bedrooms });
        const result = await jsonFetch(`/api/collection/map?${params}`, {}, "mapController");
        if (generation !== state.mapGeneration) return;
        if (firstPage) {
          total = Number(result.total) || 0;
          mappedTotal = Number(result.mapped_total) || 0;
          unmappedTotal = Number(result.unmapped_total) || 0;
          revision = result.revision;
          firstPage = false;
        } else if (result.revision !== revision || Number(result.total) !== total || Number(result.mapped_total) !== mappedTotal || Number(result.unmapped_total) !== unmappedTotal) {
          throw new Error("Saved locations changed between map pages. Keeping the previous map until the next refresh.");
        }
        const points = Array.isArray(result.points) ? result.points : [];
        gathered.push(...points);
        if (result.next_offset === null || result.next_offset === undefined) break;
        const nextOffset = Number(result.next_offset);
        if (!Number.isFinite(nextOffset) || nextOffset <= offset) throw new Error("Map paging returned an invalid next offset. Keeping the previous map.");
        offset = nextOffset;
      }
      if (generation !== state.mapGeneration) return;
      const ids = new Set(gathered.map(point => String(point.listing_id)));
      if (ids.size !== gathered.length) throw new Error("Map pages contained duplicate listing IDs. Keeping the previous map.");
      if (gathered.length !== mappedTotal) throw new Error(`Map paging returned ${count(gathered.length)} of ${count(mappedTotal)} mapped listings. Keeping the previous map.`);
      state.mapPoints = gathered;
      state.mapRevision = revision;
      state.mapTotals = { total, mapped: mappedTotal, unmapped: unmappedTotal };
      renderMapPoints(fitAfterLoad);
    } catch (error) {
      if (error.name === "AbortError" || generation !== state.mapGeneration) return;
      state.nodes.mapMeta.textContent = `Map locations unavailable: ${error.message} · saved library remains available`;
      notify("Map locations could not refresh. The saved listing library remains available.", "error");
    }
  }

  function renderMapPoints(fitAfterLoad = false) {
    if (!state.map) return;
    state.markers.forEach(marker => marker.remove()); state.markers = [];
    const points = state.mapPoints || [], bounds = [];
    const totals = state.mapTotals || { total: points.length, mapped: points.length, unmapped: 0 };
    for (const point of points) {
      const lat = Number(point.latitude), lng = Number(point.longitude);
      if (!Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat) > 90 || Math.abs(lng) > 180) continue;
      const row = { ...point, person_capacity: point.guest_capacity };
      const marker = window.L.circleMarker([lat, lng], {
        radius: 6, weight: 1.5, color: "#125e56", fillColor: "#32a591", fillOpacity: .88,
        renderer: state.canvasRenderer || undefined,
      });
      marker.bindPopup(mapPopup(row), { maxWidth: 280 });
      marker.addTo(state.map); state.markers.push(marker); bounds.push([lat, lng]);
    }
    state.nodes.mapMeta.textContent = `${count(totals.mapped)} of ${count(totals.total)} matching listings mapped · ${count(totals.unmapped)} missing locations`;
    if (fitAfterLoad && bounds.length) state.map.fitBounds(bounds, { padding: [24, 24], maxZoom: 13 });
    else if (fitAfterLoad && !bounds.length) state.map.setView([25.2048, 55.2708], 10);
  }

  function mapPopup(row) {
    const content = node("div", "cs-map-popup");
    const title = value(row.title, `Listing ${row.listing_id}`);
    const bedroomText = row.bedrooms === null || row.bedrooms === undefined || row.bedrooms === ""
      ? "Bedrooms unknown"
      : Number(row.bedrooms) === 0 ? "Studio" : `${row.bedrooms} bedroom${Number(row.bedrooms) === 1 ? "" : "s"}`;
    content.appendChild(node("strong", "", title));
    content.appendChild(node("span", "", bedroomText));
    const actions = node("div", "cs-map-popup-actions");
    add(actions,
      button("Open calendar", "cs-map-popup-button", () => selectListing(row), `Open calendar for ${title}`),
      button("Listing details", "cs-map-popup-button is-secondary", () => showProfile(row), `Show full profile for ${title}`));
    content.appendChild(actions);
    return content;
  }

  function fitMapResults() {
    if (!state.map) return;
    const bounds = state.markers.map(marker => marker.getLatLng());
    if (bounds.length) state.map.fitBounds(bounds, { padding: [24, 24], maxZoom: 13 });
    else state.map.setView([25.2048, 55.2708], 10);
  }

  async function loadListings(keepPage = false) {
    if (!activeTab()) return;
    if (!keepPage) state.calendar = null;
    const params = new URLSearchParams({ offset: String(state.offset), limit: "50", query: state.query, bedrooms: state.bedrooms });
    try {
      const result = await jsonFetch(`/api/collection/listings?${params}`, {}, "listingsController");
      state.rows = Array.isArray(result.listings) ? result.listings : [];
      state.total = Number.isFinite(Number(result.total)) ? Number(result.total) : 0;
      state.listingRevision = result.revision ?? state.listingRevision;
      state.offset = Math.max(0, Number(state.offset) || 0);
      renderListings();
      if (state.selected && !state.rows.some(row => String(row.listing_id) === String(state.selected.listing_id))) {
        if (!keepPage) state.selected = null;
      }
    } catch (error) {
      if (error.name === "AbortError") return;
      state.nodes.list.replaceChildren(node("p", "cs-empty", `Listings are unavailable: ${error.message}`));
      notify("The library could not refresh. Existing records remain on the page until a successful response.", "error");
    }
  }

  function renderListings() {
    const { list, previous, next, pageLabel, libraryMeta } = state.nodes;
    list.replaceChildren(); (state.nodes.markers || []).forEach(marker => marker.remove()); state.nodes.markers = [];
    libraryMeta.textContent = state.total ? `${count(state.total)} observed · ${count(state.offset + 1)}–${count(Math.min(state.offset + state.rows.length, state.total))}` : "No observed listings match this view";
    pageLabel.textContent = `Page ${Math.floor(state.offset / 50) + 1} · ${Math.ceil(state.total / 50) || 1}`;
    previous.disabled = state.offset === 0; next.disabled = state.offset + 50 >= state.total;
    if (!state.rows.length) list.appendChild(node("p", "cs-empty", state.total ? "No listings on this page." : "No observed listings match these filters yet."));
    else for (const row of state.rows) list.appendChild(listingCard(row));
  }

  function listingCard(row) {
    const selected = state.selected && String(state.selected.listing_id) === String(row.listing_id);
    const item = node("article", `cs-listing${selected ? " is-selected" : ""}`);
    const hasBedrooms = row.bedrooms !== null && row.bedrooms !== undefined && row.bedrooms !== "" && Number.isFinite(Number(row.bedrooms));
    const hasBeds = row.beds !== null && row.beds !== undefined && row.beds !== "" && Number.isFinite(Number(row.beds));
    const bedrooms = hasBedrooms ? Number(row.bedrooms) === 0 ? "Studio" : `${row.bedrooms} bedroom${Number(row.bedrooms) === 1 ? "" : "s"}` : "Bedrooms unknown";
    const beds = hasBeds ? `${row.beds} bed${Number(row.beds) === 1 ? "" : "s"}` : "Beds unknown";
    const instant = row.fields && row.fields.instant_book || null;
    const instantValue = instant && instant.status === "observed" ? instant.value === true ? "yes" : instant.value === false ? "no" : "unknown" : row.instant_book === true ? "yes" : row.instant_book === false ? "no" : "unknown";
    const facts = [bedrooms, beds, `${value(row.person_capacity, "Unknown capacity")} guests`, value(row.room_type || row.property_type, "Property type unknown"), `Instant Book profile signal · ${instantValue}`];
    const actions = node("div", "cs-listing-actions");
    const open = button("Open calendar →", "cs-open-listing", () => selectListing(row), `Open calendar for ${value(row.title, row.listing_id)}`);
    const profile = button("Listing details", "cs-profile-button", () => showProfile(row), `Show full profile for ${value(row.title, row.listing_id)}`);
    add(actions, open, profile);
    add(item, node("h4", "", value(row.title, `Listing ${row.listing_id}`)), node("p", "cs-listing-id", `ID ${value(row.listing_id)} · ${stamp(row.observed_at)}`), node("p", "cs-listing-facts", facts.join(" · ")), actions);
    item.addEventListener("click", event => { if (event.target === item || event.target.tagName === "H4") selectListing(row); });
    return item;
  }

  function humanize(name) {
    return String(name).replace(/([a-z0-9])([A-Z])/g, "$1 $2").replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim().replace(/^./, character => character.toUpperCase());
  }

  function showProfileValue(parent, name, value_) {
    const row = node("div", "cs-profile-field");
    row.appendChild(node("dt", "", humanize(name)));
    const dd = node("dd", "");
    if (name === "photo_urls" && Array.isArray(value_)) {
      if (!value_.length) dd.textContent = "Unknown";
      for (const raw of value_) {
        let url;
        try { url = new URL(String(raw)); } catch (_) { continue; }
        if (!(["https:", "http:"].includes(url.protocol))) continue;
        const link = node("a", "cs-photo-link", url.href); link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer";
        dd.appendChild(link);
      }
      if (!dd.childNodes.length) dd.textContent = "Unknown";
    } else if (value_ === null || value_ === undefined || value_ === "") {
      dd.textContent = "Unknown";
    } else if (Array.isArray(value_)) {
      if (!value_.length) dd.textContent = "Unknown";
      else {
        const list = node("ul", "cs-profile-list");
        for (const entry of value_) list.appendChild(node("li", "", readable(entry)));
        dd.appendChild(list);
      }
    } else {
      dd.textContent = readable(value_);
      if (typeof value_ === "object") dd.classList.add("is-structured");
    }
    row.appendChild(dd); parent.appendChild(row);
  }

  function readable(value_) {
    if (value_ === null || value_ === undefined || value_ === "") return "Unknown";
    if (Array.isArray(value_)) return value_.map(readable).join(" · ") || "Unknown";
    if (typeof value_ === "object") return JSON.stringify(value_, null, 2);
    return String(value_);
  }

  async function showProfile(row) {
    const dialog = state.nodes.profileDialog, content = state.nodes.profileContent;
    content.replaceChildren(node("p", "cs-empty", "Loading saved profile…"));
    if (!dialog.open) dialog.showModal();
    const params = new URLSearchParams({ listing_id: String(row.listing_id) });
    try {
      const profile = await jsonFetch(`/api/collection/profile?${params}`, {}, "profileController");
      content.replaceChildren();
      content.appendChild(node("p", "cs-profile-observed", `Profile observed ${stamp(profile.observed_at)} · Listing ${value(profile.listing_id, row.listing_id)}`));
      const context = profile.context && typeof profile.context === "object" ? profile.context : {};
      const contextSection = node("section", "cs-profile-section");
      contextSection.appendChild(node("h4", "", "Instant Book profile observation context"));
      contextSection.appendChild(node("p", "cs-profile-context", `Observed stay context: check-in ${value(context.check_in, "Unknown")}, check-out ${value(context.check_out, "Unknown")}; ${value(context.adults, "Unknown")} adults, ${value(context.children, "Unknown")} children; currency ${value(context.currency, "Unknown")}. This is a profile signal, not a dated booking guarantee.`));
      content.appendChild(contextSection);
      const fields = profile.fields && typeof profile.fields === "object" ? profile.fields : {};
      const fieldSection = node("section", "cs-profile-section"); fieldSection.appendChild(node("h4", "", "Observed profile fields"));
      const list = node("dl", "cs-profile-fields");
      const entries = Object.entries(fields);
      if (!entries.length) fieldSection.appendChild(node("p", "cs-empty", "Profile fields are unknown."));
      for (const [name, field] of entries) {
        const observed = field && typeof field === "object" && field.status === "observed";
        showProfileValue(list, name, observed ? field.value : null);
      }
      if (entries.length) fieldSection.appendChild(list);
      content.appendChild(fieldSection);
    } catch (error) {
      if (error.name === "AbortError") return;
      content.replaceChildren(node("p", "cs-empty", `Profile details are unavailable: ${error.message}`));
    }
  }

  async function selectListing(row) {
    state.selected = row; state.calendar = null; state.calendarStart = today();
    renderListings();
    await loadCalendar();
  }

  function addDays(start, days) {
    const date = new Date(`${start}T12:00:00Z`); date.setUTCDate(date.getUTCDate() + days);
    return date.toISOString().slice(0, 10);
  }
  function moveCalendar(days) { state.calendarStart = addDays(state.calendarStart, days); loadCalendar(); }
  async function loadCalendar() {
    if (!state.selected || !activeTab()) return;
    const params = new URLSearchParams({ listing_id: String(state.selected.listing_id), start: state.calendarStart, days: "31" });
    try {
      state.calendar = await jsonFetch(`/api/collection/calendar?${params}`, {}, "calendarController");
      renderCalendar();
    } catch (error) {
      if (error.name === "AbortError") return;
      state.nodes.calendar.replaceChildren(node("p", "cs-empty", `Calendar is unavailable: ${error.message}`));
    }
  }

  function renderCalendar() {
    const region = state.nodes.calendar, data = state.calendar;
    region.replaceChildren();
    if (!state.selected) {
      state.nodes.calendarMeta.textContent = "Choose a listing to inspect dates";
      region.appendChild(node("p", "cs-empty", "Select a listing or a map point to load its next 31 observed dates.")); return;
    }
    state.nodes.calendarMeta.textContent = `${value(state.selected.title, `Listing ${state.selected.listing_id}`)} · ${data ? `${data.dates?.length || 0} days` : "Loading dates…"}`;
    if (!data) { region.appendChild(node("p", "cs-empty", "Loading calendar evidence…")); return; }
    if (data.context) region.appendChild(node("p", "cs-calendar-context", contextLabel(data.context)));
    const rows = Array.isArray(data.dates) ? data.dates : [];
    if (!rows.length) { region.appendChild(node("p", "cs-empty", "No dates were returned for this listing.")); return; }
    const grid = node("div", "cs-calendar-grid");
    for (const day of rows) grid.appendChild(calendarDay(day, data.context || {}));
    region.appendChild(grid);
  }

  function contextLabel(context) {
    const party = context.party && typeof context.party === "object" ? context.party : {};
    const hasAdults = party.adults !== null && party.adults !== undefined;
    const hasChildren = party.children !== null && party.children !== undefined;
    const partyLabel = hasAdults || hasChildren
      ? `${hasAdults ? party.adults : "Adults unknown"} adults · ${hasChildren ? party.children : "Children unknown"} children`
      : "Guest party unknown";
    return `Source ${statusLabel(context.source_kind || "unknown")} · ${value(context.currency, "Currency unknown")} · ${partyLabel} · observed ${stamp(context.observed_at)}. A date with no evidence remains unknown.`;
  }
  function calendarDay(day, context) {
    const card = node("article", "cs-day");
    const status = day.available === true ? "Available" : day.available === false ? "Unavailable" : "Availability unknown";
    card.dataset.available = day.available === true ? "yes" : day.available === false ? "no" : "unknown";
    card.setAttribute("aria-label", `${value(day.date)}. ${status}. Check-in ${stateLabel(day.available_for_checkin)}. Check-out ${stateLabel(day.available_for_checkout)}. ${day.bookable === true ? "Bookable" : day.bookable === false ? "Not bookable" : "Bookability unknown"}. ${day.nightly_price === null || day.nightly_price === undefined ? "Price unknown" : `Nightly price ${value(context.currency, "Currency unknown")} ${day.nightly_price}`}.`);
    const date = new Date(`${value(day.date, "Invalid")}T12:00:00Z`);
    const dateLabel = Number.isNaN(date.getTime()) ? value(day.date) : date.toLocaleDateString([], { timeZone: "UTC", weekday: "short", day: "numeric", month: "short" });
    add(card, node("span", "cs-day-date", dateLabel), indicator(status, day.available), restriction("In", day.available_for_checkin), restriction("Out", day.available_for_checkout), node("span", "cs-stay", stayRange(day)), node("strong", "cs-price", day.nightly_price === null || day.nightly_price === undefined ? "Price unknown" : `${value(context.currency, "Currency unknown")} ${value(day.nightly_price)}`));
    return card;
  }
  function stateLabel(value_) { return value_ === true ? "allowed" : value_ === false ? "restricted" : "unknown"; }
  function indicator(label, available) {
    const item = node("span", `cs-indicator ${available === true ? "is-yes" : available === false ? "is-no" : "is-unknown"}`);
    item.setAttribute("aria-label", label);
    item.append(node("i", "", available === true ? "✓" : available === false ? "×" : "?"), node("span", "", label)); return item;
  }
  function restriction(label, allowed) {
    const stateLabel_ = allowed === true ? "allowed" : allowed === false ? "restricted" : "unknown";
    const item = node("span", `cs-restriction ${allowed === false ? "is-restricted" : allowed === true ? "is-allowed" : "is-unknown"}`);
    item.setAttribute("aria-label", `${label} ${stateLabel_}`);
    add(item, node("i", "", allowed === true ? "✓" : allowed === false ? "!" : "?"), node("span", "", label)); return item;
  }
  function stayRange(day) {
    if (day.min_nights === null && day.max_nights === null || day.min_nights === undefined && day.max_nights === undefined) return "Stay length unknown";
    if (day.min_nights !== null && day.min_nights !== undefined && day.max_nights !== null && day.max_nights !== undefined) return `${day.min_nights}–${day.max_nights} nights`;
    if (day.min_nights !== null && day.min_nights !== undefined) return `Min ${day.min_nights} nights`;
    return `Max ${value(day.max_nights)} nights`;
  }

  async function startRefresh() {
    if (state.busy) return;
    state.busy = true; if (state.status) renderStatus();
    try {
      const allowed = state.sessionReady ? await state.sessionReady : state.ownerSession;
      if (!allowed || !state.ownerSession) {
        const help = root.querySelector("[data-owner-help]");
        if (help) help.textContent = "Refresh requires the owner link. Open the dashboard using that link to enable collection.";
        notify("Owner access is required to refresh collection. Open the owner link, then try again.", "error");
        return;
      }
      notify("Sending one refresh request to the active collection worker…");
      const result = await jsonFetch("/api/collection/refresh", { method: "POST", headers: { "Content-Type": "application/json", "X-CompSet-Request": "dashboard-v1" }, body: JSON.stringify({ dataset: "dubai" }) });
      notify(value(result.message, `Refresh ${statusLabel(result.state)}.`), result.state === "failed" ? "error" : "success");
      await loadStatus(); await loadListings(true);
    } catch (error) {
      if (error.status === 401) {
        state.ownerSession = false;
        const help = root.querySelector("[data-owner-help]");
        if (help) help.textContent = "Refresh requires the owner link. Open the dashboard using that link to enable collection.";
        notify("Owner access is required to refresh collection. Open the owner link, then try again.", "error");
      } else notify(`Refresh could not be requested: ${error.message}`, "error");
    }
    finally { state.busy = false; if (state.status) renderStatus(); }
  }

  mount();
})();
