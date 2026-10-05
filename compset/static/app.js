"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const form = $("collection-form");
  const filters = Array.from(document.querySelectorAll("[data-filter]"));
  const candidateFilters = Array.from(document.querySelectorAll("[data-candidate-filter]"));
  const exportPaths = { "export-calendar": "/exports/calendar.csv", "export-quotes": "/exports/quotes.csv", "export-result": "/exports/result.json" };
  let snapshot = null;
  let activeFilter = "all";
  let jobState = "idle";
  let timer = null;
  let requestPending = false;
  let monitoring = false;
  let compSet = null;
  let candidateFilter = "all";
  let candidatePage = 0;
  let activeJob = null;
  let searchMap = null;
  let searchCircle = null;
  let centerMarker = null;
  let candidateLayer = null;
  let cellLayer = null;
  let subjectMarker = null;
  let mapMarkers = new Map();
  let centerEdited = false;
  let formEdited = false;
  let subjectCenter = [25.1929, 55.2716];
  let portfolio = null;
  let inventoryEdited = false;
  let portfolioPage = 0;
  let activeView = "rates";
  let pauseRequested = false;
  let oneNightCells = [];
  let oneNightPage = 0;
  let hotelSnapshot = null;
  let legacyInitialized = false;

  const isPresent = (value) => value !== undefined && value !== null && value !== "";
  const text = (value, fallback = "Unknown") => isPresent(value) ? String(value) : fallback;
  const count = (value) => Number.isInteger(value) && value >= 0 ? String(value) : "—";
  const numberValue = (value) => Number.isFinite(Number(value)) && isPresent(value) ? Number(value) : null;
  const make = (tag, className, value) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = text(value, "");
    return node;
  };

  function dateInput(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  }

  function localDate(value) {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
    const [year, month, day] = value.split("-").map(Number);
    const date = new Date(year, month - 1, day);
    return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : null;
  }

  function dateDisplay(value, includeYear = true) {
    const date = localDate(value);
    return date ? date.toLocaleDateString(undefined, { day: "numeric", month: "short", ...(includeYear ? { year: "numeric" } : {}) }) : text(value);
  }

  function money(amount, currency, fallback) {
    // Decimal strings are displayed directly: no stay-total division or rounding.
    if (isPresent(amount)) return `${text(currency, "")} ${text(amount)}`.trim();
    return text(fallback, "Not observed");
  }

  function availability(row) {
    if (row.reason === "not_observed") return "missing";
    if (row.availability === "available" || row.availability === "unavailable" || row.availability === "unknown") return row.availability;
    if (row.available === true) return "available";
    if (row.available === false) return "unavailable";
    return "unknown";
  }

  function setDefaults() {
    const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Dubai", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
    const fields = Object.fromEntries(parts.map(part => [part.type, part.value]));
    const today = localDate(`${fields.year}-${fields.month}-${fields.day}`);
    const checkin = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 14);
    const checkout = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 17);
    $("checkin").value = dateInput(checkin);
    $("checkout").value = dateInput(checkout);
    $("start-date").value = dateInput(today);
    $("adults").value = "1";
    $("days").value = "30";
    $("inventory-adults").value = "1";
    $("inventory-checkin").value = dateInput(checkin);
    $("inventory-checkout").value = dateInput(checkout);
  }

  function setBusy(busy) {
    for (const input of form.querySelectorAll("input, button")) input.disabled = busy;
    for (const id of ["radius", "center-lat", "center-lng", "subject-center-button"]) $(id).disabled = busy;
    $("run-button-label").textContent = busy && activeJob === "subject" ? "Collecting subject…" : "Refresh subject snapshot";
    $("discover-button-label").textContent = busy ? activeJob === "discover" ? "Discovering competitor set…" : "Job in progress…" : "Discover competitor set";
    $("monitor-button").disabled = busy || selectedCandidates().length === 0;
    $("monitor-button").textContent = busy && activeJob === "monitor" ? "Refreshing calendars & prices…" : "Refresh selected calendars & prices ↻";
    if (centerMarker && centerMarker.dragging) busy ? centerMarker.dragging.disable() : centerMarker.dragging.enable();
    for (const id of ["inventory-checkin", "inventory-checkout", "inventory-adults", "inventory-refresh-button"]) $(id).disabled = busy;
    $("inventory-refresh-button").textContent = busy && activeJob === "inventory" ? "Inventory collection in progress…" : "Start / resume inventory collection →";
    $("inventory-pause-button").disabled = !busy || pauseRequested || (activeJob !== null && activeJob !== "inventory");
    if (!busy) { pauseRequested = false; $("inventory-pause-button").textContent = "Pause inventory refresh"; }
    form.setAttribute("aria-busy", String(busy));
  }

  function setStatus(state, message) {
    jobState = state;
    const labels = { idle: "Ready to collect", running: "Collection in progress", complete: "Collection complete", partial: "Partial collection", failed: "Collection failed", paused: "Collection paused", stopped: "Collection stopped", interrupted: "Collection interrupted" };
    $("job-badge").className = `job-badge ${state}`;
    $("job-label").textContent = labels[state] || "Unknown collection state";
    $("job-message").textContent = text(message, labels[state] || "Unknown state");
    setBusy(state === "running" || requestPending);
  }

  function connectionError(message) {
    $("connection-error-text").textContent = message;
    $("connection-error").hidden = false;
  }

  async function api(path, options = {}, allowMissing = false) {
    const response = await fetch(path, { cache: "no-store", ...options });
    if (allowMissing && response.status === 404) return null;
    let body;
    try { body = await response.json(); }
    catch { throw new Error(`The local service returned an unreadable response (${response.status}).`); }
    if (!response.ok) throw new Error(text(body.error || body.message, `Request failed (${response.status}).`));
    return body;
  }

  function renderListing(result) {
    const listing = result.listing || {};
    const context = result.context || {};
    if (!formEdited && !compSet) restoreContext(context);
    $("snapshot-title").textContent = text(listing.title || listing.name, `Listing ${text(context.listing_id, "snapshot")}`);
    const stay = isPresent(context.checkin) && isPresent(context.checkout) ? `${dateDisplay(context.checkin)} – ${dateDisplay(context.checkout)}` : "Stay dates unknown";
    const adults = isPresent(context.adults) ? `${context.adults} ${Number(context.adults) === 1 ? "adult" : "adults"}` : "Guest count unknown";
    $("snapshot-description").textContent = `${stay} · ${adults} · ${text(context.currency, "Currency unknown")}`;
    $("snapshot-badge").textContent = "Saved observation";
    const facts = $("listing-facts");
    facts.replaceChildren();
    for (const [key, label] of [["bedrooms", "bedrooms"], ["beds", "beds"], ["bathrooms", "bathrooms"], ["person_capacity", "guest capacity"]]) {
      if (isPresent(listing[key])) facts.append(make("span", "", `${text(listing[key])} ${label}`));
    }
    facts.hidden = facts.childElementCount === 0;
    const observed = new Date(context.observed_at);
    $("observed-at").textContent = isPresent(context.observed_at) && !Number.isNaN(observed.getTime()) ? `Observed ${observed.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}` : "Observation time not provided";
    const sourceLink = $("source-link");
    // Only a known public listing destination is used; source text cannot set URLs.
    const listingId = text(context.listing_id, "");
    sourceLink.hidden = !/^\d+$/.test(listingId);
    if (!sourceLink.hidden) sourceLink.href = `https://www.airbnb.com/rooms/${listingId}`;
    else sourceLink.removeAttribute("href");
    const coordinates = listingCoordinates(listing);
    if (coordinates) {
      subjectCenter = coordinates;
      if (!centerEdited && !compSet) setMapCenter(coordinates, false);
      renderSubjectMarker(listing);
    }
  }

  function renderCoverage(result) {
    const coverage = result.coverage || {};
    for (const [id, key] of [["observed", "observed_days"], ["available", "available_days"], ["unavailable", "unavailable_days"], ["unknown", "unknown_days"], ["missing", "missing_days"], ["priced", "priced_days"]]) {
      $("metric-" + id).textContent = count(coverage[key]);
    }
    $("metric-requested").textContent = Number.isInteger(coverage.requested_days) ? `of ${coverage.requested_days} requested dates` : "requested count not provided";
    const requested = numberValue(coverage.requested_days);
    const observed = numberValue(coverage.observed_days);
    $("coverage-track-fill").style.width = requested && observed !== null ? `${Math.min(100, Math.max(0, observed / requested * 100))}%` : "0%";
    const context = result.context || {};
    const endDate = localDate(context.end_date);
    if (endDate) endDate.setDate(endDate.getDate() - 1);
    $("coverage-context").textContent = isPresent(context.start_date) && endDate ? `${dateDisplay(context.start_date)} – ${dateDisplay(dateInput(endDate))}` : "Window dates not provided";
  }

  function renderCalendar() {
    const rows = snapshot && Array.isArray(snapshot.calendar) ? snapshot.calendar : [];
    const shown = rows.filter((row) => activeFilter === "all" || availability(row) === activeFilter);
    const body = $("calendar-body");
    body.replaceChildren();
    $("calendar-table-wrap").hidden = shown.length === 0;
    $("calendar-empty").hidden = shown.length > 0;
    const heading = $("calendar-empty").querySelector("h3");
    const description = $("calendar-empty").querySelector("p");
    heading.textContent = rows.length > 0 ? "No dates match this filter" : snapshot ? "No calendar dates were observed" : "No calendar observations yet";
    description.textContent = rows.length > 0 ? "Choose another filter to see the available observations." : snapshot ? "This collection did not provide daily calendar data. See coverage and observation notes." : "Run a collection to see the dates the source makes available.";
    for (const row of shown) {
      const tr = make("tr");
      const dateCell = make("td");
      dateCell.append(make("span", "date-primary", dateDisplay(row.date, false)));
      const date = localDate(row.date);
      if (date) dateCell.append(make("span", "date-secondary", date.toLocaleDateString(undefined, { weekday: "short" })));
      tr.append(dateCell);
      const state = availability(row);
      const stateCell = make("td");
      const badge = make("span", `availability-badge ${state}`);
      badge.append(make("span", `legend-dot ${state}`), make("span", "", state === "available" ? "Available" : state === "unavailable" ? "Unavailable" : state === "missing" ? "Not observed" : "Unknown"));
      stateCell.append(badge);
      tr.append(stateCell);
      const observedPrice = isPresent(row.price_amount) || isPresent(row.price_display);
      tr.append(make("td", observedPrice ? "price-cell" : "not-observed", money(row.price_amount, row.currency, row.price_display)));
      tr.append(make("td", isPresent(row.min_nights) ? "" : "not-observed", text(row.min_nights, "Not provided")));
      tr.append(make("td", isPresent(row.max_nights) ? "" : "not-observed", text(row.max_nights, "Not provided")));
      body.append(tr);
    }
    $("calendar-count").textContent = `${shown.length} of ${rows.length} dates shown`;
    $("calendar-context").textContent = snapshot ? "Source observations only; missing dates are counted in coverage." : "Observed daily availability and restrictions.";
  }

  function renderQuotes(result) {
    const quotes = Array.isArray(result.quotes) ? result.quotes : [];
    const context = result.context || {};
    const stay = isPresent(context.checkin) && isPresent(context.checkout) ? `${dateDisplay(context.checkin, false)} – ${dateDisplay(context.checkout, false)}` : "Stay dates unknown";
    const guests = [];
    for (const [key, label] of [["adults", "adults"], ["children", "children"], ["infants", "infants"], ["pets", "pets"]]) {
      if (isPresent(context[key]) && (key === "adults" || Number(context[key]) > 0)) guests.push(`${text(context[key])} ${label}`);
    }
    $("quote-context").textContent = `${stay} · ${guests.join(", ") || "Guests unknown"} · ${text(context.currency, "Currency unknown")}${isPresent(context.locale) ? ` · ${context.locale}` : ""}`;
    $("quotes-empty").hidden = quotes.length > 0;
    $("quotes-empty").textContent = "No stay pricing was observed for this context.";
    const list = $("quotes-list");
    list.hidden = quotes.length === 0;
    list.replaceChildren();
    for (const quote of quotes) {
      const item = make("article", "quote-item");
      const displayedEstimate = quote.quote_kind === "display_price" && quote.price_basis === "stay_total";
      const ratePlanTotal = quote.quote_kind === "rate_plan_total" && quote.price_basis === "stay_total";
      let basis = quote.price_basis === "stay_total" ? "Stay total" : quote.price_basis === "nightly_display" ? "Nightly display" : "Price basis unknown";
      if (displayedEstimate) basis = "Displayed estimate";
      if (ratePlanTotal) {
        const plan = text(quote.rate_plan, "Rate plan");
        const normalizedPlan = plan.toLowerCase().replace(/[_-]/g, " ").trim();
        const label = normalizedPlan === "non refundable" || normalizedPlan === "nonrefundable" ? "Non-refundable" : normalizedPlan === "refundable" ? "Refundable" : plan;
        basis = `${label} · Stay total`;
      }
      const amount = displayedEstimate ? quote.display_total_amount ?? quote.display_amount : quote.price_basis === "stay_total" ? quote.total_amount : quote.price_basis === "nightly_display" ? quote.display_amount : quote.display_amount ?? quote.total_amount;
      const unavailable = quote.status === "unavailable";
      const heading = make("div", "quote-heading");
      heading.append(make("span", "quote-basis", unavailable ? "Requested stay" : basis));
      if (ratePlanTotal && quote.is_selected === true) heading.append(make("span", "selected-rate-badge", "Selected"));
      item.append(heading, make("div", "quote-value", unavailable && !isPresent(amount) ? "Stay unavailable" : money(amount, quote.currency || context.currency, quote.price_display)));
      if (isPresent(quote.message)) item.append(make("p", "quote-qualifier", quote.message));
      if (isPresent(quote.qualifier)) item.append(make("p", "quote-qualifier", quote.qualifier));
      if (Array.isArray(quote.line_items) && quote.line_items.length > 0) {
        const lines = make("ul", "quote-lines");
        for (const line of quote.line_items) {
          const lineNode = make("li");
          if (line && typeof line === "object") {
            lineNode.append(make("span", "", text(line.description || line.label || line.title || line.name, "Source line item")), make("span", "", money(line.amount ?? line.total_amount, line.currency || quote.currency, line.display_amount ?? line.price_display)));
          } else lineNode.textContent = text(line);
          lines.append(lineNode);
        }
        item.append(lines);
      }
      list.append(item);
    }
  }

  function warningText(warning) {
    if (typeof warning === "string") return warning;
    if (warning && typeof warning === "object") return text(warning.message || warning.reason || warning.detail, JSON.stringify(warning));
    return text(warning);
  }

  function listingCoordinates(listing) {
    if (!listing || typeof listing !== "object") return null;
    const lat = numberValue(listing.latitude ?? listing.lat);
    const lng = numberValue(listing.longitude ?? listing.lng ?? listing.lon);
    return lat !== null && lng !== null && Math.abs(lat) <= 90 && Math.abs(lng) <= 180 ? [lat, lng] : null;
  }

  function selectedIds() {
    const selected = compSet && Array.isArray(compSet.selected) ? compSet.selected : [];
    return new Set(selected.map((item) => text(item && typeof item === "object" ? item.listing_id ?? item.id : item, "")));
  }

  function isSelected(candidate) {
    return candidate.selected === true || selectedIds().has(text(candidate.listing_id, ""));
  }

  function selectedCandidates() {
    return compSet && Array.isArray(compSet.candidates) ? compSet.candidates.filter(isSelected) : [];
  }

  function candidateState(candidate) {
    return isSelected(candidate) ? "selected" : ["eligible", "excluded", "provisional"].includes(candidate.eligibility) ? candidate.eligibility : "unknown";
  }

  function candidateLink(candidate) {
    const id = text(candidate.listing_id, "");
    const title = text(candidate.title, `Listing ${id || "ID unknown"}`);
    const node = make(/^\d+$/.test(id) ? "a" : "span", "candidate-title", title);
    if (/^\d+$/.test(id)) {
      node.href = `https://www.airbnb.com/rooms/${id}`;
      node.target = "_blank";
      node.rel = "noopener noreferrer";
    }
    return node;
  }

  function candidatePopup(candidate) {
    const node = make("div", "map-popup");
    node.append(make("strong", "", text(candidate.title, `Listing ${text(candidate.listing_id)}`)));
    node.append(make("p", "", `Decision: ${candidateState(candidate)}`));
    node.append(make("p", "", `${text(candidate.bedrooms)} bedrooms · ${text(candidate.bathrooms)} bathrooms`));
    node.append(make("p", "", `Distance: ${isPresent(candidate.distance_km) ? `${text(candidate.distance_km)} km` : "Unknown"}`));
    if (Array.isArray(candidate.rejection_reasons) && candidate.rejection_reasons.length) node.append(make("p", "", candidate.rejection_reasons.map(warningText).join(" · ")));
    if (Array.isArray(candidate.missing_fields) && candidate.missing_fields.length) node.append(make("p", "", `Missing: ${candidate.missing_fields.map(warningText).join(", ")}`));
    node.append(candidateLink(candidate));
    return node;
  }

  function updateBoundaryNote() {
    const radius = numberValue($("radius").value);
    const pending = centerEdited && compSet !== null;
    $("boundary-context").classList.toggle("pending", pending);
    $("boundary-context").textContent = pending ? `Search area changed · ${text(radius)} km initial radius. Candidate results remain from the last discovery until you run again.` : `Search center ${$("center-lat").value}, ${$("center-lng").value} · ${text(radius)} km initial radius. Secondary filters and radius may change only at ten or fewer eligible matches, within a 10 km cap. Each applied step is recorded below.`;
  }

  function setMapCenter(coordinates, edited = true, pan = false) {
    $("center-lat").value = String(Number(coordinates[0].toFixed(6)));
    $("center-lng").value = String(Number(coordinates[1].toFixed(6)));
    if (edited) centerEdited = true;
    if (centerMarker) centerMarker.setLatLng(coordinates);
    if (searchCircle) searchCircle.setLatLng(coordinates);
    if (searchMap && pan) searchMap.panTo(coordinates);
    updateBoundaryNote();
  }

  function initializeMap() {
    if (!window.L) { $("map-error").hidden = false; return; }
    try {
      const L = window.L;
      const center = [Number($("center-lat").value), Number($("center-lng").value)];
      searchMap = L.map("search-map", { scrollWheelZoom: false }).setView(center, 14);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).on("tileerror", () => {
        $("map-error").textContent = "Some map tiles could not load. Coordinates, the search circle and candidate evidence remain available.";
        $("map-error").hidden = false;
      }).addTo(searchMap);
      searchCircle = L.circle(center, { radius: Number($("radius").value) * 1000, color: "#16796e", weight: 2, fillColor: "#16796e", fillOpacity: 0.07 }).addTo(searchMap);
      const icon = L.divIcon({ className: "search-center-icon", html: make("span", "center-marker-core"), iconSize: [24, 24], iconAnchor: [12, 12] });
      centerMarker = L.marker(center, { icon, draggable: true, autoPan: true, title: "Search center. Drag to move the circle." }).addTo(searchMap);
      centerMarker.on("dragend", (event) => {
        if (jobState === "running" || requestPending) return;
        const point = event.target.getLatLng();
        setMapCenter([point.lat, point.lng]);
      });
      searchMap.on("click", (event) => {
        if (jobState !== "running" && !requestPending) setMapCenter([event.latlng.lat, event.latlng.lng]);
      });
      candidateLayer = L.layerGroup().addTo(searchMap);
      cellLayer = L.layerGroup();
      updateBoundaryNote();
    } catch {
      $("map-error").textContent = "Map could not initialize. Use the center coordinates to set a search area.";
      $("map-error").hidden = false;
    }
  }

  function renderSubjectMarker(subject) {
    if (!searchMap || !window.L) return;
    const coordinates = listingCoordinates(subject);
    if (!coordinates) return;
    if (subjectMarker) searchMap.removeLayer(subjectMarker);
    const popup = make("div", "map-popup");
    popup.append(make("strong", "", text(subject.title, "Subject property")), make("p", "", "Subject property · public listing location"));
    subjectMarker = window.L.circleMarker(coordinates, { radius: 8, color: "#ffffff", weight: 2, fillColor: "#172c38", fillOpacity: 1 }).bindPopup(popup).addTo(searchMap);
  }

  function cellBounds(cell) {
    const bounds = cell.bounds;
    if (bounds && !Array.isArray(bounds) && typeof bounds === "object") {
      const north = numberValue(bounds.ne_lat ?? bounds.neLat ?? bounds.north);
      const east = numberValue(bounds.ne_lng ?? bounds.neLng ?? bounds.east);
      const south = numberValue(bounds.sw_lat ?? bounds.swLat ?? bounds.south);
      const west = numberValue(bounds.sw_lng ?? bounds.swLng ?? bounds.west);
      if ([north, east, south, west].every((value) => value !== null)) return [[south, west], [north, east]];
    }
    if (Array.isArray(bounds) && bounds.length === 2 && bounds.every((point) => Array.isArray(point) && point.length === 2)) return bounds;
    if (Array.isArray(bounds) && bounds.length === 4 && bounds.every((value) => numberValue(value) !== null)) return [[Number(bounds[0]), Number(bounds[1])], [Number(bounds[2]), Number(bounds[3])]];
    return null;
  }

  function renderMapResults() {
    if (!searchMap || !window.L || !candidateLayer) return;
    candidateLayer.clearLayers();
    mapMarkers = new Map();
    const colors = { selected: "#16796e", eligible: "#6695aa", excluded: "#a3aab2", provisional: "#bd8d47", unknown: "#939e97" };
    const candidates = compSet && Array.isArray(compSet.candidates) ? compSet.candidates : [];
    for (const candidate of candidates) {
      const coordinates = listingCoordinates(candidate);
      if (!coordinates) continue;
      const state = candidateState(candidate);
      const marker = window.L.circleMarker(coordinates, { radius: state === "selected" ? 6 : 4, color: "#fffefa", weight: 1, fillColor: colors[state], fillOpacity: state === "excluded" ? 0.65 : 0.95 }).bindPopup(candidatePopup(candidate)).addTo(candidateLayer);
      mapMarkers.set(text(candidate.listing_id, ""), marker);
    }
    cellLayer.clearLayers();
    const discovery = compSet && compSet.discovery ? compSet.discovery.report || compSet.discovery : {};
    const cells = Array.isArray(discovery.cells) ? discovery.cells : [];
    for (const cell of cells) {
      const bounds = cellBounds(cell);
      if (!bounds) continue;
      const popup = make("div", "map-popup");
      popup.append(make("strong", "", `Search cell · ${text(cell.status)}`), make("p", "", `${text(cell.returned_count)} results · depth ${text(cell.depth)} · pages ${text(cell.pages)}`));
      const colors = { exhausted: "#598671", subdivided: "#95a695", capped: "#bc8c4b", error: "#b87563", unvisited: "#a0aab0" };
      window.L.rectangle(bounds, { color: colors[cell.status] || "#7a8f7c", weight: 1, dashArray: "4 4", fillOpacity: 0.025, interactive: true }).bindPopup(popup).addTo(cellLayer);
    }
    const subject = compSet && compSet.subject ? compSet.subject.listing || compSet.subject : null;
    if (subject) renderSubjectMarker(subject);
  }

  function renderCandidates() {
    const candidates = compSet && Array.isArray(compSet.candidates) ? compSet.candidates : [];
    const filtered = candidates.filter((candidate) => candidateFilter === "all" || (candidateFilter === "selected" ? isSelected(candidate) : candidate.eligibility === candidateFilter));
    const pages = Math.max(1, Math.ceil(filtered.length / 50));
    candidatePage = Math.min(candidatePage, pages - 1);
    const displayed = filtered.slice(candidatePage * 50, (candidatePage + 1) * 50);
    const body = $("candidate-body");
    body.replaceChildren();
    $("candidate-table-wrap").hidden = displayed.length === 0;
    $("candidates-empty").hidden = displayed.length > 0;
    $("candidates-empty").querySelector("h3").textContent = !compSet ? "Your competitor set starts here" : candidates.length ? "No candidates match this filter" : "No candidates were returned";
    $("candidates-empty").querySelector("p").textContent = !compSet ? "Choose a circle and discover listings. Results will show the evidence behind every selection." : candidates.length ? "Choose another filter to inspect the returned evidence." : "Review the discovery coverage. No suitable count is assumed and the circle remains fixed.";
    for (const candidate of displayed) {
      const state = candidateState(candidate);
      const row = make("tr", state === "selected" ? "selected-row" : "");
      const listingCell = make("td");
      listingCell.append(candidateLink(candidate), make("span", "cell-secondary", `ID ${text(candidate.listing_id)}`));
      const marker = mapMarkers.get(text(candidate.listing_id, ""));
      if (marker) {
        const locate = make("button", "candidate-map-link", "Locate on map");
        locate.type = "button";
        locate.addEventListener("click", () => { searchMap.panTo(marker.getLatLng()); marker.openPopup(); $("search-map").scrollIntoView({ behavior: "smooth", block: "center" }); });
        listingCell.append(locate);
      }
      row.append(listingCell);
      const decision = make("td");
      decision.append(make("span", `eligibility-badge ${state}`, state.charAt(0).toUpperCase() + state.slice(1)));
      if (state === "selected") decision.append(make("span", "cell-secondary", text(candidate.eligibility)));
      row.append(decision);
      const distance = numberValue(candidate.distance_km);
      row.append(make("td", "", distance === null ? "Unknown" : `${distance.toFixed(2)} km`));
      const capacity = make("td", "", `${text(candidate.bedrooms)} bedrm / ${text(candidate.bathrooms)} bath`);
      capacity.append(make("span", "cell-secondary", `${text(candidate.beds)} beds · ${text(candidate.person_capacity)} guests`));
      row.append(capacity);
      const reviews = make("td", "", isPresent(candidate.rating) ? `★ ${text(candidate.rating)}` : "Rating unknown");
      reviews.append(make("span", "cell-secondary", isPresent(candidate.review_count) ? `${text(candidate.review_count)} reviews` : "Review count unknown"));
      row.append(reviews);
      const operator = make("td", "", text(candidate.host_name, "Host unknown"));
      const operatorSize = make("span", "cell-secondary", candidate.operator_size === "large" ? "Large operator footprint" : candidate.operator_size === "small" ? "Small operator footprint" : "Operator size unknown");
      const observedFootprint = candidate.operator_size_basis === "observed_listings_for_same_public_host_id";
      operatorSize.title = observedFootprint ? "Observed listings with the same public host ID: a lower bound on its footprint, not proof of company ownership." : candidate.operator_size_basis === "publicly_disclosed_listing_count" ? "Based on the publicly disclosed listing count; company ownership is not established." : "Operator size basis is unknown; company ownership is not established.";
      operator.append(operatorSize);
      operator.append(make("span", "cell-secondary", isPresent(candidate.host_listing_count) ? `${text(candidate.host_listing_count)} ${observedFootprint ? "observed host listings" : "public host listings"}` : "Host listing count unknown"));
      if (observedFootprint) operator.append(make("span", "cell-secondary", "Observed lower bound"));
      if (isPresent(candidate.host_id)) operator.append(make("span", "cell-secondary", `Host ID ${text(candidate.host_id)}`));
      row.append(operator);
      const evidence = make("td", "", `Similarity: ${text(candidate.similarity_score)}`);
      evidence.append(make("span", "cell-secondary", `Coverage: ${typeof candidate.evidence_coverage === "object" && candidate.evidence_coverage !== null ? JSON.stringify(candidate.evidence_coverage) : text(candidate.evidence_coverage)}`));
      row.append(evidence);
      const audit = make("td");
      if (Array.isArray(candidate.rejection_reasons)) for (const reason of candidate.rejection_reasons) audit.append(make("span", "audit-reason", warningText(reason)));
      if (Array.isArray(candidate.missing_fields) && candidate.missing_fields.length) audit.append(make("span", "audit-missing", `Missing: ${candidate.missing_fields.map(warningText).join(", ")}`));
      if (Array.isArray(candidate.amenities) && candidate.amenities.length) audit.append(make("span", "cell-secondary", `Amenities: ${candidate.amenities.map(warningText).join(", ")}`));
      if (!audit.childElementCount) audit.append(make("span", "cell-secondary", "No audit notes provided"));
      row.append(audit);
      body.append(row);
    }
    $("candidate-count").textContent = filtered.length ? `${candidatePage * 50 + 1}–${candidatePage * 50 + displayed.length} of ${filtered.length} matching · ${candidates.length} returned` : `${filtered.length} matching · ${candidates.length} returned`;
    $("candidate-page").textContent = `Page ${candidatePage + 1} of ${pages}`;
    $("candidate-previous").disabled = candidatePage === 0;
    $("candidate-next").disabled = candidatePage >= pages - 1;
  }

  function renderCompMonitoring(result) {
    const observation = result.monitoring || {};
    const records = Array.isArray(observation.records) ? observation.records : [];
    $("monitor-empty").hidden = records.length > 0;
    $("monitor-table-wrap").hidden = records.length === 0;
    $("monitor-empty").textContent = selectedCandidates().length ? "No competitor calendars or stay quotes have been collected yet. Refresh the selected set to observe them." : "Discover a competitor set to start monitoring. No prices or availability are assumed.";
    $("monitor-context").textContent = isPresent(observation.processed) && isPresent(observation.total) ? `${text(observation.processed)} of ${text(observation.total)} selected listings processed · ${text(observation.state)}` : "Refresh the selected competitors for the saved stay and calendar context. Changing the form requires a new discovery.";
    const body = $("monitor-body");
    body.replaceChildren();
    for (const record of records) {
      const row = make("tr");
      const listing = make("td");
      listing.append(candidateLink(record), make("span", "cell-secondary", `ID ${text(record.listing_id)}`));
      row.append(listing);
      const quote = record.selected_quote || {};
      const quoteCell = make("td");
      quoteCell.append(make("span", "monitor-price", money(quote.total_amount, quote.currency, quote.status === "unavailable" ? "Stay unavailable" : "Not observed")));
      quoteCell.append(make("span", "cell-secondary", isPresent(quote.total_amount) ? `Stay total${isPresent(quote.rate_plan) ? ` · ${quote.rate_plan}` : ""}` : "No complete stay total observed"));
      if (isPresent(quote.checkin) && isPresent(quote.checkout)) quoteCell.append(make("span", "cell-secondary", `${dateDisplay(quote.checkin, false)} – ${dateDisplay(quote.checkout, false)}`));
      row.append(quoteCell);
      const coverage = record.coverage || {};
      const calendar = make("td", "", `${count(coverage.observed_days)} / ${count(coverage.requested_days)} dates observed`);
      calendar.append(make("span", "cell-secondary", `${count(coverage.available_days)} available · ${count(coverage.unavailable_days)} unavailable`));
      calendar.append(make("span", "cell-secondary", `${count(coverage.unknown_days)} unknown · ${count(coverage.missing_days)} missing · ${count(coverage.priced_days)} priced`));
      row.append(calendar);
      const status = make("td", "", text(record.status, "Status unknown"));
      if (isPresent(record.run_id)) status.append(make("span", "cell-secondary", `Run ${text(record.run_id)}`));
      status.append(make("span", "cell-secondary", isPresent(record.observed_at) ? text(record.observed_at) : "Observation time not provided"));
      if (Array.isArray(record.warnings)) for (const warning of record.warnings) status.append(make("span", "audit-reason", warningText(warning)));
      row.append(status);
      body.append(row);
    }
  }

  function renderCompSet(result) {
    compSet = result;
    const candidates = Array.isArray(result.candidates) ? result.candidates : [];
    const summary = result.summary || {};
    const criteria = result.criteria || {};
    if (!formEdited) restoreContext(result.context || {});
    const target = numberValue(criteria.target);
    $("comp-candidates").textContent = String(candidates.length);
    $("comp-selected").textContent = String(selectedCandidates().length);
    $("comp-excluded").textContent = String(candidates.filter((candidate) => candidate.eligibility === "excluded").length);
    $("comp-provisional").textContent = String(candidates.filter((candidate) => candidate.eligibility === "provisional").length);
    $("comp-target").textContent = target === null ? "target not provided" : `target up to ${target}`;
    const observedAt = new Date(result.observed_at);
    $("compset-observed").textContent = isPresent(result.observed_at) && !Number.isNaN(observedAt.getTime()) ? `Discovered ${observedAt.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}` : "Discovery time not provided";
    const radius = numberValue(criteria.radius_km);
    $("candidate-context").textContent = `Saved boundary: ${text(criteria.center_lat)}, ${text(criteria.center_lng)} · ${text(criteria.radius_km)} km. Every returned candidate is retained for audit.`;
    const discovery = result.discovery ? result.discovery.report || result.discovery : {};
    const notes = [];
    const unresolved = Array.isArray(discovery.unresolved_cells) ? discovery.unresolved_cells.length : null;
    if (discovery.complete_for_requested_cells === false || unresolved > 0) notes.push(`Partial discovery${unresolved === null ? "" : ` · ${unresolved} unresolved search cells`}.`);
    if (Number.isInteger(discovery.http_requests)) notes.push(`${discovery.http_requests} search requests observed.`);
    if (isPresent(summary.shortfall)) notes.push(`Selection shortfall: ${text(summary.shortfall)}.`);
    if (result.adaptive && Array.isArray(result.adaptive.steps)) {
      for (const step of result.adaptive.steps) {
        const changes = Object.entries(step.changes || {}).map(([key, value]) => `${key.replaceAll("_", " ")}: ${text(value.before)} → ${text(value.after, "disabled")}`).join("; ");
        notes.push(`${text(step.stage).replaceAll("_", " ")}: ${text(step.counts && step.counts.eligible_count)} eligible${changes ? ` · ${changes}` : ""}.`);
      }
      notes.push("Secondary filters and radius change only at ten or fewer eligible matches; every step remains in the audit.");
    }
    notes.push("The discovery uses a bounded search; this is not proof that every listing in the circle was found.");
    if (discovery.budget_exhausted === true || discovery.capped === true) notes.push("The collection budget was reached.");
    if (isPresent(discovery.stop_reason)) notes.push(`Stop reason: ${text(discovery.stop_reason)}.`);
    if (isPresent(discovery.message)) notes.push(text(discovery.message));
    notes.push("Operator size describes a public listing footprint; it does not establish company ownership.");
    $("discovery-note").textContent = notes.join(" ");
    const coordinates = listingCoordinates({ lat: criteria.center_lat, lng: criteria.center_lng });
    if (coordinates && (!centerEdited || activeJob === "discover")) {
      centerEdited = false;
      if (radius !== null && radius >= 0.25 && radius <= 10) {
        $("radius").value = String(radius);
        if (searchCircle) searchCircle.setRadius(radius * 1000);
      }
      setMapCenter(coordinates, false, true);
    }
    const subject = result.subject && (result.subject.listing || result.subject);
    const subjectCoordinates = listingCoordinates(subject);
    if (subjectCoordinates) subjectCenter = subjectCoordinates;
    renderMapResults();
    candidatePage = 0;
    renderCandidates();
    renderCompMonitoring(result);
    for (const [id, path] of [["export-candidates", "/exports/candidates.csv"], ["export-compset", "/exports/compset.json"]]) {
      $(id).href = path;
      $(id).setAttribute("aria-disabled", "false");
      $(id).setAttribute("download", "");
    }
    setBusy(jobState === "running" || requestPending);
    updateBoundaryNote();
  }

  function safePublicUrl(value) {
    if (typeof value !== "string" || !value.trim()) return null;
    try {
      const url = new URL(value, "https://bnbmehomes.com");
      return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
    } catch { return null; }
  }

  function propertyCity(property) {
    const location = property.attributes && property.attributes.location || {};
    const city = property.city ?? location.city ?? location.city_name;
    return typeof city === "object" && city !== null ? text(city.name || city.title) : text(city);
  }

  function propertyCountry(property) {
    const location = property.attributes && property.attributes.location || {};
    const country = property.country ?? location.country ?? location.country_name;
    const label = typeof country === "object" && country !== null ? country.name || country.title : country;
    if (isPresent(label)) {
      const normalized = String(label).trim().toLowerCase();
      if (["uae", "ae", "united arab emirates"].includes(normalized)) return "United Arab Emirates";
      if (["ksa", "sa", "saudi arabia", "kingdom of saudi arabia"].includes(normalized)) return "Saudi Arabia";
      if (["uk", "gb", "united kingdom", "england"].includes(normalized)) return "United Kingdom";
      return String(label);
    }
    const city = propertyCity(property).toLowerCase();
    if (["dubai", "abu dhabi", "sharjah"].includes(city)) return "United Arab Emirates";
    if (["riyadh", "jeddah", "dammam", "al khobar", "al ula", "alula"].includes(city)) return "Saudi Arabia";
    if (city === "london") return "United Kingdom";
    return "Unknown";
  }

  function propertyCurrency(property) {
    const value = property.currency ?? (property.attributes && property.attributes.currency);
    return typeof value === "object" && value !== null ? text(value.code || value.name) : text(value);
  }

  function portfolioProperties() {
    return portfolio && Array.isArray(portfolio.properties) ? portfolio.properties : [];
  }

  function optionsFor(select, values, label) {
    const previous = select.value;
    select.replaceChildren(make("option", "", label));
    select.children[0].value = "all";
    for (const value of [...new Set(values)].sort()) {
      const option = make("option", "", value);
      option.value = value;
      select.append(option);
    }
    select.value = values.includes(previous) ? previous : "all";
  }

  function refreshPortfolioFilters() {
    const properties = portfolioProperties();
    optionsFor($("portfolio-country"), properties.map(propertyCountry), "All countries");
    const country = $("portfolio-country").value;
    optionsFor($("portfolio-city"), properties.filter((property) => country === "all" || propertyCountry(property) === country).map(propertyCity), "All cities");
    optionsFor($("portfolio-currency"), [...properties.map(propertyCurrency), "AED", "SAR", "GBP"], "All currencies");
  }

  function attributeValue(value) {
    if (value === undefined || value === null || value === "") return "Unknown / not provided";
    return typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
  }

  function propertyAttributes(property) {
    const content = make("div", "portfolio-attribute-content");
    content.append(make("h3", "", "Observed property fields"));
    const fields = make("dl", "property-attributes");
    for (const [key, value] of Object.entries(property)) {
      if (key === "attributes" || key === "detail_attributes" || key === "quotes" || key === "profile") continue;
      fields.append(make("dt", "", key.replace(/_/g, " ")), make("dd", "", attributeValue(value)));
    }
    content.append(fields);
    const canonical = property.profile && property.profile.attributes;
    if (canonical && typeof canonical === "object") {
      content.append(make("h3", "", "Property features & source evidence"));
      const features = make("dl", "property-attributes");
      for (const [key, attribute] of Object.entries(canonical)) {
        const value = attribute && typeof attribute === "object" && Object.hasOwn(attribute, "value") ? attribute.value : attribute;
        const feature = make("dd", "", attributeValue(value));
        if (attribute && typeof attribute === "object" && isPresent(attribute.status)) feature.append(make("span", "cell-secondary", `Evidence status: ${attribute.status}`));
        if (attribute && attribute.evidence) feature.append(make("span", "cell-secondary", `Source evidence: ${attributeValue(attribute.evidence)}`));
        features.append(make("dt", "", key.replace(/_/g, " ")), feature);
      }
      content.append(features);
    }
    content.append(make("h3", "", "All published attributes"), make("pre", "property-raw-attributes", attributeValue(property.attributes)));
    content.append(make("h3", "", "Latest property-detail attributes"), make("pre", "property-raw-attributes", attributeValue(property.detail_attributes)));
    content.append(make("h3", "", "All price observations and their contexts"), make("pre", "property-raw-attributes", attributeValue(property.quotes)));
    return content;
  }

  function propertyPriceCell(property) {
    const cell = make("td");
    const attributes = property.attributes || {};
    const currency = propertyCurrency(property);
    const quotes = Array.isArray(property.quotes) ? property.quotes.slice().sort((a, b) => {
      const priority = (quote) => quote.quote_kind === "website_stay_total" ? 0 : quote.quote_kind === "search_display" ? 2 : 1;
      return priority(a) - priority(b) || (Date.parse(b.observed_at) || 0) - (Date.parse(a.observed_at) || 0);
    }) : [];
    const published = [];
    for (const [key, label] of [["non_refundable_price", "Non-refundable"], ["refundable_price", "Refundable"]]) {
      const value = property[key] ?? attributes[key];
      if (isPresent(value) && numberValue(value) !== null && Number(value) > 0) published.push(`${label}: ${money(value, currency === "Unknown" ? null : currency)}`);
    }
    if (published.length && !quotes.length) {
      cell.append(make("span", "portfolio-price-label", "Published catalog prices"));
      for (const price of published) cell.append(make("span", "portfolio-price-value", price));
      const from = property.from_date ?? attributes.from_date;
      const to = property.to_date ?? attributes.to_date;
      cell.append(make("span", "portfolio-price-note", `${isPresent(from) || isPresent(to) ? `${text(from)} – ${text(to)} · ` : ""}Price unit and bookability require quote evidence.`));
    }
    for (const quote of quotes.slice(0, 2)) {
      const unavailableStay = quote.status === "unavailable";
      const bookable = quote.bookable === true || quote.availability_confirmed === true || quote.evidence_type === "bookable_quote";
      const publishedOnly = quote.evidence_type === "published_rate" || quote.quote_kind === "published_rate" || quote.quote_kind === "search_display" || quote.status === "display_only";
      const basis = quote.price_basis === "stay_total" ? "Stay total" : quote.price_basis === "nightly_display" ? "Nightly display" : quote.price_basis === "unspecified_search_price" ? "Price unit unspecified" : "Price basis unknown";
      cell.append(make("span", "portfolio-price-label", quote.quote_kind === "website_stay_total" ? "Direct website · dated quote" : bookable ? "Bookable quote evidence" : publishedOnly ? "Published price observation" : "Price observation"));
      cell.append(make("span", "portfolio-price-value", unavailableStay ? "Unavailable for this stay" : money(quote.total_amount ?? quote.display_amount ?? quote.amount, quote.currency, quote.price_display)));
      const context = quote.context || quote;
      const dates = isPresent(context.checkin) && isPresent(context.checkout) ? `${dateDisplay(context.checkin, false)} – ${dateDisplay(context.checkout, false)}` : "Stay dates not provided";
      const guests = quote.price_endpoint_guest_parameter === false ? `${isPresent(context.adults) ? ` · ${context.adults} adults requested` : ""} · guest pricing unverified` : isPresent(context.adults) ? ` · ${context.adults} adults` : " · guest count unknown";
      cell.append(make("span", "portfolio-price-note", `${basis} · ${dates}${guests}${unavailableStay ? " · source declined this date range" : bookable ? " · confirmed only at observation time" : " · bookability not established"}`));
    }
    if (!published.length && !quotes.length) cell.append(make("span", "cell-secondary", "No price observation"));
    if (quotes.length > 2) cell.append(make("span", "cell-secondary", `${quotes.length} observations · inspect all attributes`));
    return cell;
  }

  function renderPortfolioTable() {
    const properties = portfolioProperties();
    const query = $("portfolio-search").value.trim().toLowerCase();
    const country = $("portfolio-country").value;
    const city = $("portfolio-city").value;
    const currency = $("portfolio-currency").value;
    const filtered = properties.filter((property) => {
      const searchText = [property.title, property.property_id, property.building, property.building_name, property.attributes && property.attributes.property_details_name].map((value) => text(value, "")).join(" ").toLowerCase();
      return (!query || searchText.includes(query)) && (country === "all" || propertyCountry(property) === country) && (city === "all" || propertyCity(property) === city) && (currency === "all" || propertyCurrency(property) === currency);
    });
    const pages = Math.max(1, Math.ceil(filtered.length / 50));
    portfolioPage = Math.min(portfolioPage, pages - 1);
    const displayed = filtered.slice(portfolioPage * 50, (portfolioPage + 1) * 50);
    const body = $("portfolio-body");
    body.replaceChildren();
    $("portfolio-empty").hidden = displayed.length > 0;
    $("portfolio-table-wrap").hidden = displayed.length === 0;
    $("portfolio-empty").querySelector("h3").textContent = !portfolio ? "Catalog observations will appear here" : properties.length ? "No properties match these filters" : "No catalog records were returned";
    $("portfolio-empty").querySelector("p").textContent = !portfolio ? "Published records, platform identity and stay pricing will be shown only when collected." : properties.length ? "Change the country, city, currency or search to inspect another part of the observed catalog." : "This is a collection coverage gap; it does not establish an empty company inventory.";
    for (const property of displayed) {
      const row = make("tr");
      const listing = make("td");
      const source = safePublicUrl(property.public_property_url || property.source_url);
      const title = make(source ? "a" : "span", "portfolio-title", text(property.title, `Property ${text(property.property_id)}`));
      if (source) { title.href = source; title.target = "_blank"; title.rel = "noopener noreferrer"; }
      listing.append(title, make("span", "cell-secondary", `Property ID ${text(property.property_id)}`));
      const publicationLabel = property.publication_status === "published_in_public_catalogue" ? "Published catalog record" : ["active", "ACTIVE", "active_in_public_details"].includes(property.publication_status) ? "Active in source details" : text(property.publication_status, "Publication status not provided").replace(/_/g, " ");
      listing.append(make("span", "portfolio-source-status", publicationLabel));
      row.append(listing);
      const location = make("td", "", propertyCity(property));
      location.append(make("span", "cell-secondary", propertyCountry(property)));
      const coordinates = listingCoordinates(property);
      location.append(make("span", "cell-secondary", coordinates ? `${coordinates[0]}, ${coordinates[1]}` : "Coordinates not provided"));
      row.append(location);
      const capacity = make("td", "", `${text(property.bedrooms)} bedrm / ${text(property.bathrooms)} bath`);
      capacity.append(make("span", "cell-secondary", `${text(property.beds)} beds · ${text(property.person_capacity)} guests`));
      capacity.append(make("span", "cell-secondary", `Size: ${text(property.floor_area ?? property.size, "Not provided")}`));
      row.append(capacity);
      const identity = make("td");
      const airbnbId = text(property.airbnb_listing_id, "");
      if (/^\d+$/.test(airbnbId)) identity.append(candidateLink({ listing_id: airbnbId, title: `Airbnb ${airbnbId}` }));
      else identity.append(make("span", "cell-secondary", "Airbnb identity not linked"));
      identity.append(make("span", "cell-secondary", `Link status: ${text(property.link_status, "Unknown")}`));
      identity.append(make("span", "cell-secondary", isPresent(property.host_name) ? `Host: ${property.host_name}` : "Host not linked"));
      if (isPresent(property.host_id)) identity.append(make("span", "cell-secondary", `Host ID ${property.host_id}`));
      const profile = safePublicUrl(property.host_profile_url);
      if (profile) { const link = make("a", "text-link", "Host profile ↗"); link.href = profile; link.target = "_blank"; link.rel = "noopener noreferrer"; identity.append(link); }
      row.append(identity, propertyPriceCell(property));
      const detail = make("td");
      const button = make("button", "attribute-toggle", "Inspect all attributes");
      button.type = "button";
      button.setAttribute("aria-expanded", "false");
      const detailRow = make("tr", "portfolio-attributes-row");
      detailRow.hidden = true;
      const detailCell = make("td");
      detailCell.colSpan = 6;
      detailRow.append(detailCell);
      button.addEventListener("click", () => {
        if (!detailCell.childElementCount) detailCell.append(propertyAttributes(property));
        detailRow.hidden = !detailRow.hidden;
        button.setAttribute("aria-expanded", String(!detailRow.hidden));
        button.textContent = detailRow.hidden ? "Inspect all attributes" : "Hide attributes";
      });
      detail.append(button, make("span", "cell-secondary", `Currency: ${propertyCurrency(property)}`));
      const coverage = property.calendar_coverage || {};
      if (isPresent(coverage.observed_days)) {
        detail.append(make("span", "calendar-coverage-primary", `${count(coverage.observed_days)} calendar dates observed`));
        detail.append(make("span", "cell-secondary", `${count(coverage.available_days)} available · ${count(coverage.unavailable_days)} unavailable · ${count(coverage.unknown_days)} unknown`));
        detail.append(make("span", "cell-secondary", `${count(coverage.priced_days)} dates with observed rates`));
      } else detail.append(make("span", "cell-secondary", "Daily calendar not observed"));
      detail.append(make("span", "cell-secondary", isPresent(property.observed_at) ? `Observed: ${property.observed_at}` : "Observation time not provided"));
      row.append(detail);
      body.append(row, detailRow);
    }
    $("portfolio-count").textContent = filtered.length ? `${portfolioPage * 50 + 1}–${portfolioPage * 50 + displayed.length} of ${filtered.length} matching · ${properties.length} observed records` : `${filtered.length} matching · ${properties.length} observed records`;
    $("portfolio-page").textContent = `Page ${portfolioPage + 1} of ${pages}`;
    $("portfolio-previous").disabled = portfolioPage === 0;
    $("portfolio-next").disabled = portfolioPage >= pages - 1;
  }

  function renderPortfolio(result) {
    portfolio = result;
    if (!inventoryEdited) {
      const stay = (result.properties || []).flatMap(property => property.quotes || []).find(quote => String(quote.quote_kind || "").startsWith("website_stay_") && localDate(quote.checkin) && localDate(quote.checkout));
      if (stay) {
        $("inventory-checkin").value = stay.checkin;
        $("inventory-checkout").value = stay.checkout;
        // The next requested collection uses one adult; historical quotes keep
        // their original party in the evidence table.
        $("inventory-adults").value = "1";
      }
    }
    const summary = result.summary || {};
    for (const [id, key] of [["property", "property_count"], ["active", "active_property_count"], ["linked", "airbnb_linked_count"], ["host", "host_count"], ["display", "display_price_count"], ["quoted", "stay_price_count"], ["calendar", "calendar_property_count"], ["calendar-record", "calendar_record_count"]]) $("portfolio-" + id + "-count").textContent = count(summary[key]);
    const observed = new Date(result.observed_at);
    $("portfolio-observed").textContent = isPresent(result.observed_at) && !Number.isNaN(observed.getTime()) ? `Observed ${observed.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}` : "Catalog observation time not provided";
    refreshPortfolioFilters();
    portfolioPage = 0;
    renderPortfolioTable();
    const notes = ["Public catalog coverage does not establish the entire company inventory.", "Published prices remain in their source currency. No currency conversion is applied.", "A published property is not presumed available or bookable for an unspecified stay."];
    if (Array.isArray(summary.coverage_notes)) notes.push(...summary.coverage_notes.map(warningText));
    $("portfolio-notes").replaceChildren(...[...new Set(notes)].map((note) => make("li", "", note)));
    const hosts = Array.isArray(result.hosts) ? result.hosts : [];
    $("portfolio-hosts-panel").hidden = hosts.length === 0;
    $("portfolio-hosts").replaceChildren();
    for (const host of hosts) {
      const card = make("article", "portfolio-host-card");
      card.append(make("strong", "", text(host.host_name || host.display_name || host.name, "Business host")), make("p", "", `Host ID: ${text(host.host_id || host.legacy_host_id)}`));
      card.append(make("p", "", `Identity: ${text(host.identity_status || host.link_status, host.profile_evidence?.complete_declared_profile_sample ? "Public profile membership verified" : "Verification status not provided")}`));
      const disclosedCount = host.disclosed_listing_count ?? host.public_listing_count ?? host.declared_listing_count;
      if (isPresent(disclosedCount)) card.append(make("p", "", `Publicly disclosed listing count: ${text(disclosedCount)}. This is not a company inventory total.`));
      if (isPresent(host.company_provenance)) card.append(make("p", "", host.company_provenance));
      const url = safePublicUrl(host.host_profile_url || host.profile_url);
      if (url) { const link = make("a", "", "Public host profile ↗"); link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer"; card.append(link); }
      $("portfolio-hosts").append(card);
    }
    for (const [id, path] of [["export-portfolio-csv", "/exports/portfolio.csv"], ["export-portfolio-prices", "/exports/prices.csv"], ["export-portfolio-calendar", "/exports/inventory-calendar.csv"], ["export-portfolio-json", "/exports/portfolio.json"]]) { $(id).href = path; $(id).setAttribute("aria-disabled", "false"); $(id).setAttribute("download", ""); }
    const airbnbListings = Array.isArray(result.airbnb_listings) ? result.airbnb_listings : [];
    $("portfolio-airbnb-panel").hidden = airbnbListings.length === 0;
    $("portfolio-airbnb-count").textContent = `${airbnbListings.length} platform records · direct-site property links require explicit evidence.`;
    $("portfolio-airbnb-data").textContent = JSON.stringify(airbnbListings, null, 2);
  }

  function selectView(view) {
    activeView = view;
    $("rates-workspace").hidden = view !== "rates";
    document.body.classList.toggle("rate-workspace-active", view === "rates");
    document.body.classList.toggle("dual-workspace-active", view === "rates" && Boolean(window.CompSetDual));
    if (view !== "rates" && !legacyInitialized) { legacyInitialized = true; initialize(); }
    const headings = {
      rates: ["Rate intelligence", "Your rates, competitors and source evidence in one workspace."],
      portfolio: ["Property portfolio", "Browse BnBME’s published properties and verified source details."],
      comparison: ["Competitor research", "Define your market and inspect every selection decision."],
      prices: ["Saved prices", "Inspect contextual prices, availability and the evidence behind them."],
    };
    $("workspace-title").textContent = headings[view][0];
    $("workspace-description").textContent = headings[view][1];
    const portfolioView = view === "portfolio";
    $("portfolio-workspace").hidden = !portfolioView;
    $("comparison-workspace").hidden = view !== "comparison";
    $("comparison-controls").hidden = view !== "comparison";
    $("prices-workspace").hidden = view !== "prices";
    $("workspace-grid").classList.toggle("portfolio-view", view !== "comparison");
    for (const id of ["rates", "portfolio", "comparison", "prices"]) { $("view-" + id).classList.toggle("active", id === view); $("view-" + id).setAttribute("aria-pressed", String(id === view)); }
    if (view === "comparison") {
      if (!searchMap) { initializeMap(); renderMapResults(); if (snapshot) renderSubjectMarker(snapshot.listing); renderCandidates(); }
      if (searchMap) setTimeout(() => searchMap.invalidateSize(), 0);
    }
  }

  const inclusion = (value) => value === true ? "included" : value === false ? "excluded" : "unknown";
  const readableReason = (value) => text(value, "Not collected").replaceAll("_", " ");
  const partyText = (context) => `${text(context.adults)} adult(s) · ${text(context.children)} children${isPresent(context.rooms) ? ` · ${context.rooms} room(s)` : ` · ${text(context.infants)} infants · ${text(context.pets)} pets`} · ${text(context.currency, "Currency unknown")}`;

  function evidenceDetails(value, label = "Inspect saved evidence") {
    const details = make("details", "saved-evidence-details");
    details.append(make("summary", "", label), make("pre", "property-raw-attributes", JSON.stringify(value, null, 2)));
    return details;
  }

  function savedDownload(id, path, enabled) {
    const link = $(id);
    link.setAttribute("aria-disabled", String(!enabled));
    if (enabled) { link.href = path; link.setAttribute("download", ""); }
    else { link.removeAttribute("href"); link.removeAttribute("download"); }
  }

  function expandOneNightCells(report) {
    const records = Array.isArray(report.records) ? report.records : [];
    const lookup = new Map(records.map(record => [`${record.context?.listing_id}|${record.context?.checkin}`, record]));
    const ids = Array.from(new Set([...(Array.isArray(report.listing_ids) ? report.listing_ids : []), ...records.map(record => record.context?.listing_id)].filter(Boolean))).sort();
    const start = localDate(report.context?.start_date);
    const end = localDate(report.context?.end_date);
    if (!start || !end || end <= start) return records;
    const cells = [];
    for (const id of ids) {
      let day = new Date(start);
      for (let step = 0; day < end && step < 366; step += 1) {
        const checkin = dateInput(day);
        const checkoutDate = new Date(day.getFullYear(), day.getMonth(), day.getDate() + 1);
        cells.push(lookup.get(`${id}|${checkin}`) || { context: { ...report.context, listing_id: id, checkin, checkout: dateInput(checkoutDate) }, status: "not_collected", quotes: [], reason: "No quote request result saved for this date." });
        day = checkoutDate;
      }
    }
    return cells;
  }

  function renderOneNightTable() {
    const listing = $("one-night-listing").value;
    const filter = $("one-night-filter").value;
    const rows = oneNightCells.filter(row => (listing === "all" || row.context?.listing_id === listing) && (filter === "all" || (filter === "unknown" ? !["quoted", "calendar_skipped"].includes(row.status) : row.status === filter)));
    const pages = Math.max(1, Math.ceil(rows.length / 40));
    oneNightPage = Math.min(oneNightPage, pages - 1);
    const body = $("one-night-body");
    body.replaceChildren();
    for (const record of rows.slice(oneNightPage * 40, (oneNightPage + 1) * 40)) {
      const context = record.context || {};
      const quotes = Array.isArray(record.quotes) ? record.quotes : [];
      const row = make("tr");
      const identity = make("td");
      const id = text(context.listing_id, "Unknown listing");
      const title = compSet?.candidates?.find(candidate => candidate.listing_id === id)?.title;
      const link = make("a", "candidate-title", title || `Listing ${id}`);
      if (/^\d+$/.test(id)) { link.href = `https://www.airbnb.com/rooms/${id}`; link.target = "_blank"; link.rel = "noopener noreferrer"; }
      identity.append(link, make("span", "cell-secondary", `${dateDisplay(context.checkin, false)} → ${dateDisplay(context.checkout, false)}`));
      const state = make("td");
      const label = record.status === "quoted" ? "Exact quote" : record.status === "calendar_skipped" ? "Calendar restricted" : record.status === "not_collected" ? "Not collected" : "Unknown";
      state.append(make("span", `availability-badge ${record.status === "quoted" ? "available" : record.status === "calendar_skipped" ? "unavailable" : "unknown"}`, label));
      state.append(make("span", "cell-secondary", record.status === "calendar_skipped" ? readableReason(record.preflight?.reason) : record.reason || (record.status === "unknown" ? "No verified exact total was saved." : "")));
      const price = make("td");
      const plans = make("td");
      if (!quotes.length) price.append(make("span", "not-observed", "Not observed"));
      for (const quote of quotes) {
        price.append(make("strong", "monitor-price", money(quote.amount, quote.currency || context.currency)), make("span", "cell-secondary", quote.amount_kind === "one_night_stay_total" ? "One-night stay total" : readableReason(quote.amount_kind)));
        plans.append(make("span", "saved-plan", text(quote.rate_plan, "Rate plan unknown")), make("span", "cell-secondary", `Taxes ${inclusion(quote.taxes_included)} · fees ${inclusion(quote.fees_included)}`), make("span", "cell-secondary", text(quote.cancellation_terms, "Cancellation terms unknown")));
        const options = Array.isArray(quote.rate_options) ? quote.rate_options : [];
        for (const option of options) {
          plans.append(make("span", "saved-plan", `${text(option.rate_plan, "Rate plan unknown")}: ${money(option.amount, option.currency || context.currency)}${option.is_selected === true ? " · selected" : ""}`), make("span", "cell-secondary", `Taxes ${inclusion(option.taxes_included)} · fees ${inclusion(option.fees_included)} · ${text(option.cancellation_terms, "Cancellation terms unknown")}`));
        }
      }
      if (!quotes.length) plans.append(make("span", "not-observed", "No rate plan observed"));
      const source = make("td");
      source.append(make("span", "", partyText(context)), make("span", "cell-secondary", `Observed: ${text(record.observed_at, "Not observed")}`), evidenceDetails(record));
      row.append(identity, state, price, plans, source);
      body.append(row);
    }
    if (!rows.length) { const row = make("tr"); const cell = make("td", "", "No saved date cells match this view."); cell.colSpan = 5; row.append(cell); body.append(row); }
    $("one-night-count").textContent = `${rows.length} matching date cells · ${oneNightCells.length} represented in this saved grid`;
    $("one-night-page").textContent = `Page ${oneNightPage + 1} of ${pages}`;
    $("one-night-previous").disabled = oneNightPage === 0;
    $("one-night-next").disabled = oneNightPage >= pages - 1;
  }

  function renderOneNight(report) {
    oneNightCells = report ? expandOneNightCells(report) : [];
    const context = report?.context || {};
    $("one-night-context").textContent = report ? `${dateDisplay(context.start_date)} to ${dateDisplay(context.end_date)} (checkout boundary) · ${partyText(context)}` : "No saved one-night observations yet.";
    $("one-night-state").textContent = report ? `${readableReason(report.state)}${report.stop_reason ? ` · ${readableReason(report.stop_reason)}` : ""} · updated ${text(report.updated_at, "Unknown time")}` : "Not collected";
    for (const [id, key] of [["quoted", "quoted_date_cells"], ["skipped", "calendar_skipped_date_cells"], ["unknown", "unknown_date_cells"], ["total", "total_date_cells"]]) $("one-night-" + id).textContent = count(report?.[key]);
    const selected = $("one-night-listing").value;
    const select = $("one-night-listing");
    select.replaceChildren(new Option("All listings", "all"));
    for (const id of new Set(oneNightCells.map(row => row.context?.listing_id).filter(Boolean))) select.append(new Option(`Listing ${id}`, id));
    select.value = Array.from(select.options).some(option => option.value === selected) ? selected : "all";
    savedDownload("export-one-night-csv", "/exports/one-night-prices.csv", Boolean(report));
    savedDownload("export-one-night-json", "/exports/one-night.json", Boolean(report));
    renderOneNightTable();
  }

  function renderHotel(report) {
    hotelSnapshot = report;
    const context = report?.context || {};
    const summary = report?.summary || {};
    const pipeline = report?.pipelines;
    const filter = $("hotel-source-filter").value;
    const allRates = Array.isArray(report?.pipeline_rates) ? report.pipeline_rates : (report?.rates || []);
    const rates = allRates.filter(rate => filter === "all" || (rate.source || "google_hotels") === filter);
    const allDates = Array.isArray(pipeline?.coverage) ? pipeline.coverage : (report?.dates || []);
    const dates = allDates.filter(day => filter === "all" || (day.source || "google_hotels") === filter);
    const hotelParty = `${text(context.adults)} adult(s) · ${text(context.children)} children · ${isPresent(context.rooms) ? `${context.rooms} room(s)` : `Room count unconfirmed${isPresent(context.requested_rooms) ? ` (requested ${context.requested_rooms})` : ""}`} · ${text(context.currency, "Currency unknown")}`;
    $("hotel-prices-context").textContent = report ? `${text(context.hotel_name, "Hotel Aketa")} · ${text(context.source, "Source unknown")} · ${dateDisplay(context.start_date)} · ${text(context.days)} days · ${hotelParty}` : "One room, one adult. No verified hotel rates saved yet.";
    $("hotel-prices-state").textContent = report ? `${readableReason(report.state)}${report.stop_reason ? ` · ${readableReason(report.stop_reason)}` : ""} · observed ${text(report.observed_at, "Unknown time")}` : "Not collected";
    if (pipeline) {
      const requested = pipeline.context || {};
      $("hotel-prices-context").textContent = `Hotel Aketa · ${count(pipeline.summary?.source_count)} sources · ${dateDisplay(requested.start_date)} · ${count(requested.days)} days · requested ${text(requested.adults)} adult(s), ${text(requested.rooms)} room(s), ${text(requested.currency)}`;
      $("hotel-prices-state").textContent = `${readableReason(pipeline.state)}${pipeline.stop_reason ? ` · ${readableReason(pipeline.stop_reason)}` : ""} · pipeline updated ${text(pipeline.updated_at)}. Individual source timestamps are below.`;
    }
    $("hotel-prices-summary").textContent = report ? `${isPresent(summary.indicative_dates) ? `${count(summary.indicative_dates)} dates with indicative calendar prices · ${count(summary.partner_offer_dates)} dates with displayed partner offers · ` : ""}${count(summary.quoted_dates)} verified supplier quote dates · ${count(summary.unavailable_dates)} source-confirmed unavailable · ${count(summary.unknown_dates)} unknown. Google displays do not establish final supplier prices; room count, taxes, meals and cancellation terms remain as observed.` : "No availability conclusion can be drawn from missing prices.";
    if (pipeline) $("hotel-prices-summary").textContent = `${count(pipeline.summary?.quoted_cells)} direct source/date quotes · ${count(pipeline.summary?.indicative_cells)} indicative source/date prices · ${count(pipeline.summary?.unavailable_cells || 0)} source-confirmed unavailable stays · ${count(pipeline.summary?.unknown_cells)} unknown of ${count(pipeline.summary?.date_cells)} source/date cells. Membership, coupon, room, tax and cancellation conditions apply as observed. Google displays remain indicative.`;
    const sourceStatus = $("hotel-source-status");
    sourceStatus.replaceChildren();
    for (const item of pipeline?.source_states || []) sourceStatus.append(make("p", "", `${readableReason(item.source)}: ${readableReason(item.status)}${item.last_stay ? ` for last checked arrival ${item.last_stay}` : ""}${item.reason ? ` · ${readableReason(item.reason)}` : ""} · ${count(item.rate_count)} price observations · ${text(item.observed_at, "Not observed")}`));
    const body = $("hotel-prices-body");
    body.replaceChildren();
    const rows = [...rates.map(rate => ({ ...rate, state: rate.state || (String(rate.amount_type).startsWith("google_") ? "indicative_price" : "price_observation") })), ...dates.filter(day => !rates.some(rate => rate.checkin === day.checkin && rate.checkout === day.checkout && (!pipeline || rate.source === day.source)))].sort((a, b) => text(a.checkin).localeCompare(text(b.checkin)));
    for (const record of rows) {
      const row = make("tr");
      const stay = make("td");
      stay.append(make("strong", "", `${dateDisplay(record.checkin, false)} → ${dateDisplay(record.checkout, false)}`), make("span", "cell-secondary", `${readableReason(record.state)}${record.reason ? ` · ${readableReason(record.reason)}` : ""}`));
      const room = make("td");
      room.append(make("span", "saved-plan", text(record.room_name, "Room not observed")), make("span", "cell-secondary", text(record.rate_plan_name, "Rate plan not observed")));
      if (record.partner || record.provider || record.supplier) room.append(make("span", "cell-secondary", `Displayed supplier: ${text(record.partner || record.provider || record.supplier)}`));
      const price = make("td");
      const priceDisplay = record.display_amount || record.amount_display || record.raw_price || record.display_price;
      price.append(make("strong", "monitor-price", money(record.amount, record.currency || context.currency, priceDisplay)), make("span", "cell-secondary", readableReason(record.amount_type || "Price basis unknown")));
      if (record.precision) price.append(make("span", "cell-secondary", record.precision === "abbreviated" ? "Abbreviated display · exact amount unknown" : readableReason(record.precision)));
      const conditions = make("td");
      conditions.append(make("span", "", `Taxes ${inclusion(record.taxes_included)} · fees ${inclusion(record.fees_included)}`), make("span", "cell-secondary", `Meals: ${typeof record.meals === "object" && record.meals !== null ? JSON.stringify(record.meals) : text(record.meals)}`), make("span", "cell-secondary", `Cancellation: ${typeof record.cancellation === "object" && record.cancellation !== null ? JSON.stringify(record.cancellation) : text(record.cancellation)}`));
      if (isPresent(record.taxes_and_fees)) conditions.append(make("span", "cell-secondary", `Taxes & fees: ${typeof record.taxes_and_fees === "object" ? JSON.stringify(record.taxes_and_fees) : money(record.taxes_and_fees, record.currency || context.currency)}`));
      if (record.conditions) conditions.append(make("span", "cell-secondary", `Conditions: ${typeof record.conditions === "object" ? JSON.stringify(record.conditions) : text(record.conditions)}`));
      if (record.membership_required) conditions.append(make("span", "cell-secondary", "Membership condition applies"));
      const source = make("td");
      const actual = record.observed_context || record;
      source.append(make("strong", "", readableReason(record.source || "google_hotels")), make("span", "cell-secondary", record.channel ? `Supplier channel: ${readableReason(record.channel)}` : "Supplier not identified"), make("span", "", pipeline ? `${text(actual.adults)} adult(s) · ${text(actual.rooms, "Unverified")} room(s) · ${text(record.currency, context.currency)}` : hotelParty), evidenceDetails(record));
      row.append(stay, room, price, conditions, source);
      body.append(row);
    }
    if (!rows.length) { const row = make("tr"); const cell = make("td", "", "No verified rates collected. Missing prices remain unknown."); cell.colSpan = 5; row.append(cell); body.append(row); }
    savedDownload("export-hotel-rates", "/exports/hotel-aketa-rates.csv", Boolean(report));
    savedDownload("export-hotel-json", "/exports/hotel-aketa.json", Boolean(report));
  }

  async function loadSavedPrices() {
    const results = await Promise.allSettled([api("/api/one-night", {}, true), api("/api/hotels/aketa", {}, true)]);
    for (const [index, renderSaved] of [renderOneNight, renderHotel].entries()) {
      const result = results[index];
      if (result.status === "fulfilled") renderSaved(result.value);
      else {
        $(index === 0 ? "one-night-state" : "hotel-prices-state").textContent = `Read error: ${text(result.reason.message)} Previously displayed evidence may be stale.`;
        connectionError(text(result.reason.message, "Could not read saved price evidence."));
      }
    }
  }

  function renderWarnings(result) {
    const warnings = Array.isArray(result.warnings) ? result.warnings.slice() : [];
    const report = result.report || {};
    if (Array.isArray(report.errors)) warnings.push(...report.errors);
    if (isPresent(report.error)) warnings.push(report.error);
    const seen = new Set();
    const list = $("warnings-list");
    list.replaceChildren();
    for (const warning of warnings) {
      const message = warningText(warning);
      if (!seen.has(message)) { list.append(make("li", "", message)); seen.add(message); }
    }
    $("warnings-panel").hidden = list.childElementCount === 0;
  }

  function render(result) {
    snapshot = result;
    renderListing(result);
    renderCoverage(result);
    renderCalendar();
    renderQuotes(result);
    renderWarnings(result);
    for (const [id, path] of Object.entries(exportPaths)) {
      $(id).href = path;
      $(id).setAttribute("aria-disabled", "false");
      $(id).setAttribute("download", "");
    }
  }

  async function loadLatest() {
    const result = await api("/api/latest", {}, true);
    if (result) render(result);
  }

  function restoreContext(context) {
    for (const [id, key] of [["checkin", "checkin"], ["checkout", "checkout"], ["currency", "currency"]]) {
      if (isPresent(context[key])) $(id).value = text(context[key]);
    }
    if (/^\d+$/.test(text(context.listing_id, ""))) $("listing").value = `https://www.airbnb.com/rooms/${context.listing_id}`;
    // Saved observations retain their old window/party. A new collection starts
    // from the current Dubai date and the one-adult, thirty-day defaults.
  }

  async function loadResults() {
    const results = await Promise.allSettled([api("/api/compset", {}, true), api("/api/latest", {}, true), api("/api/portfolio", {}, true), api("/api/health", {}, true)]);
    if (results[0].status === "fulfilled" && results[0].value) renderCompSet(results[0].value);
    if (results[1].status === "fulfilled" && results[1].value) render(results[1].value);
    if (results[2].status === "fulfilled" && results[2].value) renderPortfolio(results[2].value);
    if (results[3].status === "fulfilled" && results[3].value) {
      const health = results[3].value;
      const alerts = Array.isArray(health.semantic_alerts) ? health.semantic_alerts : [];
      const changes = Array.isArray(health.changes) ? health.changes : [];
      $("contract-health").textContent = alerts.length ? `${alerts.length} source contract issue(s) need review. Missing data remains unknown; saved evidence is retained.` : changes.length ? `${changes.length} response structure change(s) recorded for review. No meaning changes are approved automatically.` : "Source checks recorded. Missing values stay unknown; price and availability evidence remain separate.";
    }
    for (const result of results) if (result.status === "rejected") connectionError(text(result.reason.message, "Could not load a saved observation."));
    await loadSavedPrices();
  }

  function scheduleStatus() {
    clearTimeout(timer);
    if (jobState === "running" && monitoring) timer = setTimeout(checkStatus, 2000);
  }

  async function checkStatus(refreshOnTransition = true) {
    clearTimeout(timer);
    try {
      const status = await api("/api/status");
      if (!["idle", "running", "complete", "partial", "failed", "paused", "stopped", "interrupted"].includes(status.state)) throw new Error("The local service returned an unknown collection state.");
      const previous = jobState;
      activeJob = status.state === "running" ? status.command === "run" ? "subject" : status.command || activeJob : null;
      setStatus(status.state, status.message);
      $("connection-error").hidden = true;
      if (refreshOnTransition && previous === "running" && ["complete", "partial", "failed", "paused", "stopped", "interrupted"].includes(status.state)) {
        // Failed runs may still have partial evidence. Both datasets remain separate.
        await loadResults();
        activeJob = null;
        setBusy(false);
      }
      scheduleStatus();
    } catch (error) {
      monitoring = false;
      connectionError(`${text(error.message, "Could not reach the local service.")} Status checks are paused. Retry to reconnect.`);
    }
  }

  window.CompSetCollectionStatus = function (status) {
    if (!status || !["idle", "running", "complete", "partial", "failed", "paused", "stopped", "interrupted"].includes(status.state)) return;
    // A workspace read may have no own job while a legacy collector is active.
    if (status.state === "idle" && jobState === "running") return;
    const previous = jobState;
    activeJob = status.state === "running" ? status.legacy ? status.command || "legacy" : "workspace" : null;
    setStatus(status.state, status.message);
    if (!legacyInitialized) return;
    if (status.state === "running") { monitoring = true; scheduleStatus(); }
    else if (previous === "running") {
      clearTimeout(timer);
      loadResults().catch(error => connectionError(text(error.message, "Could not reload saved collection results.")));
    }
  };

  async function initialize() {
    monitoring = true;
    await checkStatus(false);
    await loadResults();
  }

  function readContext() {
    $("form-error").hidden = true;
    if (!form.reportValidity()) return null;
    const checkin = $("checkin").value;
    const checkout = $("checkout").value;
    if (!localDate(checkin) || !localDate(checkout) || checkout <= checkin) {
      $("form-error").textContent = "Check-out must be after check-in.";
      $("form-error").hidden = false;
      $("checkout").focus();
      return null;
    }
    const payload = { listing: $("listing").value.trim(), checkin, checkout, adults: Number($("adults").value), currency: $("currency").value.trim().toUpperCase(), start_date: $("start-date").value, days: Number($("days").value) };
    if (!payload.listing) {
      $("form-error").textContent = "Enter an Airbnb listing URL or listing ID.";
      $("form-error").hidden = false;
      $("listing").focus();
      return null;
    }
    return payload;
  }

  async function startJob(path, payload, kind) {
    if (requestPending || jobState === "running") return;
    requestPending = true;
    pauseRequested = false;
    activeJob = kind;
    setBusy(true);
    try {
      const result = await api(path, { method: "POST", headers: { "Content-Type": "application/json", "X-CompSet-Request": "dashboard-v1" }, body: JSON.stringify(payload) });
      if (result.state !== "running") throw new Error("The local service did not confirm that collection started.");
      monitoring = true;
      setStatus("running", kind === "inventory" ? "Collecting public inventory observations. Saved records remain available; pause between steps when needed." : kind === "discover" ? "Discovering candidates from the selected comparison area. This may take a few minutes." : kind === "monitor" ? "Refreshing selected calendars and stay quotes. Coverage will remain explicit." : "Collecting the subject’s public observations.");
      $("connection-error").hidden = true;
      scheduleStatus();
    } catch (error) {
      const errorTarget = $(kind === "inventory" ? "inventory-error" : "form-error");
      errorTarget.textContent = text(error.message, "Collection could not start.");
      errorTarget.hidden = false;
      activeJob = null;
    } finally {
      requestPending = false;
      setBusy(jobState === "running");
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (requestPending || jobState === "running") return;
    const payload = readContext();
    if (!payload) return;
    const center = listingCoordinates({ lat: $("center-lat").value, lng: $("center-lng").value });
    const radius = numberValue($("radius").value);
    if (!center || radius === null || radius < 0.25 || radius > 10) {
      $("form-error").textContent = "Set a valid map center and a radius between 0.25 and 10 km.";
      $("form-error").hidden = false;
      return;
    }
    await startJob("/api/discover", { ...payload, center_lat: center[0], center_lng: center[1], radius_km: radius, target: 100, budget: 18 }, "discover");
  });

  $("run-button").addEventListener("click", async () => {
    if (requestPending || jobState === "running") return;
    const payload = readContext();
    if (payload) { $("subject-details").open = true; await startJob("/api/run", payload, "subject"); }
  });
  $("monitor-button").addEventListener("click", () => startJob("/api/monitor", {}, "monitor"));
  form.addEventListener("input", () => { formEdited = true; });

  for (const id of ["center-lat", "center-lng"]) $(id).addEventListener("change", () => {
    const coordinates = listingCoordinates({ lat: $("center-lat").value, lng: $("center-lng").value });
    if (coordinates) setMapCenter(coordinates, true, true);
  });
  $("radius").addEventListener("input", () => {
    const radius = numberValue($("radius").value);
    if (radius !== null && radius >= 0.25 && radius <= 10) {
      centerEdited = true;
      if (searchCircle) searchCircle.setRadius(radius * 1000);
      updateBoundaryNote();
    }
  });
  $("subject-center-button").addEventListener("click", () => setMapCenter(subjectCenter, true, true));
  $("show-search-cells").addEventListener("change", () => {
    if (!searchMap || !cellLayer) return;
    $("show-search-cells").checked ? cellLayer.addTo(searchMap) : searchMap.removeLayer(cellLayer);
  });
  for (const button of candidateFilters) button.addEventListener("click", () => {
    candidateFilter = button.dataset.candidateFilter;
    candidatePage = 0;
    for (const filter of candidateFilters) {
      const selected = filter === button;
      filter.classList.toggle("active", selected);
      filter.setAttribute("aria-pressed", String(selected));
    }
    renderCandidates();
  });
  $("candidate-previous").addEventListener("click", () => { candidatePage = Math.max(0, candidatePage - 1); renderCandidates(); });
  $("candidate-next").addEventListener("click", () => { candidatePage += 1; renderCandidates(); });
  for (const view of ["rates", "portfolio", "comparison", "prices"]) $("view-" + view).addEventListener("click", () => selectView(view));
  $("prices-refresh").addEventListener("click", loadSavedPrices);
  for (const id of ["one-night-listing", "one-night-filter"]) $(id).addEventListener("change", () => { oneNightPage = 0; renderOneNightTable(); });
  $("hotel-source-filter").addEventListener("change", () => renderHotel(hotelSnapshot));
  $("one-night-previous").addEventListener("click", () => { oneNightPage = Math.max(0, oneNightPage - 1); renderOneNightTable(); });
  $("one-night-next").addEventListener("click", () => { oneNightPage += 1; renderOneNightTable(); });
  $("portfolio-search").addEventListener("input", () => { portfolioPage = 0; renderPortfolioTable(); });
  $("portfolio-country").addEventListener("change", () => { portfolioPage = 0; refreshPortfolioFilters(); renderPortfolioTable(); });
  for (const id of ["portfolio-city", "portfolio-currency"]) $(id).addEventListener("change", () => { portfolioPage = 0; renderPortfolioTable(); });
  $("portfolio-previous").addEventListener("click", () => { portfolioPage = Math.max(0, portfolioPage - 1); renderPortfolioTable(); });
  $("portfolio-next").addEventListener("click", () => { portfolioPage += 1; renderPortfolioTable(); });
  $("inventory-form").addEventListener("input", () => { inventoryEdited = true; });
  $("inventory-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (requestPending || jobState === "running") return;
    $("inventory-error").hidden = true;
    if (!$("inventory-form").reportValidity()) return;
    const checkin = $("inventory-checkin").value;
    const checkout = $("inventory-checkout").value;
    if (!localDate(checkin) || !localDate(checkout) || checkout <= checkin) { $("inventory-error").textContent = "Check-out must be after check-in."; $("inventory-error").hidden = false; $("inventory-checkout").focus(); return; }
    await startJob("/api/inventory-refresh", { checkin, checkout, adults: Number($("inventory-adults").value) }, "inventory");
  });
  $("inventory-pause-button").addEventListener("click", async () => {
    $("inventory-error").hidden = true;
    try {
      await api("/api/inventory-pause", { method: "POST", headers: { "Content-Type": "application/json", "X-CompSet-Request": "dashboard-v1" }, body: "{}" });
      pauseRequested = true;
      $("inventory-pause-button").disabled = true;
      $("inventory-pause-button").textContent = "Pause requested…";
      $("job-message").textContent = "Pause requested. The current collection step will finish before stopping.";
    } catch (error) { $("inventory-error").textContent = text(error.message, "Pause could not be requested."); $("inventory-error").hidden = false; }
  });
  $("inventory-view-refresh").addEventListener("click", initialize);

  for (const button of filters) {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.filter;
      for (const filter of filters) {
        const selected = filter === button;
        filter.classList.toggle("active", selected);
        filter.setAttribute("aria-pressed", String(selected));
      }
      renderCalendar();
    });
  }
  $("retry-button").addEventListener("click", initialize);
  window.addEventListener("beforeunload", () => { monitoring = false; clearTimeout(timer); });
  setDefaults();
  window.CompSetOpenTools = () => selectView("comparison");
  selectView("rates");
  if (window.CompSetDual) window.CompSetDual.mount($("rates-workspace"));
  else if (window.CompSetRates) { window.CompSetRates.mount($("rates-workspace")); legacyInitialized = true; initialize(); }
  else { $("rates-workspace").textContent = "The rate workspace needs the updated local service. Restart CompSet Studio, then reload this page. Your saved evidence is still available in Property portfolio and Saved prices."; legacyInitialized = true; initialize(); }
})();
