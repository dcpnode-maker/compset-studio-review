"use strict";

/* Two saved-evidence workspaces. Collection remains owned by CompSetRates. */
(function (global) {
  const rates = global.CompSetRates || (typeof require === "function" ? require("./rates-workspace.js") : null);
  const shared = rates && rates.model;
  const array = value => Array.isArray(value) ? value : [];
  const present = value => value !== null && value !== undefined && value !== "";
  const text = (value, fallback = "Unknown") => present(value) ? String(value) : fallback;
  const human = value => text(value).replace(/_/g, " ");
  const STATES = ["quoted", "indicative", "unavailable", "restricted", "unknown"];
  const LABELS = { quoted: "Exact quote", indicative: "Indicative", unavailable: "Unavailable", restricted: "Stay restricted", unknown: "Unknown" };
  const SOURCES = { bnbme_direct: "BnBMe website", airbnb: "Airbnb", google_hotels: "Google Hotels", agoda: "Agoda", booking: "Booking.com", expedia: "Expedia", makemytrip: "MakeMyTrip" };
  const sourceName = value => SOURCES[value] || human(value);
  const summarize = value => Array.isArray(value) ? value.map(summarize).join(" · ") : value && typeof value === "object" ? Object.entries(value).map(([k, v]) => `${human(k)}: ${summarize(v)}`).join(" · ") : value === true ? "Yes" : value === false ? "No" : text(value);

  function isoDate(value) {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
    const parsed = new Date(`${value}T12:00:00Z`);
    return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value ? value : null;
  }
  function addDays(value, count) {
    if (!isoDate(value) || !Number.isInteger(count)) return null;
    const parsed = new Date(`${value}T12:00:00Z`); parsed.setUTCDate(parsed.getUTCDate() + count);
    return parsed.toISOString().slice(0, 10);
  }
  function dateLabel(value, full = false) {
    return isoDate(value) ? new Date(`${value}T12:00:00Z`).toLocaleDateString("en-GB", { timeZone: "UTC", day: "numeric", month: "short", ...(full ? { year: "numeric" } : {}) }) : text(value);
  }
  function amount(value) { return typeof value === "string" && /^\d+(?:\.\d+)?$/.test(value) && /[1-9]/.test(value) ? value : null; }
  function stateOf(cell) {
    if (cell.availability === "unavailable") return "unavailable";
    return STATES.includes(cell.state) ? cell.state : "unknown";
  }
  function priceLabel(cell) {
    const status = stateOf(cell);
    if (status === "unavailable") return LABELS[status];
    if (["quoted", "indicative", "restricted"].includes(status)) {
      if (amount(cell.amount)) return `${text(cell.currency, "")} ${cell.amount}`.trim();
      if (present(cell.display_amount)) return String(cell.display_amount);
    }
    if (status === "restricted") return LABELS[status];
    return cell.availability === "available" ? "Available · price unknown" : "Unknown";
  }
  function calendarQuery(options) {
    if (!isoDate(options.start)) throw new TypeError("Choose a valid saved calendar date.");
    const query = new URLSearchParams({ start: options.start, days: String(options.days || 14), offset: String(options.offset || 0), limit: "25" });
    for (const key of ["city", "currency", "namespace", "query", "bedrooms"]) if (present(options[key]) && options[key] !== "all") query.set(key, String(options[key]));
    if (options.namespace === "all") query.set("namespace", "all");
    return `/api/intelligence/str/calendar?${query}`;
  }
  function calendarView(payload, options = {}) {
    const dates = array(payload.dates).filter(isoDate);
    const index = new Map();
    for (const cell of array(payload.cells)) {
      const key = `${cell.entity_id}\0${cell.date}`;
      if (index.has(key)) index.set(key, { entity_id: cell.entity_id, date: cell.date, state: "unknown", amount: null, reason: "duplicate_saved_cell", offers: [] });
      else index.set(key, cell);
    }
    const wantedDates = options.day && dates.includes(options.day) ? [options.day] : dates;
    return array(payload.entities).map(entity => ({ entity, cells: wantedDates.map(date => {
      const cell = index.get(`${entity.id}\0${date}`) || { entity_id: entity.id, date, state: "unknown", amount: null, currency: entity.currency, reason: "not_observed", offers: [] };
      if (entity.currency && cell.currency && entity.currency !== cell.currency) return { entity_id: entity.id, date, state: "unknown", amount: null, currency: entity.currency, reason: "currency_context_mismatch", offers: [] };
      return cell;
    }) })).filter(row => !options.evidence || options.evidence === "all" || row.cells.some(cell => stateOf(cell) === options.evidence));
  }
  function filteredOfferCell(cell, filters = {}) {
    const active = ["room", "meal", "cancellation"].some(key => filters[key] && filters[key] !== "all");
    if (!active) return cell;
    const offers = array(cell.offers).filter(offer => (!filters.room || filters.room === "all" || offer.room_name === filters.room)
      && (!filters.meal || filters.meal === "all" || summarize(offer.meals) === filters.meal)
      && (!filters.cancellation || filters.cancellation === "all" || summarize(offer.cancellation || offer.cancellation_terms) === filters.cancellation));
    // Conditions may carry different price bases. Show the matching offers without inventing parity.
    return { ...cell, state: offers.length ? "indicative" : "unknown", availability: "unknown", amount: null,
      display_amount: offers.length ? `${offers.length} matching offer${offers.length === 1 ? "" : "s"}` : null,
      amount_basis: offers.length ? "inspect_matching_offer_conditions" : null, reason: offers.length ? "saved_offer_filter" : "no_matching_saved_offer", offers };
  }
  function hotelView(dataset, options = {}) {
    const entities = array(dataset.entities).filter(entity => !options.source || options.source === "all" || entity.source === options.source);
    const filtered = { ...dataset, entities, cells: array(dataset.cells).map(cell => filteredOfferCell(cell, options)) };
    return calendarView(filtered, { ...options, day: null });
  }
  function exportRows(rows, context) {
    const fields = ["entity_id", "property_or_source", "observation_source", "date", "checkout", "state", "availability", "amount", "display_amount", "currency", "amount_basis", "precision", "observed_at", "reason", "source_url", "context", "offers"];
    const csv = [fields];
    for (const { entity, cells } of rows) for (const cell of cells) csv.push([entity.id, entity.label || entity.title, entity.source,
      cell.date, cell.checkout, stateOf(cell), cell.availability, ["quoted", "indicative"].includes(stateOf(cell)) ? amount(cell.amount) : null,
      ["quoted", "indicative"].includes(stateOf(cell)) ? cell.display_amount : null, cell.currency, cell.amount_basis, cell.precision,
      cell.observed_at, cell.reason, shared.safeUrl(cell.source_url || entity.source_url), context || {}, array(cell.offers)]);
    return csv.map(row => row.map(shared.csvField).join(",")).join("\r\n");
  }
  function configuredGroup(payload, subjectId) {
    const unknown = status => ({ status, group: null, count: null, labels: [] });
    if (!payload || payload.status !== "observed_name_only") return unknown(payload && payload.status === "read_error" ? "read_error" : "not_observed");
    const groups = array(payload.groups).filter(group => group && group.subject_id === subjectId);
    if (!groups.length) return unknown("not_observed");
    const group = groups[0];
    if (groups.length !== 1 || group.identity_status !== "name_only_unresolved" || !Array.isArray(group.competitor_labels)
      || group.competitor_labels.some(label => typeof label !== "string" || !label.trim() || label.length > 250)) return unknown("read_error");
    return { status: "observed_name_only", group, count: group.competitor_labels.length, labels: group.competitor_labels };
  }
  function configuredCsv(profile, payload) {
    const evidence = configuredGroup(payload, profile.id), group = evidence.group || {};
    const fields = ["subject_id", "subject_title", "competitor_label", "observation_status", "identity_status", "rate_status", "observed_at", "source_url"];
    const rows = evidence.labels.length ? evidence.labels : [""];
    return [fields, ...rows.map(label => [profile.id, profile.title || profile.name, label, evidence.status,
      group.identity_status || "unknown", "not_collected", group.observed_at, shared.safeUrl(group.source_url)])]
      .map(row => row.map(shared.csvField).join(",")).join("\r\n");
  }
  function distanceKm(a, b) {
    const values = [a && a.latitude, a && a.longitude, b && b.latitude, b && b.longitude];
    if (values.some(v => typeof v !== "number" || !Number.isFinite(v)) || Math.abs(values[0]) > 90 || Math.abs(values[2]) > 90 || Math.abs(values[1]) > 180 || Math.abs(values[3]) > 180) return null;
    const [lat1, lng1, lat2, lng2] = values.map(v => v * Math.PI / 180);
    const h = Math.sin((lat2 - lat1) / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin((lng2 - lng1) / 2) ** 2;
    return 6371 * 2 * Math.asin(Math.sqrt(Math.min(1, h)));
  }
  function mapCandidates(payload, center, radius) {
    if (typeof radius !== "number" || !Number.isFinite(radius) || radius < 0) return [];
    return array(payload.candidates).map(candidate => ({ ...candidate, view_distance_km: distanceKm(center, candidate) }))
      .filter(candidate => candidate.view_distance_km !== null && candidate.view_distance_km <= radius);
  }
  function polygonAreaKm2(vertices) {
    if (!Array.isArray(vertices) || vertices.length < 3 || vertices.some(point => distanceKm(point, point) === null)) return 0;
    const lat0 = vertices.reduce((sum, point) => sum + point.latitude, 0) / vertices.length * Math.PI / 180;
    const xy = vertices.map(point => [point.longitude * Math.PI / 180 * 6371 * Math.cos(lat0), point.latitude * Math.PI / 180 * 6371]);
    return Math.abs(xy.reduce((sum, point, index) => { const next = xy[(index + 1) % xy.length]; return sum + point[0] * next[1] - next[0] * point[1]; }, 0)) / 2;
  }
  function validPolygon(vertices) {
    if (!Array.isArray(vertices) || vertices.length < 3 || vertices.length > 64 || polygonAreaKm2(vertices) < .000001) return false;
    const orientation = (a, b, c) => (b.longitude - a.longitude) * (c.latitude - a.latitude) - (b.latitude - a.latitude) * (c.longitude - a.longitude);
    const between = (a, b, c) => c.longitude >= Math.min(a.longitude, b.longitude) - 1e-12 && c.longitude <= Math.max(a.longitude, b.longitude) + 1e-12 && c.latitude >= Math.min(a.latitude, b.latitude) - 1e-12 && c.latitude <= Math.max(a.latitude, b.latitude) + 1e-12;
    const intersects = (a, b, c, d) => { const abC = orientation(a, b, c), abD = orientation(a, b, d), cdA = orientation(c, d, a), cdB = orientation(c, d, b); return abC * abD < 0 && cdA * cdB < 0 || Math.abs(abC) < 1e-12 && between(a, b, c) || Math.abs(abD) < 1e-12 && between(a, b, d) || Math.abs(cdA) < 1e-12 && between(c, d, a) || Math.abs(cdB) < 1e-12 && between(c, d, b); };
    for (let i = 0; i < vertices.length; i++) {
      if (distanceKm(vertices[i], vertices[(i + 1) % vertices.length]) < .001) return false;
      for (let j = i + 1; j < vertices.length; j++) {
        if (j === i + 1 || i === 0 && j === vertices.length - 1) continue;
        if (intersects(vertices[i], vertices[(i + 1) % vertices.length], vertices[j], vertices[(j + 1) % vertices.length])) return false;
      }
    }
    return true;
  }
  function pointInPolygon(point, vertices) {
    if (distanceKm(point, point) === null || !Array.isArray(vertices) || vertices.length < 3 || polygonAreaKm2(vertices) < .000001) return false;
    let inside = false;
    for (let i = 0, j = vertices.length - 1; i < vertices.length; j = i++) {
      const a = vertices[i], b = vertices[j], cross = (point.longitude - a.longitude) * (b.latitude - a.latitude) - (point.latitude - a.latitude) * (b.longitude - a.longitude);
      if (Math.abs(cross) < 1e-9 && point.longitude >= Math.min(a.longitude, b.longitude) - 1e-9 && point.longitude <= Math.max(a.longitude, b.longitude) + 1e-9 && point.latitude >= Math.min(a.latitude, b.latitude) - 1e-9 && point.latitude <= Math.max(a.latitude, b.latitude) + 1e-9) return true;
      if ((a.latitude > point.latitude) !== (b.latitude > point.latitude) && point.longitude < (b.longitude - a.longitude) * (point.latitude - a.latitude) / (b.latitude - a.latitude) + a.longitude) inside = !inside;
    }
    return inside;
  }
  function polygonCandidates(payload, vertices) {
    return array(payload.candidates).filter(candidate => pointInPolygon(candidate, vertices));
  }

  const MIN_RADIUS_KM = .1, MAX_RADIUS_KM = 50;
  function boundedRadius(value) {
    const radius = typeof value === "number" ? value : typeof value === "string" && value.trim() ? Number(value) : NaN;
    return Number.isFinite(radius) ? Math.max(MIN_RADIUS_KM, Math.min(MAX_RADIUS_KM, radius)) : null;
  }
  function mapCenter(latlng) {
    const center = latlng && { latitude: latlng.lat, longitude: latlng.lng };
    return distanceKm(center, center) === null ? null : center;
  }
  function radiusEdge(center, radius) {
    const lat = center.latitude * Math.PI / 180, lng = center.longitude * Math.PI / 180, arc = radius / 6371;
    const edgeLat = Math.asin(Math.sin(lat) * Math.cos(arc));
    const edgeLng = lng + Math.atan2(Math.sin(arc) * Math.cos(lat), Math.cos(arc) - Math.sin(lat) * Math.sin(edgeLat));
    return [edgeLat * 180 / Math.PI, ((edgeLng * 180 / Math.PI + 540) % 360) - 180];
  }

  let active = null;
  function mount(root) {
    if (!root || typeof root.replaceChildren !== "function") throw new TypeError("A workspace root is required.");
    if (!shared) throw new Error("Load the shared rate workspace before the dual workspace.");
    if (active && active.root === root) return active.refresh();
    if (active) active.destroy();
    active = createController(root);
    return active.ready;
  }
  function createController(root) {
    const doc = root.ownerDocument || global.document;
    const state = { mode: "str", view: "calendar", summary: null, calendar: null, comparison: null, hotel: null,
      city: "all", currency: "all", namespace: "bnbme_direct", bedrooms: "all", query: "", evidence: "all",
      start: null, days: 14, offset: 0, day: null, subject: null, source: "all", room: "all", meal: "all", cancellation: "all",
      decision: "all", candidateQuery: "", candidatePage: 0, radius: 2, center: null, areaType: "circle", polygon: null, localExcluded: new Set(), hotelProfile: "aketa", hotelDay: null,
      hotelSearch: "", hotelSort: "date", hotelColumns: new Set(["room", "basis", "meal", "cancellation", "payment", "tax", "context", "observed"]), hotelEditor: null,
      loading: false, error: null };
    let alive = true, summarySequence = 0, viewSequence = 0, detailSequence = 0, searchTimer = null, bridge = null, map = null, mapView = null, lastFocus = null, readEpoch = 0, pendingFocusFallback = false;
    const mobileMedia = typeof global.matchMedia === "function" ? global.matchMedia("(max-width: 760px)") : { matches: false };
    const overlayMedia = typeof global.matchMedia === "function" ? global.matchMedia("(max-width: 1150px)") : { matches: false };
    const mobile = () => mobileMedia.matches;
    const cache = new Map();
    const pendingReads = new Map(), readOwners = new Map();
    const controls = new Map();
    const el = (tag, className, value) => { const n = doc.createElement(tag); if (className) n.className = className; if (value !== undefined) n.textContent = text(value, ""); return n; };
    const append = (node, ...children) => { children.filter(Boolean).forEach(c => node.appendChild(c)); return node; };
    const p = (value, className = "dw-muted") => el("p", className, value);
    const button = (label, fn, className = "dw-button") => { const n = el("button", className, label); n.type = "button"; n.addEventListener("click", fn); return n; };
    const icon = name => {
      const paths = { str: "M3 10 12 3l9 7M5 9v12h14V9M9 21v-8h6v8", hotel: "M5 21V3h14v18M3 21h18M9 7h1m4 0h1M9 11h1m4 0h1M10 21v-6h4v6", calendar: "M4 5h16v16H4zM8 3v4m8-4v4M4 10h16", compset: "M4 4h6v6H4zm10 0h6v6h-6zM4 14h6v6H4zm10 0h6v6h-6z", map: "m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2zM9 3v16m6-14v16", activity: "M3 12h4l3-8 4 16 3-8h4" };
      if (!doc.createElementNS) return el("span", "dw-icon", name === "str" ? "⌂" : name === "hotel" ? "▥" : name === "map" ? "⌖" : "▦");
      const svg = doc.createElementNS("http://www.w3.org/2000/svg", "svg"); svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("class", "dw-icon"); svg.setAttribute("aria-hidden", "true");
      const path = doc.createElementNS("http://www.w3.org/2000/svg", "path"); path.setAttribute("d", paths[name] || paths.calendar); svg.appendChild(path); return svg;
    };
    const link = (value, label) => { const url = shared.safeUrl(value); if (!url) return el("span", "", label); const n = el("a", "dw-link", label); n.href = url; n.target = "_blank"; n.rel = "noopener noreferrer"; return n; };
    const select = (label, values, value, fn) => { const n = el("select", "dw-select"); n.setAttribute("aria-label", label); controls.set(label, n); for (const [key, name] of values) { const o = el("option", "", name); o.value = key; n.appendChild(o); } n.value = value; n.addEventListener("change", () => fn(n.value)); return n; };
    const field = (label, control) => append(el("label", "dw-field"), el("span", "dw-label", label), control);
    const badge = (label, tone = "unknown") => el("span", `dw-state dw-state-${tone}`, label);
    const empty = message => p(message, "dw-empty");
    const facts = items => { const n = el("dl", "dw-facts"); for (const [key, value] of items) append(n, el("dt", "", key), el("dd", "", summarize(value))); return n; };
    const smallContext = context => shared.contextSummary(context || {});
    const stamp = value => shared.observedLabel(value);
    const currentHotel = () => state.hotel && (state.hotel.dataset || state.hotel.rates) || {};
    const hotelProfiles = () => array(state.summary && state.summary.hotel && state.summary.hotel.portfolio && state.summary.hotel.portfolio.profiles);
    const selectedHotelProfile = () => state.hotelProfile === "aketa" ? null : hotelProfiles().find(p => p.id === state.hotelProfile);
    const configuredLabels = () => state.hotel && state.hotel.portfolio && state.hotel.portfolio.configured_labels;
    const syncCollectionScope = () => { if (bridge) bridge.setDataset(state.mode === "hotel" ? selectedHotelProfile() ? null : "aketa" : "airbnb-compset"); };
    const allSubjects = () => array(state.summary && state.summary.str && state.summary.str.properties);
    const removeMap = () => { if (mapView && mapView.cleanup) mapView.cleanup(); if (map && typeof map.remove === "function") map.remove(); map = null; mapView = null; };
    root.className = "dw-root";
    const sidebar = el("aside", "dw-sidebar"), content = el("main", "dw-main"), navigation = el("nav", "dw-navigation"), bottomNav = el("nav", "dw-bottom-nav");
    sidebar.setAttribute("aria-label", "Workspace navigation"); bottomNav.setAttribute("aria-label", "Mobile workspace navigation");
    const modeNav = el("nav", "dw-mode-nav"); modeNav.setAttribute("aria-label", "Property type");
    const toolsButton = button("Collection tools →", () => { if (typeof global.CompSetOpenTools === "function") global.CompSetOpenTools(); else { state.error = "Collection tools need the updated application shell."; renderView(); } }, "dw-tools-link");
    append(sidebar, el("div", "dw-brand", "CompSet Studio"), modeNav, navigation, toolsButton, p("Local workspace\nSaved source evidence", "dw-sidebar-note"));
    const heading = el("header", "dw-heading"), toolbar = el("div", "dw-toolbar"), coverage = el("div", "dw-coverage"), alerts = el("div", "dw-alerts"), collection = el("section", "dw-collection"), layout = el("div", "dw-content-layout"), canvas = el("section", "dw-canvas"), inspector = el("aside", "dw-inspector");
    inspector.hidden = true; collection.setAttribute("aria-label", "Collection scope and progress"); alerts.setAttribute("aria-live", "polite");
    append(layout, canvas, inspector); append(content, heading, coverage, toolbar, alerts, layout, collection); root.replaceChildren(sidebar, content, bottomNav);

    const background = [sidebar, bottomNav, heading, coverage, toolbar, alerts, canvas, collection];
    function inside(parent, node) { for (let current = node; current; current = current.parentNode) if (current === parent) return true; return false; }
    function modalDetail() { return !inspector.hidden && overlayMedia.matches; }
    function syncDetailMode() {
      const modal = modalDetail(); inspector.setAttribute("aria-modal", String(modal));
      for (const node of background) { node.inert = modal; node.setAttribute("aria-hidden", String(modal)); }
    }
    function detailFocusables() {
      return Array.from(inspector.querySelectorAll("button, [href], input, select, textarea, [tabindex]")).filter(node => {
        if (node.disabled || node.hidden || node.getAttribute("tabindex") === "-1") return false;
        for (let parent = node; parent && parent !== inspector; parent = parent.parentNode) if (parent.hidden || parent.getAttribute("aria-hidden") === "true") return false;
        return typeof node.getClientRects !== "function" || node.getClientRects().length > 0;
      });
    }
    function closeDetail(focus = true) {
      if (!focus && !inspector.hidden && inside(inspector, doc.activeElement)) pendingFocusFallback = true;
      detailSequence++; cancelRead("detail"); inspector.hidden = true; inspector.replaceChildren(); layout.className = "dw-content-layout"; syncDetailMode();
      if (focus) { const target = lastFocus && lastFocus.isConnected ? lastFocus : heading.querySelectorAll("button")[0]; if (target) target.focus(); }
    }
    function detail(title, items, offers = [], extra = null) {
      if (inspector.hidden || !inside(inspector, doc.activeElement)) lastFocus = doc.activeElement;
      inspector.hidden = false; layout.className = "dw-content-layout dw-with-inspector";
      inspector.setAttribute("role", "dialog"); inspector.setAttribute("aria-label", title);
      const close = button("Close ×", () => closeDetail(), "dw-text-button");
      inspector.replaceChildren(append(el("div", "dw-inspector-heading"), el("h2", "", title), close), facts(items));
      if (offers.length) {
        inspector.appendChild(el("h3", "dw-detail-heading", `${offers.length} saved offer${offers.length === 1 ? "" : "s"}`));
        offers.forEach(offer => {
          const n = el("section", "dw-offer");
          append(n, el("h4", "", offer.room_name || offer.rate_plan_name || "Source offer"),
            el("strong", "dw-offer-amount", amount(offer.amount) ? `${text(offer.currency, "")} ${offer.amount}` : text(offer.display_amount, "Amount not observed")),
            facts([["Price basis / precision", [human(offer.amount_basis || offer.source_amount_basis), human(offer.precision)].filter(value => value !== "Unknown").join(" · ") || "Unknown"], ["Rate plan", offer.rate_plan_name || offer.rate_plan], ["Room type", offer.room_name || offer.room_type], ["Meal", offer.meal_plan || offer.meals || (present(offer.breakfast_included) ? { breakfast_included: offer.breakfast_included } : null)], ["Cancellation", offer.cancellation_policy || offer.cancellation || offer.cancellation_terms || (present(offer.refundable) ? { refundable: offer.refundable } : null)], ["Payment", offer.payment_terms || offer.payment], ["Taxes included", offer.taxes_included], ["Fees included", offer.fees_included], ["Tax amount", offer.taxes], ["Fee amount", offer.fees], ["Tax / fee details", offer.taxes_and_fees || offer.tax_details || offer.fee_details], ["Membership required", offer.membership_required], ["Membership terms", offer.membership], ["Coupon", offer.coupon], ["Conditions", offer.conditions], ["Discount conditions", offer.discount_conditions], ["Party", offer.observed_context || offer.context], ["Context verified", offer.context_verified], ["Observed", stamp(offer.observed_at)]]));
          for (const option of array(offer.rate_options)) append(n, append(el("div", "dw-option"), el("strong", "", option.is_selected ? "Selected source option" : "Alternative source option"), facts([["Rate plan", option.rate_plan_name || option.rate_plan_id], ["Amount", present(option.amount) ? `${text(option.currency, "")} ${option.amount}` : "Not observed"], ["Basis", human(option.amount_basis)], ["Cancellation", option.cancellation_terms], ["Taxes included", option.taxes_included], ["Fees included", option.fees_included], ["Observed", stamp(option.observed_at)]])));
          inspector.appendChild(n);
        });
      }
      if (extra) inspector.appendChild(extra); syncDetailMode(); close.focus();
    }
    function showCell(entity, cell, context) {
      const inherited = state.mode === "str" && state.calendar && state.calendar.source_context && state.calendar.source_context[entity.source || entity.namespace];
      detail(entity.label || entity.title || entity.id,
        [["Stay", `${dateLabel(cell.date, true)} → ${dateLabel(cell.checkout, true)}`], ["Evidence", LABELS[stateOf(cell)]], ["Reported price", priceLabel(cell)], ["Availability", cell.availability], ["Source", sourceName(entity.source)], ["Basis", human(cell.amount_basis)], ["Precision", cell.precision], ["Original observation", stamp(cell.observed_at)], ["Reason", human(cell.reason)], ["Source context", inherited || context]], array(cell.offers).map(offer => ({ ...inherited, ...offer, observed_context: offer.observed_context || inherited, source_url: offer.source_url || cell.source_url })),
        append(el("div", "dw-detail-actions"), link(entity.source_url, "Open source property"), p("Unavailable applies only to the recorded source and context. It does not identify a booking.")));
    }
    function showProperty(entity) {
      detail(entity.label || entity.title || entity.id, [["Identity", entity.id], ["City", entity.city], ["Bedrooms", entity.bedrooms], ["Bathrooms", entity.bathrooms], ["Guest capacity", entity.person_capacity || entity.capacity], ["Currency", entity.currency], ["Source", sourceName(entity.source || entity.namespace)], ["Observed", stamp(entity.observed_at)]], [],
        append(el("div", "dw-detail-actions"), button("View comparison set →", () => { state.subject = entity.id; state.center = null; state.areaType = "circle"; state.polygon = null; state.localExcluded = new Set(); state.candidatePage = 0; state.view = "compset"; closeDetail(false); loadView(); }), link(entity.source_url, "Open source property"), p("Direct-site and Airbnb records remain separate unless an explicit identity link has been verified.")));
    }
    async function showCandidate(row) {
      if (mapView && mapView.mode && mapView.cancel) mapView.cancel();
      if (state.mode === "str" && !Array.isArray(row.missing_fields)) {
        const subject = state.subject, revision = state.summary && state.summary.revision, sequence = ++detailSequence;
        detail(row.title || row.name || row.id, [["Evidence", "Loading this candidate's saved audit…"]]);
        try {
          const result = await get(`/api/intelligence/str/compset?subject_id=${encodeURIComponent(subject)}&candidate_id=${encodeURIComponent(row.id || row.candidate_id)}&offset=0&limit=1`, "detail");
          if (!alive || sequence !== detailSequence || state.subject !== subject || state.mode !== "str") return;
          if (revision !== (state.summary && state.summary.revision) || result.revision && revision && result.revision !== revision) throw new Error("Saved sources changed during this detail. Reload saved data to use one consistent revision.");
          if (result.subject && result.subject.id === subject && result.candidates && result.candidates.length === 1 && result.candidates[0].id === (row.id || row.candidate_id)) return showCandidate(result.candidates[0]);
          throw new Error("The saved audit did not match this candidate.");
        } catch (error) { if (alive && sequence === detailSequence) detail(row.title || row.id, [["Evidence unavailable", error.message]]); }
        return;
      }
      detail(row.title || row.name || row.label || row.id || row.candidate_id,
        [["Decision", row.selected === true ? "Selected" : human(row.eligibility || row.status)], ["Reasons", row.rejection_reasons || row.reasons || row.match_reasons], ["Missing fields", row.missing_fields], ["Distance (km)", row.distance_km], ["Bedrooms", row.bedrooms], ["Bathrooms", row.bathrooms], ["Property type", row.property_type], ["Product / service profile", row.product], ["Amenities / services", row.amenities || row.services], ["Operator", row.operator_name || row.host_name], ["Operator size", row.operator_size], ["Operator evidence", row.operator_size_basis], ["Observed host listings", row.observed_host_listing_count ?? row.host_listing_count], ["Rating", row.rating ?? row.review_score], ["Observed", stamp(row.observed_at)], ["Provisional physical match", row.provisional_physical_match], ["Classification evidence", row.classification_evidence], ["Location evidence", row.location_evidence]], [], link(row.source_url || row.url, "Open evidence source"));
    }
    function navigationButton(label, glyph, selected, fn) { const b = button("", fn, `dw-nav-button${selected ? " is-active" : ""}`); b.setAttribute("aria-pressed", String(selected)); append(b, icon(glyph), el("span", "", label)); return b; }
    function navigate(mode, view) {
      if (searchTimer) { global.clearTimeout(searchTimer); searchTimer = null; }
      if (mode !== state.mode) { state.center = null; state.areaType = "circle"; state.polygon = null; state.localExcluded = new Set(); state.candidatePage = 0; }
      state.mode = mode; state.view = view || "calendar"; state.error = null; closeDetail(false); removeMap();
      syncCollectionScope();
      loadView();
    }
    function renderNavigation() {
      modeNav.replaceChildren(navigationButton("Short-term rentals", "str", state.mode === "str", () => navigate("str")), navigationButton("Hotels", "hotel", state.mode === "hotel", () => navigate("hotel")));
      const tabs = [["calendar", state.mode === "str" ? "Portfolio calendar" : "Rates", "calendar"], ["compset", "Comparison set", "compset"], ["map", "Map", "map"], ["activity", "Source activity", "activity"]];
      navigation.replaceChildren(...tabs.map(([id, label, glyph]) => navigationButton(label, glyph, state.view === id || id === "calendar" && state.view === "table", () => navigate(state.mode, id))));
      bottomNav.replaceChildren(...tabs.map(([id, label, glyph]) => navigationButton(id === "calendar" ? "Calendar" : id === "compset" ? "Compset" : id === "activity" ? "Activity" : label, glyph, state.view === id, () => navigate(state.mode, id))));
    }
    function renderHeading() {
      const profile = selectedHotelProfile();
      const title = state.mode === "str" ? "Your rental portfolio" : profile ? profile.title || profile.name || profile.id : "Hotel Aketa";
      const note = state.mode === "str" ? "Properties, calendars and comparison evidence." : profile ? `${text(profile.city)} · imported hotel profile · rates not configured` : `Dehradun · ${smallContext(currentHotel().context)}`;
      const collectionLink = el("a", "dw-text-button", "Collection & map"); collectionLink.href = "#collection-studio";
      collectionLink.setAttribute("aria-label", "Open the collection dashboard and map");
      const actions = append(el("div", "dw-heading-actions"), collectionLink, button("Reload saved", refresh), button(state.mode === "hotel" && profile && state.view === "compset" ? "Export configured names ↓" : state.view === "map" ? "Export map view ↓" : "Export visible page ↓", exportCurrent));
      if (state.mode === "hotel") {
        const calendar = el("a", "dw-button", "17-property Aketa calendar →");
        calendar.href = "/aketa-calendar";
        append(actions, calendar);
      }
      heading.replaceChildren(append(el("div"), el("h1", "", title), p(note)), actions);
    }
    function renderCoverage() {
      const str = state.summary && state.summary.str || {}, values = str.summary || {};
      const props = array(str.properties), direct = props.filter(p => (p.namespace || p.id && p.id.split(":")[0]) === "bnbme_direct").length, air = props.filter(p => (p.namespace || p.id && p.id.split(":")[0]) === "airbnb").length;
      let metrics;
      if (state.mode === "str") metrics = [[direct, "public properties"], [air, "separate Airbnb records"], [new Set(props.map(p => p.city).filter(present)).size, "recorded cities"]];
      else if (selectedHotelProfile()) {
        const profile = selectedHotelProfile(), evidence = configuredGroup(configuredLabels(), profile.id);
        const count = state.hotel ? evidence.count : profile.configured_label_status === "observed_name_only" ? profile.configured_label_count : null;
        metrics = [[hotelProfiles().length, "imported hotel profiles"], ["—", "rates not configured"], [Number.isInteger(count) && count >= 0 ? count : "—", "configured names · unverified"]];
      }
      else { const s = currentHotel().summary || {}; metrics = [[s.rate_rows ?? "—", "saved offer observations"], [s.unknown_cells ?? "—", "unknown source / dates"], [array(state.hotel && state.hotel.compset && state.hotel.compset.candidates).length, "researched candidates"]]; }
      const time = state.mode === "str" ? str.observed_at || state.summary && state.summary.observed_at : selectedHotelProfile() ? selectedHotelProfile().observed_at : currentHotel().observed_at;
      coverage.replaceChildren(...metrics.map(([value, label]) => append(el("div", "dw-stat"), el("strong", "", value), el("span", "", label))), append(el("div", "dw-source-time"), el("span", "", "Original source observation"), el("strong", "", stamp(time))));
    }
    function changedFilter(key, value) { state[key] = value; state.offset = 0; closeDetail(false); loadView(); }
    function renderToolbar() {
      toolbar.replaceChildren(); controls.clear();
      if (state.mode === "hotel" && hotelProfiles().length) {
        append(toolbar, field("Hotel", select("Hotel", [["aketa", "Hotel Aketa · collected rate dataset"], ...hotelProfiles().map(p => [p.id, `${p.title || p.name || p.id}${p.city ? ` · ${p.city}` : ""} · imported profile`])], state.hotelProfile, value => { state.hotelProfile = value; closeDetail(false); syncCollectionScope(); renderView(); })));
        if (selectedHotelProfile()) return;
      }
      if (state.mode === "str" && state.view === "calendar") {
        const props = array(state.summary && state.summary.str && state.summary.str.properties);
        const cities = [...new Set(props.map(x => x.city).filter(present))].sort();
        const input = el("input", "dw-search"); input.type = "search"; input.maxLength = 120; input.placeholder = "Find property or area"; input.value = state.query; input.setAttribute("aria-label", "Find property or area"); controls.set("Find property or area", input);
        input.addEventListener("input", () => { state.query = input.value; state.offset = 0; if (searchTimer) global.clearTimeout(searchTimer); searchTimer = global.setTimeout(() => { searchTimer = null; loadView(); }, 250); });
        append(toolbar, field("Location", select("Location", [["all", "All cities"], ...cities.map(c => [c, c])], state.city, v => changedFilter("city", v))), field("Property records", select("Property records", [["bnbme_direct", "BnBMe website"], ["airbnb", "Airbnb host records"], ["all", "Both sources · separate IDs"]], state.namespace, v => changedFilter("namespace", v))), field("Bedrooms", select("Bedrooms", [["all", "Any bedrooms"], ["0", "Studio"], ...[1, 2, 3, 4].map(n => [String(n), `${n} bedrooms`])], state.bedrooms, v => changedFilter("bedrooms", v))), field("Find a property", input));
      } else if (state.mode === "hotel" && state.view === "calendar") {
        const data = currentHotel(), offers = array(data.cells).flatMap(c => array(c.offers));
        const unique = values => [...new Set(values.filter(v => present(v) && v !== "Unknown"))].sort().map(v => [v, v]);
        const change = (k, v) => { state[k] = v; renderView(); };
        append(toolbar, field("Observation source", select("Observation source", [["all", "All sources"], ...array(data.entities).map(e => [e.source, e.label])], state.source, v => change("source", v))), field("Room", select("Room", [["all", "Any recorded room"], ...unique(offers.map(o => o.room_name))], state.room, v => change("room", v))), field("Meal", select("Meal", [["all", "Any recorded meal"], ...unique(offers.map(o => summarize(o.meals)))], state.meal, v => change("meal", v))), field("Cancellation", select("Cancellation", [["all", "All recorded terms"], ...unique(offers.map(o => summarize(o.cancellation || o.cancellation_terms)))], state.cancellation, v => change("cancellation", v))));
      } else if (state.view === "compset" || state.view === "map") {
        if (state.mode === "str") append(toolbar, field("Subject property", select("Subject property", allSubjects().map(s => [s.subject_id || s.id, `${s.city || "Unknown city"} · ${s.title || s.label || s.subject_id}`]), state.subject, value => { state.subject = value; state.center = null; state.areaType = "circle"; state.polygon = null; state.localExcluded = new Set(); state.candidatePage = 0; loadView(); })));
        append(toolbar, field("Saved decision", select("Saved decision", [["all", "All candidates"], ["selected", "Selected"], ["provisional", "Provisional"], ["excluded", "Excluded"]], state.decision, v => { state.decision = v; state.candidatePage = 0; state.mode === "str" ? loadView() : renderView(); })));
      }
    }
    function table(headers, label) {
      const scroll = el("div", "dw-table-scroll"); scroll.tabIndex = 0; scroll.setAttribute("role", "region"); scroll.setAttribute("aria-label", label);
      const n = el("table", "dw-table"), head = el("thead"), row = el("tr"), body = el("tbody");
      headers.forEach(value => { const th = el("th", "", value); th.scope = "col"; row.appendChild(th); }); append(head, row); append(n, head, body); scroll.appendChild(n); return { scroll, body, node: n };
    }
    function datePager(parent, dates, onChange) {
      const previous = button("←", () => onChange(-1), "dw-icon-button"), next = button("→", () => onChange(1), "dw-icon-button");
      previous.setAttribute("aria-label", "Previous date window"); next.setAttribute("aria-label", "Next date window");
      append(parent, append(el("div", "dw-date-pager"), previous, el("strong", "", dates.length ? `${dateLabel(dates[0])} – ${dateLabel(dates[dates.length - 1], true)}` : "No dates saved"), next));
    }
    function renderStrCalendar() {
      const data = state.calendar;
      if (!data) { canvas.appendChild(empty("No saved calendar window is available.")); return; }
      const top = el("div", "dw-panel-heading"); datePager(top, array(data.dates), direction => { const bounds = state.summary.str.calendar_bounds || {}; let next = addDays(state.start, direction * state.days); if (isoDate(bounds.start) && next < bounds.start) next = bounds.start; if (isoDate(bounds.end) && next >= bounds.end) next = addDays(bounds.end, -1); state.start = next; state.day = null; loadView(); }); canvas.appendChild(top);
      const rows = calendarView(data, { evidence: state.evidence });
      if (!mobile()) {
        const grid = table(["Property", ...array(data.dates).map(d => dateLabel(d))], "Saved rental multicalendar"); grid.node.className += " dw-multicalendar"; grid.scroll.className += " dw-desktop-calendar";
        for (const { entity, cells } of rows) {
          const tr = el("tr"), th = el("th", "dw-property-cell"); th.scope = "row";
          const name = button(entity.label || entity.title || entity.id, () => showProperty(entity), "dw-property-name");
          append(th, name, el("small", "", `${present(entity.bedrooms) ? entity.bedrooms === 0 ? "Studio" : `${entity.bedrooms} bedrooms` : "Bedrooms unknown"} · ${text(entity.bathrooms, "?")} baths · ${text(entity.currency)}`), badge(sourceName(entity.source || entity.namespace), "source")); tr.appendChild(th);
          cells.forEach(cell => { const status = stateOf(cell); const b = button("", () => showCell(entity, cell, data.request), `dw-cell dw-cell-${status}`); append(b, el("strong", "", priceLabel(cell)), el("small", "", status === "restricted" ? LABELS[status] : cell.amount_basis === "website_calendar_rate" ? "Website calendar" : LABELS[status])); b.setAttribute("aria-label", `${entity.label || entity.title}, ${cell.date}: ${priceLabel(cell)}, ${LABELS[status]}`); tr.appendChild(append(el("td"), b)); }); grid.body.appendChild(tr);
        }
        canvas.appendChild(rows.length ? grid.scroll : empty("No properties match these filters."));
      } else {
        const days = el("div", "dw-mobile-days"); canvas.appendChild(days);
        const paint = () => {
          days.replaceChildren(); const date = state.day && array(data.dates).includes(state.day) ? state.day : array(data.dates)[0]; state.day = date;
          days.appendChild(dayStrip(data.dates, date, day => { state.day = day; paint(); }));
          for (const { entity, cells } of calendarView(data, { day: date, evidence: state.evidence })) {
            const cell = cells[0]; if (!cell) continue;
            const n = el("article", "dw-day-row"), status = stateOf(cell); append(n, append(el("div"), button(entity.label || entity.title || entity.id, () => showProperty(entity), "dw-property-name"), p(`${sourceName(entity.source || entity.namespace)} · ${text(entity.bedrooms, "?")} bedrooms · ${text(entity.currency)}`, "dw-caption")), button(priceLabel(cell), () => showCell(entity, cell, data.request), `dw-day-price dw-cell-${status}`)); if (status === "restricted") n.appendChild(badge(LABELS[status], status)); days.appendChild(n);
          }
          if (!rows.length) days.appendChild(empty("No properties match these filters."));
        }; paint();
      }
      const total = Number.isInteger(data.total) ? data.total : Number.isInteger(data.total_properties) ? data.total_properties : rows.length;
      const prev = button("←", () => { state.offset = Math.max(0, state.offset - 25); loadView(); }, "dw-icon-button"), next = button("→", () => { state.offset += 25; loadView(); }, "dw-icon-button"); prev.disabled = state.offset === 0; next.disabled = state.offset + rows.length >= total; prev.setAttribute("aria-label", "Previous property page"); next.setAttribute("aria-label", "Next property page");
      append(canvas, append(el("div", "dw-table-footer"), p(`${rows.length ? state.offset + 1 : 0}–${state.offset + rows.length} of ${total} matching properties`, "dw-caption"), append(el("div", "dw-button-group"), prev, next)), p("Amounts retain their source currency. Calendar rates are indicative; an available date is not a verified stay quote.", "dw-footnote"));
    }
    function dayStrip(dates, selected, choose) {
      const strip = el("div", "dw-day-strip"); strip.setAttribute("role", "group"); strip.setAttribute("aria-label", "Saved arrival date");
      for (const date of array(dates)) { const b = button(dateLabel(date), () => choose(date), `dw-day${date === selected ? " is-active" : ""}`); b.setAttribute("aria-pressed", String(date === selected)); b.setAttribute("aria-label", `Arrival ${date}`); strip.appendChild(b); }
      return strip;
    }
    function renderHotelDays(data, rows, dates) {
      const holder = el("div", "dw-hotel-days"); canvas.appendChild(holder);
      const paint = () => {
        holder.replaceChildren(); const date = dates.includes(state.hotelDay) ? state.hotelDay : dates[0]; state.hotelDay = date;
        holder.appendChild(dayStrip(dates, date, day => { state.hotelDay = day; paint(); }));
        for (const { entity, cells } of rows) {
          const cell = cells.find(item => item.date === date); if (!cell) continue;
          const row = el("article", "dw-day-row dw-hotel-day-row");
          append(row, append(el("div", "dw-source-heading"), el("h3", "", entity.label || sourceName(entity.source)), badge(LABELS[stateOf(cell)], stateOf(cell))),
            button(priceLabel(cell), () => showCell(entity, cell, data.context), `dw-day-price dw-cell-${stateOf(cell)}`),
            p(`${dateLabel(cell.date)} → ${dateLabel(cell.checkout)} · ${text(cell.currency)} · ${human(cell.amount_basis)}`, "dw-caption"),
            p(`Observed ${stamp(cell.observed_at)}`, "dw-caption"));
          holder.appendChild(row);
        }
        if (!rows.length || !dates.length) holder.appendChild(empty("No saved source rows match this view."));
      }; paint();
    }
    function renderHotelTable(data, rows) {
      const entries = rows.flatMap(({ entity, cells }) => cells.flatMap(cell => (array(cell.offers).length ? cell.offers : [null]).map((offer, index) => ({ entity, cell, offer, index }))));
      const ribbon = el("div", "dw-table-controls dw-hotel-ribbon"), actions = el("div", "dw-table-control-actions"), editor = el("div", "dw-table-editor");
      const search = el("input", "dw-search"); search.type = "search"; search.placeholder = "Search saved rates, rooms, terms"; search.setAttribute("aria-label", "Search saved hotel rates"); search.value = state.hotelSearch;
      const count = el("span", "dw-caption");
      const sort = el("select", "dw-select"); sort.setAttribute("aria-label", "Sort saved hotel rates");
      for (const [key, label] of [["date", "Stay date"], ["source", "Source"], ["observed", "Observation time"]]) { const option = el("option", "", label); option.value = key; sort.appendChild(option); } sort.value = state.hotelSort;
      const editorButton = (label, mode) => {
        const control = button(label, () => { state.hotelEditor = state.hotelEditor === mode ? null : mode; paintEditor(); }, "dw-button");
        control.setAttribute("aria-controls", "dw-hotel-editor"); control.setAttribute("aria-expanded", String(state.hotelEditor === mode)); return control;
      };
      const filterButton = editorButton("Filter", "filter"), columnsButton = editorButton("Columns", "columns"); editor.id = "dw-hotel-editor";
      const optional = [["room", "Room / rate plan"], ["basis", "Rate basis"], ["meal", "Meal"], ["cancellation", "Cancellation"], ["payment", "Payment"], ["tax", "Tax & fees"], ["context", "Stay context"], ["observed", "Observed"]];
      function paintEditor() {
        editor.replaceChildren(); editor.hidden = !state.hotelEditor; filterButton.setAttribute("aria-expanded", String(state.hotelEditor === "filter")); columnsButton.setAttribute("aria-expanded", String(state.hotelEditor === "columns"));
        if (state.hotelEditor === "columns") for (const [key, label] of optional) {
          const toggle = el("input"); toggle.type = "checkbox"; toggle.checked = state.hotelColumns.has(key); toggle.setAttribute("aria-label", `Show ${label} column`);
          toggle.addEventListener("change", () => { if (toggle.checked) state.hotelColumns.add(key); else state.hotelColumns.delete(key); paint(); });
          append(editor, append(el("label", "dw-column-choice"), toggle, el("span", "", label)));
        }
        if (state.hotelEditor === "filter") {
          const offers = array(data.cells).flatMap(cell => array(cell.offers)), unique = values => [...new Set(values.filter(value => present(value) && value !== "Unknown"))].sort().map(value => [value, value]);
          const change = (key, value) => { state[key] = value; renderView(); };
          append(editor, field("Observation source", select("Observation source", [["all", "All sources"], ...array(data.entities).map(entity => [entity.source, entity.label])], state.source, value => change("source", value))),
            field("Room", select("Room", [["all", "Any recorded room"], ...unique(offers.map(offer => offer.room_name))], state.room, value => change("room", value))),
            field("Meal", select("Meal", [["all", "Any recorded meal"], ...unique(offers.map(offer => summarize(offer.meals)))], state.meal, value => change("meal", value))),
            field("Cancellation", select("Cancellation", [["all", "All recorded terms"], ...unique(offers.map(offer => summarize(offer.cancellation || offer.cancellation_terms)))], state.cancellation, value => change("cancellation", value))));
        }
      }
      const list = table([], "Hotel saved rate table, one row per recorded offer"); list.node.className += " dw-hotel-rate-table"; list.scroll.className += " dw-hotel-rate-table";
      const filteredEntries = () => {
        const query = state.hotelSearch.trim().toLocaleLowerCase();
        const matching = query ? entries.filter(({ entity, cell, offer }) => [entity.label, entity.source, cell.date, cell.checkout, cell.currency, cell.amount_basis, offer && offer.room_name, offer && offer.rate_plan_name, offer && offer.meals, offer && offer.cancellation_terms, offer && offer.payment_terms].some(value => summarize(value).toLocaleLowerCase().includes(query))) : entries;
        return [...matching].sort((a, b) => state.hotelSort === "source" ? String(a.entity.label).localeCompare(String(b.entity.label)) || String(a.cell.date).localeCompare(String(b.cell.date)) : state.hotelSort === "observed" ? String(b.offer && b.offer.observed_at || b.cell.observed_at || "").localeCompare(String(a.offer && a.offer.observed_at || a.cell.observed_at || "")) : String(a.cell.date).localeCompare(String(b.cell.date)) || String(a.entity.label).localeCompare(String(b.entity.label)));
      };
      function paint() {
        const enabled = optional.filter(([key]) => state.hotelColumns.has(key));
        const headers = ["Source", "Stay", "Reported rate", ...enabled.map(([, label]) => label), "Details"];
        const heading = el("tr"); for (const label of headers) { const th = el("th", "", label); th.scope = "col"; heading.appendChild(th); } list.node.children[0].replaceChildren(heading);
        const visible = filteredEntries(); list.body.replaceChildren(); count.textContent = `${visible.length} saved ${visible.length === 1 ? "row" : "rows"} · ${entries.length} recorded rows`;
        for (const { entity, cell, offer, index } of visible) {
          const tr = el("tr", "dw-hotel-rate-row"), recorded = offer && (amount(offer.amount) ? `${text(offer.currency || cell.currency, "")} ${offer.amount}` : text(offer.display_amount, "Amount not observed"));
          const rate = offer ? recorded : priceLabel(cell), stay = `${dateLabel(cell.date)} → ${dateLabel(cell.checkout)}`;
          append(tr, append(el("th", "dw-property-cell"), el("strong", "", entity.label || sourceName(entity.source)), el("small", "", sourceName(entity.source))), el("td", "", stay), append(el("td", "dw-number"), el("strong", "", rate), badge(offer ? human(offer.precision || cell.precision || stateOf(cell)) : LABELS[stateOf(cell)], stateOf(cell))));
          for (const [key] of enabled) {
            const values = { room: offer && [offer.room_name || offer.room_type, offer.rate_plan_name || offer.rate_plan].filter(present).join(" · "), basis: offer && (offer.amount_basis || offer.source_amount_basis) || cell.amount_basis, meal: offer && (offer.meal_plan || offer.meals), cancellation: offer && (offer.cancellation_policy || offer.cancellation || offer.cancellation_terms), payment: offer && (offer.payment_terms || offer.payment), tax: offer && [present(offer.taxes_included) ? `Tax included: ${summarize(offer.taxes_included)}` : null, present(offer.fees_included) ? `Fees included: ${summarize(offer.fees_included)}` : null, offer.taxes_and_fees || offer.tax_details || offer.fee_details || offer.taxes || offer.fees].filter(present).map(summarize).join(" · "), context: offer && (offer.observed_context || offer.context) || data.context, observed: stamp(offer && offer.observed_at || cell.observed_at) };
            tr.appendChild(el("td", "", present(values[key]) ? summarize(values[key]) : "Unknown"));
          }
          const inspect = button("All offers →", () => showCell(entity, cell, data.context), "dw-text-button"); inspect.setAttribute("aria-label", `Inspect all saved ${entity.label || sourceName(entity.source)} offers for ${cell.date}`);
          tr.appendChild(append(el("td"), inspect)); list.body.appendChild(tr);
        }
      }
      search.addEventListener("input", () => { state.hotelSearch = search.value; paint(); }); sort.addEventListener("change", () => { state.hotelSort = sort.value; paint(); });
      append(actions, search, count, filterButton, field("Sort", sort), columnsButton); append(ribbon, actions, editor); canvas.appendChild(ribbon); canvas.appendChild(list.scroll); paintEditor(); paint();
    }
    function renderHotel() {
      const data = currentHotel(), dates = array(data.dates), rows = hotelView(data, state);
      const top = el("div", "dw-panel-heading"), tabs = el("div", "dw-segments dw-hotel-ribbon");
      for (const [id, name] of [["calendar", "Calendar"], ["table", "Table"]]) { const b = button(name, () => { state.view = id; renderView(); }, state.view === id ? "is-active" : ""); b.setAttribute("aria-pressed", String(state.view === id)); tabs.appendChild(b); }
      append(top, el("strong", "", dates.length ? `${dateLabel(dates[0])} – ${dateLabel(dates[dates.length - 1], true)}` : "No saved dates"), tabs); canvas.appendChild(top);
      if (state.view === "table") {
        renderHotelTable(data, rows);
      } else if (mobile()) {
        renderHotelDays(data, rows, dates);
      } else {
        const grid = el("div", "dw-month-grid"); grid.setAttribute("role", "list"); grid.setAttribute("aria-label", "Saved hotel arrival dates");
        ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].forEach(day => grid.appendChild(el("div", "dw-weekday", day)));
        const first = dates.length ? (new Date(`${dates[0]}T12:00:00Z`).getUTCDay() + 6) % 7 : 0; for (let i = 0; i < first; i++) grid.appendChild(el("div", "dw-calendar-spacer"));
        for (const date of dates) {
          const sources = rows.map(row => ({ entity: row.entity, cell: row.cells.find(c => c.date === date) })).filter(r => r.cell);
          const positive = sources.filter(r => ["quoted", "indicative"].includes(stateOf(r.cell))), negative = sources.filter(r => stateOf(r.cell) === "unavailable");
          const label = sources.length === 1 ? priceLabel(sources[0].cell) : positive.length ? `${positive.length} source${positive.length === 1 ? "" : "s"} with rates` : negative.length ? `${negative.length} source unavailable` : "Not observed";
          const tone = sources.length === 1 ? stateOf(sources[0].cell) : positive.length ? "indicative" : "unknown";
          const b = button("", () => {
            detail(`Aketa · ${dateLabel(date, true)}`, [["Saved context", data.context], ["Source coverage", sources.map(s => `${s.entity.label}: ${priceLabel(s.cell)}`).join(" · ")]], sources.flatMap(({ entity, cell }) => array(cell.offers).map(o => ({ ...o, rate_plan_name: `${entity.label} · ${o.rate_plan_name || "Source offer"}` }))), p("Each source remains separate. These are not matched competitor-hotel prices or a market minimum."));
          }, `dw-month-cell dw-cell-${tone}`); b.setAttribute("role", "listitem");
          b.setAttribute("aria-label", `${dateLabel(date, true)} · ${sources.length} recorded sources. Open all offer and stay details.`);
          const sourceLines = el("span", "dw-month-offers");
          if (sources.length) for (const { entity, cell } of sources) append(sourceLines, append(el("span", "dw-month-source"), el("span", "", entity.label || sourceName(entity.source)), el("strong", "", priceLabel(cell)), el("small", "", `${LABELS[stateOf(cell)]} · ${array(cell.offers).length} saved ${array(cell.offers).length === 1 ? "offer" : "offers"}`)));
          else sourceLines.appendChild(el("span", "dw-month-source", "No source observation"));
          append(b, el("span", "dw-date-number", dateLabel(date)), el("strong", "dw-month-summary", label), sourceLines); grid.appendChild(b);
        }
        canvas.appendChild(grid);
      }
      const comp = state.hotel && state.hotel.compset || {}; const preview = append(el("div", "dw-hotel-comparison"), append(el("div"), el("h2", "", "Your comparison set"), p("Product, service and observed location · within 10 km")), button("Review candidates →", () => navigate("hotel", "compset")));
      array(comp.candidates).slice(0, 3).forEach(row => preview.appendChild(button(row.title || row.name || row.label || "Candidate hotel", () => showCandidate(row), "dw-candidate-preview"))); canvas.appendChild(preview);
      append(canvas, p("Room, meal and cancellation controls filter saved offers. Guest count and stay length remain the recorded context. No cross-source minimum or market parity is inferred.", "dw-footnote"));
    }
    function currentComparison() { return state.mode === "str" ? state.comparison : state.hotel && state.hotel.compset; }
    function candidates(payload, forMap = false) {
      const rows = forMap && Array.isArray(payload && payload.map_points) ? payload.map_points : array(payload && payload.candidates);
      return rows.filter(row => state.decision === "all" || (state.decision === "selected" ? row.selected === true : row.eligibility === state.decision || row.status === state.decision));
    }
    function selectedMapCandidates(payload, preview = false, includeExcluded = false) {
      const rows = candidates(payload, true), shape = preview && mapView && mapView.polygonDraft ? "polygon" : state.areaType;
      let selected;
      if (shape === "polygon") selected = polygonCandidates({ candidates: rows }, preview && mapView && mapView.polygonDraft || state.polygon).map(row => ({ ...row, view_distance_km: distanceKm(payload.subject, row) }));
      else if (shape === "all") selected = rows.filter(row => distanceKm(row, row) !== null).map(row => ({ ...row, view_distance_km: distanceKm(payload.subject, row) }));
      else {
      const draft = preview && mapView && mapView.draft;
      selected = mapCandidates({ candidates: rows }, draft ? draft.center : state.center || payload.subject || {}, draft ? draft.radius : state.radius);
      }
      return includeExcluded ? selected : selected.filter(row => !state.localExcluded.has(row.id || row.candidate_id));
    }
    const localSetKey = "compset.map-selections.v1";
    const currentMapIdentity = data => `${state.mode}:${data && (data.subject_id || data.subject && data.subject.id) || ""}:${data && data.revision || state.summary && state.summary.revision || "unknown_revision"}`;
    function readLocalSets() {
      try { const value = global.localStorage && global.localStorage.getItem(localSetKey); const parsed = value && JSON.parse(value); return Array.isArray(parsed) ? parsed.filter(item => item && typeof item.name === "string" && typeof item.identity === "string").slice(0, 100) : []; } catch (_) { return []; }
    }
    function writeLocalSets(sets) { try { if (!global.localStorage) return false; global.localStorage.setItem(localSetKey, JSON.stringify(sets.slice(0, 100))); return true; } catch (_) { return false; } }
    function validLocalSet(item, data) {
      if (!item || item.identity !== currentMapIdentity(data) || !["circle", "polygon", "all"].includes(item.areaType)) return false;
      if (item.areaType === "polygon" && !validPolygon(item.polygon)) return false;
      if (boundedRadius(item.radius) !== item.radius || item.center && distanceKm(item.center, item.center) === null) return false;
      return Array.isArray(item.excludedIds) && item.excludedIds.length <= 10000 && item.excludedIds.every(id => typeof id === "string" && id.length <= 250);
    }
    function renderComparison() {
      const data = currentComparison(); if (!data) { canvas.appendChild(empty("No comparison evidence is saved for this subject.")); return; }
      const subject = data.subject || {}, rows = candidates(data), summary = data.summary || {}, total = state.mode === "str" && Number.isInteger(data.candidate_total) ? data.candidate_total : rows.length;
      append(canvas, append(el("div", "dw-panel-heading"), append(el("div"), el("h2", "", subject.title || subject.name || "Comparison evidence"), p(`${total} matching saved candidates · ${summary.selected_count ?? array(data.candidates).filter(x => x.selected === true).length} selected in saved comparison`)), button("Open map →", () => navigate(state.mode, "map"))), p(state.mode === "str" ? "Source identities stay separate. Similar physical attributes alone do not verify an Airbnb link." : "Hotel profile research is separate from Aketa's dated source rates. Candidate room prices have not been collected here.", "dw-context-note"));
      const evidence = el("details", "dw-method"); append(evidence, el("summary", "", "Matching rules and coverage"), facts([["Criteria", data.criteria || data.search], ["Source coverage", data.source_coverage || data.coverage || data.sources], ["Adaptive steps", data.adaptive && data.adaptive.steps || data.relaxation], ["Missing subject fields", data.adaptive && data.adaptive.subject_core_unknown_fields], ["Warnings", data.warnings]])); canvas.appendChild(evidence);
      const page = Math.min(state.candidatePage, Math.max(0, Math.ceil(total / 25) - 1)); state.candidatePage = page;
      const listing = table(["Property", "Decision", "Product / services", "Distance", "Evidence"], "Candidate comparison decisions");
      for (const row of (state.mode === "str" ? rows : rows.slice(page * 25, page * 25 + 25))) {
        const tr = el("tr"); const name = row.title || row.name || row.label || row.id || row.candidate_id;
        append(tr, append(el("td"), button(name, () => showCandidate(row), "dw-property-name"), el("small", "dw-caption", row.host_name || row.operator_name || row.city || row.id || row.candidate_id)),
          append(el("td"), badge(row.selected === true ? "Selected" : human(row.eligibility || row.status || "provisional"), row.selected === true ? "quoted" : "unknown")),
          el("td", state.mode === "str" ? "dw-number" : "", state.mode === "str" ? `${text(row.bedrooms, "?")} bedrooms · ${text(row.bathrooms, "?")} baths` : summarize(row.product_type || row.property_type || row.services || row.amenities)),
          el("td", "dw-number", typeof row.distance_km === "number" ? `${row.distance_km.toFixed(2)} km${row.distance_km <= 5 && state.mode === "hotel" ? " · inner 5 km" : ""}` : "Coordinates unverified"),
          append(el("td"), p(summarize(row.rejection_reasons || row.reasons || row.match_reasons || row.missing_fields), "dw-caption"), button("Review →", () => showCandidate(row), "dw-text-button"))); listing.body.appendChild(tr);
      }
      canvas.appendChild(rows.length ? listing.scroll : empty("No candidates match this saved-decision filter. Missing candidates are not evidence of an empty market."));
      const pageTo = direction => { state.candidatePage += direction; state.mode === "str" ? loadView() : renderView(); };
      const prev = button("←", () => pageTo(-1), "dw-icon-button"), next = button("→", () => pageTo(1), "dw-icon-button"); prev.disabled = page === 0; next.disabled = (page + 1) * 25 >= total; prev.setAttribute("aria-label", "Previous candidate page"); next.setAttribute("aria-label", "Next candidate page"); append(canvas, append(el("div", "dw-table-footer"), p(`${total ? page * 25 + 1 : 0}–${Math.min(total, (page + 1) * 25)} of ${total} candidates`), append(el("div", "dw-button-group"), prev, next)));
    }
    function renderMap() {
      const data = currentComparison();
      if (!data) { removeMap(); canvas.replaceChildren(empty("Choose a subject with saved comparison evidence.")); return; }
      const subject = data.subject || {}, center = state.center || subject;
      const key = `${state.mode}:${subject.id || data.subject_id}:${state.summary && state.summary.revision}`;
      if (mapView && mapView.key === key) { mapView.data = data; updateMapView(); return; }
      removeMap(); canvas.replaceChildren();
      const count = p(""), title = append(el("div", "dw-panel-heading"), append(el("div"), el("h2", "", "Comparison area"), count), button("Back to comparison", () => navigate(state.mode, "compset")));
      const radius = el("input", "dw-radius"), radiusNumber = el("input", "dw-map-radius-number");
      for (const [control, type, label] of [[radius, "range", "Map view radius in kilometres"], [radiusNumber, "number", "Area radius in kilometres"]]) {
        control.type = type; control.min = String(MIN_RADIUS_KM); control.max = String(MAX_RADIUS_KM); control.step = ".1"; control.value = String(state.radius); control.setAttribute("aria-label", label);
        control.addEventListener("change", () => { const next = boundedRadius(control.value); if (mapView && mapView.mode) mapView.cancel(); if (next !== null) { state.radius = next; state.areaType = "circle"; state.polygon = null; } updateMapView(); });
      }
      const status = p("", "dw-map-status"), summary = el("section", "dw-map-summary"), metrics = el("div", "dw-map-metrics");
      status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite"); summary.setAttribute("aria-label", "Selected area observed evidence");
      const draw = button("Draw area", () => mapView && mapView.arm("draw")), move = button("Move center", () => mapView && mapView.arm("move")), resize = button("Resize area", () => mapView && mapView.arm("resize")), polygon = button("Draw polygon", () => mapView && mapView.arm("polygon"), "dw-button dw-map-draw-polygon"),
        undo = button("Undo vertex", () => { if (mapView && mapView.polygonDraft) { mapView.polygonDraft.pop(); mapView.polygonPreview = null; if (mapView.sync) mapView.sync(); updateMapView(); } }, "dw-button dw-map-undo"),
        apply = button("Apply area", () => { if (!mapView || !mapView.polygonDraft) return; if (!validPolygon(mapView.polygonDraft)) { mapView.status.textContent = "Polygon needs 3–64 distinct vertices and a simple, non-crossing boundary."; return; } state.polygon = mapView.polygonDraft.map(point => ({ ...point })); state.areaType = "polygon"; mapView.cancel(`Polygon selected · ${state.polygon.length} vertices. Drag a vertex to refine it.`); }, "dw-button dw-map-apply"),
        clear = button("Clear area", () => { if (!mapView) return; mapView.cancel(""); state.areaType = "all"; state.polygon = null; mapView.status.textContent = "Area cleared. All located observed candidates under the saved-decision filter are shown."; updateMapView(); }, "dw-button dw-map-clear"),
        cancel = button("Cancel", () => mapView && mapView.cancel("Area edit cancelled. The previous area is retained.")); cancel.hidden = true;
      const actions = append(el("div", "dw-map-actions"), draw, polygon, move, resize, undo, apply, clear, cancel);
      const setName = el("input", "dw-map-set-name"); setName.type = "text"; setName.maxLength = 80; setName.placeholder = "Name this local selection"; setName.setAttribute("aria-label", "Local selection name");
      const setPicker = select("Saved local selection", [["", "Choose saved local selection"], ...readLocalSets().filter(item => item.identity === currentMapIdentity(data)).map(item => [item.name, item.name])], "", () => {});
      const saveSet = button("Save local set", () => {
        const name = setName.value.trim(); if (!name || !mapView) { status.textContent = "Enter a name to save this local selection."; return; }
        if (mapView.mode) mapView.cancel("Area preview cancelled. Saving the committed area.");
        const sets = readLocalSets().filter(item => item.identity !== currentMapIdentity(data) || item.name !== name);
        sets.push({ identity: currentMapIdentity(data), name, areaType: state.areaType, center: state.center, radius: state.radius, polygon: state.polygon, excludedIds: [...state.localExcluded] });
        if (!writeLocalSets(sets)) { status.textContent = "Local browser storage is unavailable; this set was not saved."; return; }
        if (!Array.from(setPicker.children).some(option => option.value === name)) { const option = el("option", "", name); option.value = name; setPicker.appendChild(option); } setPicker.value = name; status.textContent = `Saved local set “${name}” for this subject. Saved comparison decisions were not changed.`;
      }, "dw-button dw-map-save-set");
      const loadSet = button("Load local set", () => {
        const item = readLocalSets().find(entry => entry.identity === currentMapIdentity(data) && entry.name === setPicker.value);
        if (!validLocalSet(item, data)) { status.textContent = "Choose a valid local selection saved for this subject."; return; }
        if (mapView && mapView.mode) mapView.cancel(""); state.areaType = item.areaType; state.center = item.center ? { ...item.center } : null; state.radius = item.radius; state.polygon = item.polygon ? item.polygon.map(point => ({ ...point })) : null; state.localExcluded = new Set(item.excludedIds); updateMapView(); status.textContent = `Loaded local set “${item.name}”. Saved comparison decisions were not changed.`;
      }, "dw-button dw-map-load-set");
      const includeAll = button("Include all in area", () => { state.localExcluded.clear(); updateMapView(); status.textContent = "All located candidates in this area are included locally."; }, "dw-button dw-map-include-all");
      const localSets = append(el("div", "dw-map-local-sets"), field("Local set name", setName), field("Saved local sets", setPicker), saveSet, loadSet, includeAll);
      const vertexLat = el("input", "dw-map-coordinate"), vertexLng = el("input", "dw-map-coordinate");
      for (const [control, label, min, max] of [[vertexLat, "Polygon vertex latitude", -90, 90], [vertexLng, "Polygon vertex longitude", -180, 180]]) { control.type = "number"; control.min = String(min); control.max = String(max); control.step = "any"; control.setAttribute("aria-label", label); }
      const addVertex = button("Add coordinate vertex", () => { if (!mapView || !mapView.polygonLayer || typeof mapView.arm !== "function") return; const point = { latitude: Number(vertexLat.value), longitude: Number(vertexLng.value) }; if (!vertexLat.value.trim() || !vertexLng.value.trim() || distanceKm(point, point) === null) { status.textContent = "Enter a valid latitude and longitude."; return; } if (mapView.mode !== "polygon") mapView.arm("polygon"); if (mapView.polygonDraft.length >= 64) { status.textContent = "Polygon limit is 64 vertices."; return; } mapView.polygonDraft.push(point); mapView.polygonPreview = null; mapView.sync(); updateMapView(); status.textContent = `${mapView.polygonDraft.length} polygon vertices. Apply area to finish.`; }, "dw-button dw-map-add-vertex");
      const coordinateEntry = append(el("div", "dw-map-coordinate-entry"), field("Vertex latitude", vertexLat), field("Vertex longitude", vertexLng), addVertex);
      append(canvas, title, append(el("div", "dw-map-tools"), actions, field("Radius (km)", radiusNumber), field("Adjust radius", radius),
        p("Circle: draw from the center outward, or drag its center and edge handles. Polygon: tap to add vertices, move to preview an edge, drag a vertex to refine, then Apply area. Undo removes the last vertex; Cancel retains the previous area. Clear area shows all located candidates. Pan or zoom outside edit mode.", "dw-caption"),
        p("Radius is the center-to-edge distance · 0.1–50 km. Area and manual inclusion are local views of saved candidates; they do not collect or change saved match decisions.", "dw-map-radius-guide"), coordinateEntry, localSets, status));
      const mapNode = el("div", "dw-map"); mapNode.setAttribute("aria-label", "Observed subject and candidate locations"); canvas.appendChild(mapNode);
      const list = el("div", "dw-map-list"), mapTable = table(["Include", "Candidate", "Saved decision", "Observed distance", "Evidence"], "Candidates in selected area"), results = el("div", "dw-map-results"), note = p("", "dw-footnote"), pageLabel = p("", "dw-map-page-label"), pageBack = button("←", () => { if (mapView) { mapView.page--; updateMapView(); } }, "dw-icon-button"), pageNext = button("→", () => { if (mapView) { mapView.page++; updateMapView(); } }, "dw-icon-button"); pageBack.setAttribute("aria-label", "Previous map candidates"); pageNext.setAttribute("aria-label", "Next map candidates");
      const pageControls = append(el("div", "dw-table-footer dw-map-table-footer"), pageLabel, append(el("div", "dw-button-group"), pageBack, pageNext)); mapTable.scroll.className += " dw-map-table"; append(summary, el("h3", "", "Selected area"), metrics, p("Counts describe available observed candidates with recorded coordinates, under the saved-decision filter. They do not describe the full market.", "dw-caption")); append(results, mapTable.scroll, pageControls, list); append(canvas, results, summary, note);
      mapView = { key, data, count, radius, radiusNumber, list, mapTable, page: 0, pageLabel, pageBack, pageNext, note, metrics, status, mapNode, draw, move, resize, polygonButton: polygon, undo, apply, clear, cancelButton: cancel, points: new Map(), circle: null, polygonLayer: null, polygonVertices: [], polygonDraft: null, polygonPreview: null, marker: null, resizeMarker: null, layer: null, mode: null, gesture: null, draft: null };
      state.radius = boundedRadius(state.radius) ?? 2;
      if (distanceKm(center, center) === null) mapNode.appendChild(empty("Subject coordinates are not observed. No location is guessed."));
      else if (!global.L) mapNode.appendChild(empty("Map library is unavailable. The observed candidate list remains below."));
      else {
        try {
          map = global.L.map(mapNode, { scrollWheelZoom: false }).setView([center.latitude, center.longitude], 13);
          global.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).addTo(map);
          mapView.circle = global.L.circle([center.latitude, center.longitude], { radius: state.radius * 1000, color: "#087f8c", weight: 2, fillOpacity: .07 }).addTo(map);
          if (typeof global.L.polygon === "function") mapView.polygonLayer = global.L.polygon([], { color: "#c79600", weight: 3, fillOpacity: .13 }).addTo(map);
          const handle = (className, label, symbol) => ({ draggable: false, keyboard: true, title: label, alt: label,
            ...(typeof global.L.divIcon === "function" ? { icon: global.L.divIcon({ className: `dw-map-handle ${className}`, html: `<span aria-hidden="true">${symbol}</span>`, iconSize: [44, 44], iconAnchor: [22, 22] }) } : {}) });
          mapView.marker = global.L.marker([center.latitude, center.longitude], handle("dw-map-center-handle", "Move area center", "+")).addTo(map);
          mapView.resizeMarker = global.L.marker(radiusEdge(center, state.radius), handle("dw-map-resize-handle", "Resize area radius", "↔")).addTo(map);
          mapView.layer = global.L.layerGroup().addTo(map);
          installMapAreaInteraction(mapView, map);
          // Ordinary map clicks preserve the area; only explicit actions or handles edit it.
          map.on("click", () => {});
        } catch (_) { if (mapView.cleanup) mapView.cleanup(); if (map) map.remove(); map = null; mapView.circle = null; mapView.marker = null; mapView.resizeMarker = null; mapView.layer = null; mapNode.replaceChildren(empty("Map could not initialize. The observed candidate list remains available.")); }
      }
      draw.disabled = move.disabled = resize.disabled = !map; polygon.disabled = addVertex.disabled = vertexLat.disabled = vertexLng.disabled = !map || !mapView.polygonLayer;
      updateMapView();
    }
    function installMapAreaInteraction(view, mountedMap) {
      const node = view.mapNode, listeners = [], handlers = ["dragging", "touchZoom", "doubleClickZoom", "scrollWheelZoom", "boxZoom", "keyboard", "tap"];
      let suspended = null, previousTouchAction, previousCursor, previewFrame = null;
      const current = () => alive && mapView === view && map === mountedMap;
      const listen = (target, name, fn, options) => { target.addEventListener(name, fn, options); listeners.push([target, name, fn, options]); };
      const stop = event => { event.preventDefault(); if (event.stopPropagation) event.stopPropagation(); };
      const suspend = () => {
        if (suspended) return;
        suspended = handlers.map(name => mountedMap[name]).filter(handler => handler && typeof handler.enabled === "function" && typeof handler.disable === "function" && typeof handler.enable === "function").map(handler => ({ handler, enabled: handler.enabled() }));
        suspended.forEach(({ handler }) => handler.disable());
        if (node.style) { previousTouchAction = node.style.touchAction; previousCursor = node.style.cursor; node.style.touchAction = "none"; node.style.cursor = "crosshair"; }
      };
      const restore = () => {
        if (!suspended) return;
        suspended.forEach(({ handler, enabled }) => enabled ? handler.enable() : handler.disable()); suspended = null;
        if (node.style) { node.style.touchAction = previousTouchAction; node.style.cursor = previousCursor; }
      };
      const sync = () => {
        const owned = ["is-drawing", "is-moving", "is-resizing", "is-polygon", "is-editing-vertex"], modeClass = view.mode && `is-${view.mode === "draw" ? "drawing" : view.mode === "move" ? "moving" : view.mode === "resize" ? "resizing" : view.mode === "vertex" ? "editing-vertex" : "polygon"}`;
        node.className = [...node.className.split(/\s+/).filter(name => !owned.includes(name)), modeClass].filter(Boolean).join(" ");
        for (const [control, mode] of [[view.draw, "draw"], [view.move, "move"], [view.resize, "resize"], [view.polygonButton, "polygon"]]) control.setAttribute("aria-pressed", String(view.mode === mode));
        view.cancelButton.hidden = !view.mode; view.radius.disabled = view.radiusNumber.disabled = Boolean(view.mode);
        view.undo.hidden = view.apply.hidden = !view.polygonDraft; view.undo.disabled = !view.polygonDraft || !view.polygonDraft.length; view.apply.disabled = !view.polygonDraft || view.polygonDraft.length < 3;
      };
      view.sync = sync;
      const release = () => {
        const gesture = view.gesture; view.gesture = null;
        if (gesture && typeof node.releasePointerCapture === "function") { try { if (!node.hasPointerCapture || node.hasPointerCapture(gesture.id)) node.releasePointerCapture(gesture.id); } catch (_) { /* Capture may already be released by the browser. */ } }
      };
      const cancelPreviewFrame = () => { if (previewFrame !== null) { global.cancelAnimationFrame(previewFrame); previewFrame = null; } };
      const paintPreview = () => {
        if (typeof global.requestAnimationFrame !== "function" || typeof global.cancelAnimationFrame !== "function") { updateMapView(); return; }
        if (previewFrame === null) previewFrame = global.requestAnimationFrame(() => { previewFrame = null; if (current() && (view.gesture && view.draft || view.polygonDraft)) updateMapView(); });
      };
      view.cancel = (message = "Area edit cancelled. The previous area is retained.") => {
        cancelPreviewFrame(); release(); view.draft = null; view.polygonDraft = null; view.polygonPreview = null; view.mode = null; restore(); sync();
        if (current()) { view.status.textContent = message; updateMapView(); }
      };
      view.arm = mode => {
        if (!current()) return;
        view.cancel(""); view.mode = mode; if (mode === "polygon") view.polygonDraft = state.areaType === "polygon" && state.polygon ? state.polygon.map(point => ({ ...point })) : []; suspend(); sync(); updateMapView();
        view.status.textContent = mode === "draw" ? "Drawing enabled. Press the map at the center, drag outward, then release to select. Escape or Cancel keeps the previous area." : mode === "move" ? "Move enabled. Drag on the map to place the center, then release. Escape or Cancel keeps the previous area." : mode === "resize" ? "Resize enabled. Drag from the circle edge outward or inward, then release. Escape or Cancel keeps the previous area." : "Polygon drawing enabled. Tap to add vertices; move to preview the next edge. Apply area to finish, or Cancel to keep the previous area.";
      };
      const eventCenter = event => { try { return mapCenter(mountedMap.mouseEventToLatLng(event)); } catch (_) { return null; } };
      const handleTarget = (marker, target) => { const element = marker && typeof marker.getElement === "function" && marker.getElement(); return element && inside(element, target); };
      const down = event => {
        if (!current()) return;
        if (view.gesture) { if (event.pointerId !== view.gesture.id) { stop(event); view.cancel("Multiple pointers cancelled the edit. The previous area is retained."); } return; }
        const vertexIndex = view.polygonVertices.findIndex(marker => handleTarget(marker, event.target));
        const mode = vertexIndex >= 0 ? "vertex" : view.mode || (state.areaType === "circle" && handleTarget(view.marker, event.target) ? "move" : state.areaType === "circle" && handleTarget(view.resizeMarker, event.target) ? "resize" : null);
        if (!mode || event.button !== undefined && event.button !== 0) return;
        if (event.isPrimary === false) { stop(event); view.cancel("Use one pointer to edit the area."); return; }
        const point = eventCenter(event);
        if (!point || !Number.isFinite(event.clientX) || !Number.isFinite(event.clientY) || !Number.isFinite(event.pointerId)) { view.cancel("The pointer location could not be read. The previous area is retained."); return; }
        stop(event);
        if (mode === "polygon") { if (view.polygonDraft.length >= 64) { view.status.textContent = "Polygon limit is 64 vertices. Apply or undo a vertex."; return; } view.polygonDraft.push(point); view.polygonPreview = null; sync(); updateMapView(); view.status.textContent = `${view.polygonDraft.length} polygon vertices. Add another point or Apply area; Undo removes the last vertex.`; return; }
        if (mode === "vertex") { if (!view.polygonDraft) view.polygonDraft = state.polygon.map(vertex => ({ ...vertex })); view.mode = "vertex"; suspend(); sync(); }
        else if (!view.mode) { view.mode = mode; suspend(); sync(); }
        const committed = { center: state.center || view.data.subject, radius: state.radius };
        view.gesture = { id: event.pointerId, mode, vertexIndex, x: event.clientX, y: event.clientY, start: point, committed, moved: false };
        try { if (typeof node.setPointerCapture !== "function") throw new Error("Pointer capture unavailable"); node.setPointerCapture(event.pointerId); }
        catch (_) { view.cancel("Pointer capture is unavailable. Use the radius controls to adjust the area."); return; }
      };
      const preview = event => {
        const gesture = view.gesture;
        if (current() && !gesture && view.mode === "polygon" && view.polygonDraft) { const hover = eventCenter(event); if (hover) { view.polygonPreview = hover; paintPreview(); } return false; }
        if (!current() || !gesture || event.pointerId !== gesture.id) return false;
        stop(event); const point = eventCenter(event); if (!point || !Number.isFinite(event.clientX) || !Number.isFinite(event.clientY)) return false;
        if (Math.hypot(event.clientX - gesture.x, event.clientY - gesture.y) < 8 && !gesture.moved) return false;
        if (gesture.mode === "vertex") { gesture.moved = true; view.polygonDraft[gesture.vertexIndex] = point; paintPreview(); view.status.textContent = `Vertex ${gesture.vertexIndex + 1} preview. Release, then Apply area; Cancel retains the previous polygon.`; return true; }
        const center = gesture.mode === "draw" ? gesture.start : gesture.mode === "move" ? point : gesture.committed.center;
        const measured = gesture.mode === "move" ? gesture.committed.radius : distanceKm(center, point);
        if (measured === null || measured < MIN_RADIUS_KM) return false;
        gesture.moved = true; view.draft = { center, radius: boundedRadius(measured) }; paintPreview();
        view.status.textContent = `Preview · radius ${view.draft.radius.toFixed(2)} km. Release to select; Escape or Cancel retains the previous area.`; return true;
      };
      const up = event => {
        if (!current() || !view.gesture || event.pointerId !== view.gesture.id) return;
        preview(event); stop(event); const draft = view.draft, gesture = view.gesture;
        if (gesture.mode === "vertex") { release(); view.mode = "polygon"; sync(); updateMapView(); view.status.textContent = gesture.moved ? "Vertex moved. Apply area to keep the edit, or Cancel to retain the previous polygon." : "Vertex unchanged. Apply area or Cancel."; return; }
        const finalPoint = eventCenter(event), finalDistance = finalPoint && (gesture.mode === "move" ? gesture.committed.radius : distanceKm(gesture.mode === "draw" ? gesture.start : gesture.committed.center, finalPoint));
        if (!gesture.moved || !draft || !finalPoint || finalDistance === null || finalDistance < MIN_RADIUS_KM || !Number.isFinite(event.clientX) || !Number.isFinite(event.clientY) || Math.hypot(event.clientX - gesture.x, event.clientY - gesture.y) < 8) { view.cancel("No area change: drag at least 8 pixels and use a radius of at least 0.1 km."); return; }
        state.center = { ...draft.center }; state.radius = draft.radius; state.areaType = "circle"; state.polygon = null;
        view.cancel(`Area selected · radius ${state.radius.toFixed(2)} km. Drag a handle or choose Draw area to edit.`);
      };
      const cancelled = event => { if (view.gesture && event.pointerId === view.gesture.id) view.cancel("Pointer interrupted. The previous area is retained."); };
      listen(node, "pointerdown", down, true); listen(node, "pointermove", preview, true); listen(node, "pointerup", up, true); listen(node, "pointercancel", cancelled, true); listen(node, "lostpointercapture", cancelled, true);
      listen(doc, "pointerdown", event => { if (current() && view.gesture && event.pointerId !== view.gesture.id) view.cancel("Multiple pointers cancelled the edit. The previous area is retained."); }, true);
      listen(doc, "visibilitychange", () => { if (doc.hidden && current() && view.mode) view.cancel(); });
      if (typeof global.addEventListener === "function") listen(global, "blur", () => { if (current() && view.mode) view.cancel(); });
      // Keyboard activation makes the map handles' intent explicit; radius can always be edited in the labelled inputs.
      for (const [marker, mode] of [[view.marker, "move"], [view.resizeMarker, "resize"]]) {
        const element = typeof marker.getElement === "function" && marker.getElement();
        if (element) { element.setAttribute("role", "button"); element.setAttribute("aria-label", mode === "move" ? "Drag area center, or press Enter to enable moving" : "Drag radius handle, or use Area radius in kilometres"); listen(element, "keydown", event => { if (event.key === "Enter" || event.key === " ") { stop(event); view.arm(mode); } }); }
      }
      view.cleanup = () => { view.cancel(""); for (const [target, name, fn, options] of listeners) if (typeof target.removeEventListener === "function") target.removeEventListener(name, fn, options); };
      sync();
    }
    function updateMapView() {
      if (!mapView) return;
      const { data, draft } = mapView, center = draft ? draft.center : state.center || data.subject || {}, radius = draft ? draft.radius : state.radius, available = candidates(data, true), activeType = mapView.polygonDraft ? "polygon" : state.areaType, areaRows = selectedMapCandidates(data, true, true), rows = selectedMapCandidates(data, true);
      const selected = rows.some(row => typeof row.selected === "boolean") || !rows.length ? rows.filter(row => row.selected === true).length : "Unknown";
      const provisional = rows.some(row => present(row.eligibility) || present(row.status)) || !rows.length ? rows.filter(row => row.eligibility === "provisional" || row.status === "provisional").length : "Unknown";
      const unknownDecisions = rows.filter(row => typeof row.selected !== "boolean" && !present(row.eligibility) && !present(row.status)).length;
      const unlocated = available.filter(row => distanceKm(row, row) === null).length;
      mapView.count.textContent = `${rows.length} observed candidates ${activeType === "all" ? "with coordinates" : activeType === "polygon" ? "inside polygon" : `inside this ${Number(radius.toFixed(2))} km view`}${draft || mapView.polygonDraft ? " · preview" : ""}`; mapView.radius.value = mapView.radiusNumber.value = String(Number(radius.toFixed(2))); mapView.move.disabled = mapView.resize.disabled = state.areaType !== "circle" && !mapView.mode;
      mapView.metrics.replaceChildren(facts([["Observed candidates", rows.length], ["Saved selected", selected], ["Saved provisional", provisional], ["Decision evidence missing", unknownDecisions], ["Area candidates", areaRows.length], ["Locally excluded", areaRows.length - rows.length], ["Area", activeType === "polygon" ? `${polygonAreaKm2(mapView.polygonDraft || state.polygon).toFixed(2)} km² polygon` : activeType === "all" ? "All located points" : `${radius.toFixed(2)} km radius`], ...(activeType === "circle" ? [["Radius", `${radius.toFixed(2)} km`], ["Circle area", `${(Math.PI * radius ** 2).toFixed(2)} km²`]] : []), ["Available candidates without coordinates", unlocated]]));
      if (map && mapView.circle) {
        mapView.circle.setLatLng([center.latitude, center.longitude]).setRadius(radius * 1000); mapView.marker.setLatLng([center.latitude, center.longitude]); mapView.resizeMarker.setLatLng(radiusEdge(center, radius));
        if (typeof mapView.circle.setStyle === "function") mapView.circle.setStyle({ opacity: activeType === "circle" ? 1 : 0, fillOpacity: activeType === "circle" ? .07 : 0 });
        for (const marker of [mapView.marker, mapView.resizeMarker]) if (typeof marker.setOpacity === "function") marker.setOpacity(activeType === "circle" ? 1 : 0);
        const vertices = mapView.polygonDraft || state.areaType === "polygon" && state.polygon || [];
        if (mapView.polygonLayer) mapView.polygonLayer.setLatLngs(vertices.length ? [...vertices, ...(mapView.polygonDraft && mapView.polygonPreview ? [mapView.polygonPreview] : [])].map(point => [point.latitude, point.longitude]) : []);
        if (typeof global.L.marker === "function") {
          for (let index = 0; index < vertices.length; index++) {
            let vertex = mapView.polygonVertices[index];
            if (!vertex) { const icon = typeof global.L.divIcon === "function" ? { icon: global.L.divIcon({ className: "dw-map-handle dw-map-vertex-handle", html: `<span aria-hidden="true">${index + 1}</span>`, iconSize: [44, 44], iconAnchor: [22, 22] }) } : {};
              vertex = global.L.marker([vertices[index].latitude, vertices[index].longitude], { draggable: false, keyboard: true, title: `Drag polygon vertex ${index + 1}`, alt: `Drag polygon vertex ${index + 1}`, ...icon }).addTo(map); mapView.polygonVertices.push(vertex);
              const element = typeof vertex.getElement === "function" && vertex.getElement(); if (element) { element.setAttribute("role", "button"); element.setAttribute("aria-label", `Drag polygon vertex ${index + 1} to edit; Apply area to save`); }
            } else vertex.setLatLng([vertices[index].latitude, vertices[index].longitude]);
          }
          while (mapView.polygonVertices.length > vertices.length) { const vertex = mapView.polygonVertices.pop(); if (typeof vertex.remove === "function") vertex.remove(); else if (typeof map.removeLayer === "function") map.removeLayer(vertex); }
        }
        const keep = new Set();
        for (const row of rows) {
          const id = row.id || row.candidate_id; keep.add(id); let entry = mapView.points.get(id);
          if (!entry) {
            entry = { row, point: global.L.circleMarker([row.latitude, row.longitude], { radius: 6, color: row.selected === true ? "#087f8c" : "#697789", fillOpacity: .8 }).addTo(mapView.layer) };
            const observed = entry;
            entry.point.bindPopup(() => { const item = observed.row; return append(el("div"), el("strong", "", `${item.title || item.name || item.id}`), p(`${item.view_distance_km === null ? "Distance unknown" : `${item.view_distance_km.toFixed(2)} km`} · ${item.selected === true ? "Selected" : human(item.eligibility || item.status)}`), button("Inspect evidence", () => showCandidate(item))); });
            mapView.points.set(id, entry);
          } else { entry.row = row; entry.point.setLatLng([row.latitude, row.longitude]); }
        }
        for (const [id, entry] of mapView.points) if (!keep.has(id)) { mapView.layer.removeLayer(entry.point); mapView.points.delete(id); }
      }
      mapView.list.replaceChildren(...rows.slice(0, 8).map(row => button(`${row.title || row.name || row.id} · ${row.view_distance_km === null ? "distance unknown" : `${row.view_distance_km.toFixed(2)} km`}`, () => showCandidate(row), "dw-map-candidate")));
      mapView.page = Math.max(0, Math.min(mapView.page, Math.max(0, Math.ceil(areaRows.length / 25) - 1)));
      const pageStart = mapView.page * 25; mapView.pageBack.disabled = mapView.page === 0; mapView.pageNext.disabled = pageStart + 25 >= areaRows.length;
      mapView.pageLabel.textContent = `${areaRows.length ? pageStart + 1 : 0}–${Math.min(pageStart + 25, areaRows.length)} of ${areaRows.length} area candidates`;
      mapView.mapTable.body.replaceChildren(...areaRows.slice(pageStart, pageStart + 25).map(row => { const tr = el("tr"), id = row.id || row.candidate_id, checkbox = el("input"); checkbox.type = "checkbox"; checkbox.checked = !state.localExcluded.has(id); checkbox.setAttribute("aria-label", `Include ${row.title || row.name || id} in local map selection`); checkbox.addEventListener("change", () => { if (checkbox.checked) state.localExcluded.delete(id); else state.localExcluded.add(id); updateMapView(); }); return append(tr, append(el("td"), checkbox), append(el("td"), button(row.title || row.name || id, () => showCandidate(row), "dw-property-name")), el("td", "", row.selected === true ? "Selected" : human(row.eligibility || row.status)), el("td", "dw-number", row.view_distance_km === null ? "Unknown" : `${row.view_distance_km.toFixed(2)} km`), append(el("td"), button("Inspect →", () => showCandidate(row), "dw-text-button"))); }));
      mapView.note.textContent = `Candidate table pages through all ${areaRows.length} located points in this ${activeType === "polygon" ? "polygon" : activeType === "all" ? "unbounded map view" : "circle"}. Export map view includes all ${rows.length} locally included points. Saved decisions are unchanged.`;
    }
    function renderActivity() {
      const data = currentHotel();
      append(canvas, append(el("div", "dw-panel-heading"), el("h2", "", "Source activity")), p("Source time describes the evidence. Collection progress and generated time are separate.", "dw-context-note"));
      if (state.mode === "hotel") {
        const t = table(["Source", "Latest result", "Checked stay", "Observed", "Reason"], "Hotel source health");
        array(data.source_states).forEach(row => { const tr = el("tr"); append(tr, el("td", "", sourceName(row.source)), el("td", "", human(row.status)), el("td", "", summarize(row.last_stay)), el("td", "", stamp(row.observed_at)), el("td", "", human(row.reason))); t.body.appendChild(tr); }); canvas.appendChild(t.scroll);
      } else {
        const str = state.summary && state.summary.str || {}; canvas.appendChild(facts([["Portfolio observation", stamp(str.observed_at)], ["Collection scope", "Saved Dubai Airbnb comparison set only"], ["Direct-site records", "Remain separate from unlinked Airbnb records"], ["Saved coverage", str.summary], ["Warnings", str.warnings || state.summary && state.summary.warnings]]));
      }
      canvas.appendChild(p("Use the collection controls below to inspect current progress. A blocked or incomplete source is never retried automatically.", "dw-footnote"));
    }
    function renderImportedHotel() {
      const profile = selectedHotelProfile();
      append(canvas, append(el("div", "dw-panel-heading"), el("h2", "", profile.title || profile.name || "Imported hotel profile")),
        p("This is a configured Lighthouse account profile. Its presence does not provide current prices, availability or a verified comparison set.", "dw-context-note"),
        facts([["Profile identity", profile.id], ["City", profile.city], ["Country", profile.country], ["Room count", profile.room_count], ["Account roles", profile.roles], ["Observed", stamp(profile.observed_at)], ["Rate coverage", profile.rate_coverage], ["Collection", "Not configured for this profile"]]),
        append(el("div", "dw-profile-source"), link(profile.source_url, "Open profile source")));
      if (state.view === "compset") {
        const evidence = configuredGroup(configuredLabels(), profile.id), group = evidence.group;
        append(canvas, append(el("div", "dw-panel-heading"), append(el("div"), el("h2", "", "Configured comparison names"),
          p(evidence.count === null ? "Coverage unknown" : `${evidence.count} names saved for this hotel`))),
          p("Name only · OTA identities unverified. These account labels have no collected competitor prices or verified map locations.", "dw-context-note"));
        if (group) {
          append(canvas, facts([["Membership observed", stamp(group.observed_at)], ["Identity status", "Name only · unresolved"]]),
            append(el("div", "dw-profile-source"), link(group.source_url, "Open membership source")));
          const t = table(["Configured name", "Identity evidence", "Dated rates"], "Configured competitor names");
          evidence.labels.forEach(label => t.body.appendChild(append(el("tr"), el("td", "", label), el("td", "", "OTA unverified"), el("td", "", "Not collected"))));
          canvas.appendChild(t.scroll);
          if (!evidence.count) canvas.appendChild(empty("The observed group contains no configured names."));
        } else canvas.appendChild(empty(evidence.status === "read_error" ? "Configured comparison names could not be validated." : "No configured comparison-name observation is saved for this hotel."));
      } else if (state.view === "map") canvas.appendChild(empty("Map locations are unknown for these configured names. No locations or distances have been inferred."));
      else canvas.appendChild(append(el("div", "dw-panel-heading"), button("View configured comparison names →", () => navigate("hotel", "compset"))));
      canvas.appendChild(empty("No dated rate dataset is linked to this profile. Fresh collection is disabled here; any existing job keeps its original identity and pause/resume controls."));
    }
    function renderView() {
      if (!alive) return; const activeBefore = doc.activeElement, focused = activeBefore && activeBefore.getAttribute("aria-label"), caret = activeBefore && activeBefore.selectionStart;
      const mapPage = state.view === "map" && !(state.mode === "hotel" && selectedHotelProfile());
      if (!mapPage) removeMap(); renderNavigation(); renderHeading(); renderCoverage(); renderToolbar();
      if (controls.has(focused)) { controls.get(focused).focus(); if (typeof controls.get(focused).setSelectionRange === "function" && Number.isInteger(caret)) controls.get(focused).setSelectionRange(caret, caret); }
      if (pendingFocusFallback || activeBefore && activeBefore !== doc.body && !activeBefore.isConnected && !controls.has(focused)) { pendingFocusFallback = false; const fallback = heading.querySelectorAll("button")[0]; if (fallback) fallback.focus(); }
      alerts.replaceChildren(); if (state.error) { const message = p(state.error, "dw-error"); message.setAttribute("role", "alert"); alerts.appendChild(message); }
      if (state.loading) alerts.appendChild(p("Loading saved evidence…", "dw-loading"));
      if (!mapPage) canvas.replaceChildren(); canvas.className = `dw-canvas${mapPage ? " dw-map-view" : ""}`;
      if (!state.summary) { canvas.appendChild(empty("Saved portfolio evidence will appear here when the local service is available.")); return; }
      if (state.mode === "hotel" && selectedHotelProfile()) { canvas.className = "dw-canvas"; renderImportedHotel(); return; }
      if (state.view === "compset") renderComparison(); else if (state.view === "map") renderMap(); else if (state.view === "activity") renderActivity(); else if (state.mode === "hotel") renderHotel(); else renderStrCalendar();
      if (state.mode === "hotel" && state.view === "table" && controls.has(focused)) { const replacement = controls.get(focused); replacement.focus(); if (typeof replacement.setSelectionRange === "function" && Number.isInteger(caret)) replacement.setSelectionRange(caret, caret); }
      syncDetailMode();
    }
    function cancelRead(owner, keepUrl = null) {
      const entry = readOwners.get(owner); if (!entry || entry.url === keepUrl) return;
      readOwners.delete(owner); entry.owners.delete(owner);
      if (!entry.owners.size) { if (entry.controller) entry.controller.abort(); if (pendingReads.get(entry.url) === entry) pendingReads.delete(entry.url); }
    }
    function cancelReads() {
      readEpoch++; for (const entry of pendingReads.values()) if (entry.controller) entry.controller.abort(); pendingReads.clear(); readOwners.clear();
    }
    function cacheRead(url, data) {
      cache.delete(url); cache.set(url, data);
      if (cache.size > 24) cache.delete(cache.keys().next().value);
    }
    function get(url, owner = "view") {
      cancelRead(owner, url);
      if (cache.has(url)) { const data = cache.get(url); cacheRead(url, data); return Promise.resolve(data); }
      let entry = pendingReads.get(url);
      if (!entry) {
        entry = { url, epoch: readEpoch, controller: typeof global.AbortController === "function" ? new global.AbortController() : null, owners: new Set() };
        pendingReads.set(url, entry);
        const check = () => { if (!alive || entry.epoch !== readEpoch || entry.controller && entry.controller.signal.aborted) { const error = new Error("Saved read superseded"); error.name = "AbortError"; throw error; } };
        entry.promise = Promise.resolve().then(async () => {
          check();
          const response = await global.fetch(url, { method: "GET", cache: "no-store", credentials: "same-origin", headers: { Accept: "application/json" }, ...(entry.controller ? { signal: entry.controller.signal } : {}) });
          check();
          if (!response.ok) throw new Error(response.status === 404 ? "Restart CompSet Studio to activate the updated local workspace service. Your saved data is retained." : `Saved evidence returned HTTP ${response.status}.`);
          const data = await response.json(); check();
          if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("Saved evidence has an unsupported format.");
          return data;
        }).finally(() => {
          if (pendingReads.get(url) === entry) pendingReads.delete(url);
          for (const name of entry.owners) if (readOwners.get(name) === entry) readOwners.delete(name);
        });
      }
      entry.owners.add(owner); readOwners.set(owner, entry); return entry.promise;
    }
    async function loadView() {
      if (!alive || !state.summary) { renderView(); return; }
      const sequence = ++viewSequence, mode = state.mode, view = state.view;
      let url = null;
      if (mode === "hotel") url = "/api/intelligence/hotel";
      else if (view === "calendar") url = calendarQuery(state);
      else if (["compset", "map"].includes(view) && state.subject) url = `/api/intelligence/str/compset?subject_id=${encodeURIComponent(state.subject)}&offset=${state.candidatePage * 25}&limit=25${state.decision !== "all" ? `&decision=${encodeURIComponent(state.decision)}` : ""}`;
      cancelRead("view", url); cancelRead("detail"); detailSequence++;
      const cached = url && cache.has(url);
      if (!cached) {
        if (mode === "str" && view === "calendar") state.calendar = null;
        const sameMapSubject = view === "map" && mapView && (mapView.data.subject_id || mapView.data.subject && mapView.data.subject.id) === state.subject;
        // Compact map_points contain this subject's full observed point set. A local decision
        // filter can keep that same-revision map while its paged audit request refreshes.
        if (mode === "str" && ["compset", "map"].includes(view) && !sameMapSubject) state.comparison = null;
      }
      state.loading = Boolean(url && !cached); state.error = null;
      if (!cached) renderView();
      try {
        if (!url) return;
        const data = await get(url); if (!alive || sequence !== viewSequence || mode !== state.mode || view !== state.view) return;
        if (data.revision && state.summary.revision && data.revision !== state.summary.revision) throw new Error("Saved sources changed during this view. Reload saved data to use one consistent revision.");
        if (mode === "hotel") { if (!data.dataset || !Array.isArray(data.dataset.cells)) throw new Error("Hotel evidence is missing its saved dataset."); state.hotel = data; }
        else if (view === "calendar") {
          if (!Array.isArray(data.entities) || !Array.isArray(data.cells) || !Array.isArray(data.dates)) throw new Error("Calendar evidence has an unsupported format.");
          if (data.dates.length !== state.days || data.dates.some((day, index) => day !== addDays(state.start, index))) throw new Error("Calendar returned different date columns.");
          if (!data.request || data.request.start !== state.start || Number(data.request.days) !== state.days || Number(data.request.offset) !== state.offset || (data.request.namespace || "all") !== state.namespace || (data.request.city || "all") !== state.city || (data.request.currency || "all") !== state.currency || String(data.request.bedrooms ?? "all") !== state.bedrooms || (data.request.query || "") !== state.query.trim().replace(/\s+/g, " ")) throw new Error("Calendar returned different dates, filters or property page.");
          state.calendar = data;
        } else {
          const subjectId = data.subject_id || data.subject && data.subject.id;
          if (subjectId !== state.subject || !Array.isArray(data.candidates) || !data.request || data.request.offset !== state.candidatePage * 25 || (data.request.decision || "all") !== state.decision) throw new Error("Comparison evidence returned a different subject or candidate page.");
          const sameSubject = state.comparison && (state.comparison.subject_id || state.comparison.subject && state.comparison.subject.id) === subjectId;
          state.comparison = data; if (!sameSubject) state.radius = boundedRadius(data.criteria && data.criteria.radius_km) ?? 2;
        }
        cacheRead(url, data);
      } catch (error) { if (alive && sequence === viewSequence && error.name !== "AbortError") state.error = `Could not load saved evidence. ${error.message}`; }
      finally { if (alive && sequence === viewSequence) { state.loading = false; renderView(); } }
    }
    async function refresh() {
      if (!alive) return; if (mapView && mapView.cancel) mapView.cancel(); const sequence = ++summarySequence; ++viewSequence; closeDetail(false); cancelReads(); cache.clear(); state.loading = true; state.error = null; renderView();
      let viewRendered = false;
      try {
        const data = await get("/api/intelligence", "summary"); if (!alive || sequence !== summarySequence) return;
        if (!data.str || !Array.isArray(data.str.properties)) throw new Error("Portfolio summary has an unsupported format.");
        // Navigation can read/cache the previous revision while this summary is pending.
        // Accepting the summary is a new read boundary, including those intervening reads.
        ++viewSequence; closeDetail(false); cancelReads(); cache.clear();
        state.summary = data; state.calendar = null; state.hotel = null; state.comparison = null;
        if (state.hotelProfile !== "aketa" && !selectedHotelProfile()) state.hotelProfile = "aketa";
        syncCollectionScope();
        if (!state.start) state.start = isoDate(data.str.default_start) || isoDate(data.str.calendar_bounds && data.str.calendar_bounds.start) || new Date().toISOString().slice(0, 10);
        if (!allSubjects().some(s => (s.subject_id || s.id) === state.subject)) {
          state.subject = allSubjects()[0] && (allSubjects()[0].subject_id || allSubjects()[0].id);
          state.center = null; state.radius = 2; state.areaType = "circle"; state.polygon = null; state.localExcluded = new Set(); state.candidatePage = 0; removeMap();
        }
        await loadView(); viewRendered = true;
      } catch (error) { if (alive && sequence === summarySequence && error.name !== "AbortError") state.error = `Could not reload saved evidence. ${error.message}`; }
      finally { if (alive && sequence === summarySequence) { state.loading = false; if (!viewRendered) renderView(); } }
    }
    function exportCurrent() {
      if (mapView && mapView.mode && mapView.cancel) mapView.cancel("Area preview cancelled. Export contains the committed selected area.");
      let csv;
      if (state.mode === "hotel" && selectedHotelProfile()) { const profile = selectedHotelProfile(); csv = state.view === "compset" ? configuredCsv(profile, configuredLabels()) : [["profile_id", "title", "city", "country", "roles", "rate_coverage", "observed_at", "source_url"], [profile.id, profile.title, profile.city, profile.country, profile.roles, profile.rate_coverage, profile.observed_at, shared.safeUrl(profile.source_url)]].map(row => row.map(shared.csvField).join(",")).join("\r\n"); }
      else if (["compset", "map"].includes(state.view)) { const data = currentComparison() || {}, raw = candidates(data, state.view === "map"), rows = state.view === "map" ? selectedMapCandidates(data) : state.mode === "hotel" ? raw.slice(state.candidatePage * 25, state.candidatePage * 25 + 25) : raw; csv = [["subject_id", "candidate_id", "title", "decision", "distance_km", "view_distance_km", "missing_fields", "reasons", "source_url", "observed_at"], ...rows.map(row => [data.subject_id || data.subject && data.subject.id, row.id || row.candidate_id, row.title || row.name, row.selected ? "selected" : row.eligibility || row.status, row.distance_km, row.view_distance_km, row.missing_fields, row.rejection_reasons || row.reasons, shared.safeUrl(row.source_url || row.url), row.observed_at])].map(row => row.map(shared.csvField).join(",")).join("\r\n"); }
      else if (state.view === "activity") { const rows = state.mode === "hotel" ? array(currentHotel().source_states) : [{ source: "bnbme_direct", status: "saved_source_evidence", observed_at: state.summary && state.summary.observed_at, reason: "Collection scope is the saved Dubai Airbnb comparison set; direct-site records remain separate." }]; csv = [["source", "status", "checked_stay", "observed_at", "reason"], ...rows.map(row => [row.source, row.status, row.last_stay, row.observed_at, row.reason])].map(row => row.map(shared.csvField).join(",")).join("\r\n"); }
      else if (state.mode === "hotel") { const rows = hotelView(currentHotel(), state); csv = exportRows(mobile() && state.view === "calendar" ? rows.map(row => ({ ...row, cells: row.cells.filter(cell => cell.date === state.hotelDay) })) : rows, currentHotel().context); }
      else csv = exportRows(calendarView(state.calendar || {}, { day: mobile() ? state.day : null, evidence: state.evidence }), { view_request: state.calendar && state.calendar.request, source_context: state.calendar && state.calendar.source_context });
      if (!global.Blob || !global.URL || !global.URL.createObjectURL) { detail("Export preview", [["Scope", "Current saved view"]], [], el("pre", "dw-export-preview", csv)); return; }
      const url = global.URL.createObjectURL(new global.Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" })); const a = el("a"); a.href = url; a.download = `compset-${state.mode}-${state.view}.csv`; root.appendChild(a); a.click(); a.remove(); global.URL.revokeObjectURL(url);
    }
    const keyboard = event => {
      if (event.key === "Escape" && mapView && mapView.mode && mapView.cancel) { event.preventDefault(); mapView.cancel(); return; }
      if (inspector.hidden) return;
      if (event.key === "Escape") { event.preventDefault(); closeDetail(); }
      else if (event.key === "Tab" && modalDetail()) {
        const nodes = detailFocusables(), first = nodes[0], last = nodes[nodes.length - 1];
        if (!first) return;
        if (!nodes.includes(doc.activeElement) || event.shiftKey && doc.activeElement === first || !event.shiftKey && doc.activeElement === last) { event.preventDefault(); (event.shiftKey ? last : first).focus(); }
      }
    };
    const focusEntered = event => { if (modalDetail() && !inside(inspector, event.target)) { const first = detailFocusables()[0]; if (first) first.focus(); } };
    const resized = () => { if (!alive) return; renderView(); syncDetailMode(); if (map) map.invalidateSize(); };
    const watch = (media, remove = false) => { if (typeof media.addEventListener === "function") media[remove ? "removeEventListener" : "addEventListener"]("change", resized); else if (typeof media.addListener === "function") media[remove ? "removeListener" : "addListener"](resized); };
    watch(mobileMedia); watch(overlayMedia); doc.addEventListener("keydown", keyboard); doc.addEventListener("focusin", focusEntered); renderView();
    if (rates && typeof rates.mountCollection === "function") bridge = rates.mountCollection(collection, { datasetId: "airbnb-compset", onReload: refresh });
    else collection.appendChild(p("Collection controls need the updated local service. Reload saved data remains read-only.", "dw-context-note"));
    const ready = Promise.all([refresh(), bridge && bridge.ready]).then(() => undefined);
    return { root, ready, refresh, destroy() { alive = false; summarySequence++; viewSequence++; cancelReads(); removeMap(); watch(mobileMedia, true); watch(overlayMedia, true); if (searchTimer) global.clearTimeout(searchTimer); if (bridge) bridge.destroy(); doc.removeEventListener("keydown", keyboard); doc.removeEventListener("focusin", focusEntered); closeDetail(false); }, getState: () => ({ ...state }) };
  }
  const api = { mount, refresh: () => active ? active.refresh() : Promise.resolve(), destroy: () => { if (active) active.destroy(); active = null; }, model: Object.freeze({ isoDate, addDays, dateLabel, amount, stateOf, priceLabel, calendarQuery, calendarView, filteredOfferCell, hotelView, exportRows, configuredGroup, configuredCsv, distanceKm, mapCandidates, polygonAreaKm2, validPolygon, pointInPolygon, polygonCandidates }) };
  global.CompSetDual = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window === "undefined" ? globalThis : window);
