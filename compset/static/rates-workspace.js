"use strict";

/* Saved evidence plus explicit, bounded collection jobs. Reads never start work. */
(function (global) {
  const STATES = ["quoted", "indicative", "unavailable", "restricted", "unknown"];
  const JOB_STATES = ["idle", "running", "paused", "partial", "complete", "stopped", "failed", "interrupted"];
  const STATE_LABELS = { quoted: "Exact quote", indicative: "Indicative", unavailable: "Unavailable", restricted: "Stay restricted", unknown: "Unknown" };
  const SOURCES = { google_hotels: "Google Hotels", agoda: "Agoda", booking: "Booking.com", expedia: "Expedia", makemytrip: "MakeMyTrip", airbnb: "Airbnb", hotels_com: "Hotels.com", goibibo: "Goibibo" };
  const present = value => value !== undefined && value !== null && value !== "";
  const array = value => Array.isArray(value) ? value : [];
  const str = (value, fallback = "Not observed") => present(value) ? String(value) : fallback;
  const human = value => str(value).replace(/_/g, " ");
  const sourceName = value => SOURCES[value] || human(value);
  const stateOf = cell => STATES.includes(cell.state) ? cell.state : "unknown";
  const count = value => Number.isInteger(value) && value >= 0 ? String(value) : "—";
  const summarize = value => {
    if (!present(value)) return "Not observed";
    if (Array.isArray(value)) return value.map(summarize).join(" · ") || "None recorded";
    if (typeof value === "object") return Object.entries(value).map(([key, item]) => `${human(key)}: ${summarize(item)}`).join(" · ");
    return value === true ? "Yes" : value === false ? "No" : String(value);
  };

  function safeUrl(value) {
    if (typeof value !== "string") return null;
    try {
      const url = new URL(value);
      if (!["https:", "http:"].includes(url.protocol) || url.username || url.password || url.port) return null;
      const host = url.hostname.toLowerCase().replace(/\.$/, "");
      if (!host.includes(".") || host === "localhost" || host.endsWith(".localhost") || host.endsWith(".local") || host.includes(":")) return null;
      // Property links must be public hostnames; IP literals are never useful here.
      if (/^\d+(?:\.\d+){3}$/.test(host)) return null;
      return url.href;
    } catch (_) { return null; }
  }

  function dateLabel(value, short = false) {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return str(value);
    const date = new Date(`${value}T12:00:00Z`);
    if (Number.isNaN(date.getTime())) return str(value);
    return date.toLocaleDateString("en-GB", { timeZone: "UTC", day: "numeric", month: "short", ...(short ? {} : { year: "numeric" }) });
  }

  function observedLabel(value) {
    if (!present(value)) return "Observation time unknown";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Observation time unknown";
    return `${date.toLocaleString("en-GB", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })} IST`;
  }

  function ageLabel(value, now = Date.now()) {
    const milliseconds = new Date(value).getTime();
    if (!present(value) || !Number.isFinite(milliseconds)) return "Time unknown";
    const hours = Math.floor((now - milliseconds) / 3600000);
    if (hours < 0) return "Check source timestamp";
    if (hours < 1) return "Observed less than 1h ago";
    if (hours < 24) return `Observed ${hours}h ago`;
    return `Historical · ${Math.floor(hours / 24)}d old`;
  }

  function priceLabel(cell) {
    const state = stateOf(cell);
    if (!["quoted", "indicative"].includes(state)) return STATE_LABELS[state];
    // Keep decimal strings verbatim. Never divide, convert, round or fill a missing price.
    if (present(cell.amount)) return `${str(cell.currency, "")} ${str(cell.amount)}`.trim();
    return present(cell.display_amount) ? str(cell.display_amount) : "Price not reported";
  }

  function cellKey(entity, date) { return `${entity}\u0000${date}`; }

  function visibleModel(dataset, options = {}) {
    const dates = [...new Set(array(dataset.dates))].sort();
    const lastPage = Math.max(0, Math.ceil(dates.length / 7) - 1);
    const page = Math.max(0, Math.min(lastPage, Number.isInteger(options.page) ? options.page : 0));
    const windowDates = dates.slice(page * 7, page * 7 + 7);
    const query = str(options.query, "").trim().toLocaleLowerCase();
    const index = new Map(array(dataset.cells).map(cell => [cellKey(cell.entity_id, cell.date), cell]));
    const rows = array(dataset.entities).filter(entity =>
      (!options.source || options.source === "all" || entity.source === options.source) &&
      (!query || `${entity.label} ${entity.id} ${sourceName(entity.source)}`.toLocaleLowerCase().includes(query))
    ).map(entity => {
      const cells = windowDates.map(date => index.get(cellKey(entity.id, date)) || {
        entity_id: entity.id, date, checkout: null, state: "unknown", amount: null,
        currency: dataset.currency, reason: "not_observed", offers: [], observed_at: null,
      });
      return { entity, cells };
    }).filter(row => !options.state || options.state === "all" || row.cells.some(cell => stateOf(cell) === options.state));
    const cells = rows.flatMap(row => row.cells.filter(cell => !options.state || options.state === "all" || stateOf(cell) === options.state).map(cell => ({ entity: row.entity, cell })));
    return { dates: windowDates, page, lastPage, rows, cells };
  }

  function csvField(value) {
    let result = value === null || value === undefined ? "" : typeof value === "object" ? JSON.stringify(value) : String(value);
    // Spreadsheet formula guards include whitespace/control prefixes, not just '='.
    if (/^[\s\u0000-\u001f\u007f]*[=+\-@]/.test(result) || /^[\t\r\n]/.test(result)) result = `'${result}`;
    return `"${result.replace(/"/g, '""')}"`;
  }

  function exportCsv(dataset, options = {}) {
    const headers = ["dataset", "entity_id", "entity", "observation_source", "role", "checkin", "checkout", "state", "amount", "display_amount", "currency", "precision", "amount_basis", "observed_at", "reason", "offer_count", "source_url", "requested_context", "offers"];
    const rows = visibleModel(dataset, options).cells.map(({ entity, cell }) => [
      dataset.label, entity.id, entity.label, entity.source, entity.role, cell.date, cell.checkout,
      stateOf(cell), ["quoted", "indicative"].includes(stateOf(cell)) ? cell.amount : null,
      ["quoted", "indicative"].includes(stateOf(cell)) ? cell.display_amount : null,
      cell.currency, cell.precision, cell.amount_basis, cell.observed_at, cell.reason,
      array(cell.offers).length, safeUrl(entity.source_url), dataset.context || {}, array(cell.offers),
    ]);
    return [headers, ...rows].map(row => row.map(csvField).join(",")).join("\r\n");
  }

  function contextSummary(context = {}, currency) {
    const parts = [];
    if (present(context.adults)) parts.push(`${context.adults} adult${context.adults === 1 ? "" : "s"}`);
    if (present(context.children)) parts.push(`${context.children} children`);
    if (present(context.rooms)) parts.push(`${context.rooms} room${context.rooms === 1 ? "" : "s"}`);
    if (present(context.stay_nights)) parts.push(`${context.stay_nights} night${context.stay_nights === 1 ? "" : "s"}`);
    if (present(context.currency || currency)) parts.push(str(context.currency || currency));
    return parts.length ? parts.join(" · ") : "See each observation for stay context";
  }

  let controller = null;

  function mount(root) {
    if (!root || typeof root.replaceChildren !== "function") throw new TypeError("CompSetRates.mount requires a DOM element");
    if (controller && controller.root === root) return controller.refresh();
    if (controller) controller.destroy();
    controller = createController(root);
    return controller.refresh();
  }

  function mountCollection(root, options = {}) {
    if (!root || typeof root.replaceChildren !== "function") throw new TypeError("Collection dock requires a DOM element");
    if (!["aketa", "airbnb-compset"].includes(options.datasetId)) throw new TypeError("Unsupported collection dataset");
    const dock = createController(root, { collectionOnly: true, datasetId: options.datasetId, onReload: options.onReload });
    // Mount only checks ownership. The containing view owns its initial data reads.
    dock.ready = dock.refreshStatus();
    return dock;
  }

  function createController(root, settings = {}) {
    const doc = root.ownerDocument || global.document;
    const state = { payload: null, dataset: "aketa", tab: "rates", mode: "calendar", page: 0, source: "all", evidence: "all", query: "", listPage: 0, candidateQuery: "", candidateFilter: "all", portfolioQuery: "", portfolioCity: "all", loading: false, error: null, requestId: 0, job: null, jobKnown: false, jobLoading: false, jobError: null, action: null };
    if (settings.collectionOnly) {
      state.dataset = settings.datasetId;
      state.payload = { datasets: [{ id: "aketa", label: "Hotel Aketa · Dehradun" }, { id: "airbnb-compset", label: "Saved Dubai Airbnb comparison set" }] };
    }
    let dialog = null;
    let returnFocus = null;
    let refreshButton = null;
    let fetchButton = null;
    let jobRegion = null;
    let pollTimer = null;
    let jobRequestId = 0;
    let alive = true;
    let queuedSavedReload = false;
    const el = (tag, className, value) => {
      const node = doc.createElement(tag);
      if (className) node.className = className;
      if (value !== undefined) node.textContent = str(value, "");
      return node;
    };
    const append = (node, ...children) => { children.filter(Boolean).forEach(child => node.appendChild(child)); return node; };
    const button = (label, action, className = "rw-button") => {
      const node = el("button", className, label);
      node.type = "button";
      node.addEventListener("click", action);
      return node;
    };
    const badge = (text, style = "unknown") => el("span", `rw-badge rw-${style}`, text);
    const p = (text, className = "rw-muted") => el("p", className, text);
    const current = () => array(state.payload && state.payload.datasets).find(item => item.id === state.dataset) || null;
    const options = () => ({ page: state.page, source: state.source, state: state.evidence, query: state.query });
    const link = (url, label) => {
      const href = safeUrl(url);
      if (!href) return el("span", "rw-muted", label);
      const node = el("a", "rw-link", label);
      node.href = href; node.target = "_blank"; node.rel = "noopener noreferrer";
      return node;
    };
    const field = (label, control) => {
      const node = el("label", "rw-field");
      append(node, el("span", "rw-field-label", label), control);
      return node;
    };
    const select = (items, selected, callback) => {
      const node = el("select", "rw-select");
      for (const [value, label] of items) { const option = el("option", "", label); option.value = value; node.appendChild(option); }
      node.value = selected;
      node.addEventListener("change", () => callback(node.value));
      return node;
    };
    const search = (value, placeholder, callback) => {
      const node = el("input", "rw-search");
      node.type = "search"; node.value = value; node.placeholder = placeholder;
      node.addEventListener("input", () => callback(node.value));
      return node;
    };
    const facts = entries => {
      const list = el("dl", "rw-facts");
      for (const [label, value] of entries) append(list, el("dt", "", label), el("dd", "", summarize(value)));
      return list;
    };
    const table = (headers, label) => {
      const scroll = el("div", "rw-table-scroll");
      scroll.tabIndex = 0; scroll.setAttribute("role", "region"); scroll.setAttribute("aria-label", label);
      const node = el("table", "rw-table");
      append(node, el("caption", "rw-sr-only", label));
      const head = el("thead"), row = el("tr");
      headers.forEach(value => { const th = el("th", "", value); th.scope = "col"; row.appendChild(th); });
      head.appendChild(row); node.appendChild(head);
      const body = el("tbody"); node.appendChild(body); scroll.appendChild(node);
      return { scroll, node, body };
    };
    const sectionHead = (title, description, aside) => append(el("div", "rw-section-head"), append(el("div"), el("h3", "", title), p(description)), aside);
    const empty = message => p(message, "rw-empty");
    const busy = job => Boolean(job && (job.busy === true || job.state === "running"));
    const jobDatasetName = job => {
      if (job && job.legacy) return "Other collection in this workspace";
      const dataset = array(state.payload && state.payload.datasets).find(item => job && item.id === job.dataset_id);
      return dataset ? dataset.label : job && job.dataset_id === "aketa" ? "Hotel Aketa · Dehradun" : job && job.dataset_id === "airbnb-compset" ? "Airbnb · saved Dubai set" : "Collection";
    };

    function clearPoll() { if (pollTimer !== null) global.clearTimeout(pollTimer); pollTimer = null; }
    function schedulePoll() {
      clearPoll();
      if (alive && state.jobKnown && busy(state.job) && !state.action) {
        pollTimer = global.setTimeout(() => { pollTimer = null; return loadJob(); }, 3000);
      }
    }

    async function jobRequest(path, body) {
      const response = await global.fetch(path, {
        method: body ? "POST" : "GET", cache: "no-store", credentials: "same-origin",
        headers: body ? { Accept: "application/json", "Content-Type": "application/json", "X-CompSet-Request": "dashboard-v1" } : { Accept: "application/json" },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      if (!response.ok) {
        let message = response.status === 404 ? "Restart CompSet Studio to load the updated collection service." : `Collection request returned HTTP ${response.status}.`;
        if (response.status !== 404) {
          try { const detail = await response.json(); if (typeof detail.error === "string") message += ` ${detail.error}`; } catch (_) { /* Preserve status when the error body is not JSON. */ }
        }
        const error = new Error(message); error.httpStatus = response.status; throw error;
      }
      const job = await response.json();
      if (!job || !JOB_STATES.includes(job.state) || (job.state === "running" && !job.job_id && job.legacy !== true)) throw new Error("Collection status has an unsupported format.");
      return job;
    }

    function acceptJob(job) {
      const previous = state.job;
      if (previous && previous.job_id && previous.state === "running" && job.state !== "running" && previous.job_id !== job.job_id) {
        throw new Error("Collection status returned a different job. Check its status before starting another collection.");
      }
      if (previous && previous.job_id && previous.job_id === job.job_id && present(previous.updated_at) && present(job.updated_at) && new Date(job.updated_at).getTime() < new Date(previous.updated_at).getTime()) return previous;
      state.job = job; state.jobKnown = true;
      if (typeof global.CompSetCollectionStatus === "function") global.CompSetCollectionStatus(job);
      const ended = busy(previous) && !busy(job) && (previous.legacy === true || previous.job_id === job.job_id);
      if (ended) reloadSaved();
      return job;
    }

    async function loadJob({ schedule = true } = {}) {
      if (!alive) return null;
      const requestId = ++jobRequestId;
      state.jobLoading = true; updateJobView();
      try {
        const job = await jobRequest("/api/workspace/job");
        if (!alive || requestId !== jobRequestId) return null;
        state.jobError = null;
        return acceptJob(job);
      } catch (error) {
        if (alive && requestId === jobRequestId) {
          state.jobKnown = false;
          state.jobError = `Could not verify collection status. ${error.message} No collection is started automatically.`;
        }
        return null;
      } finally {
        if (alive && requestId === jobRequestId) {
          state.jobLoading = false; updateJobView();
          if (schedule) schedulePoll();
        }
      }
    }

    async function startCollection(mode, datasetId, resumeJobId = null) {
      if (!alive || state.action || !state.jobKnown || busy(state.job)) return;
      state.action = mode; state.jobError = null; clearPoll(); ++jobRequestId; updateJobView();
      try {
        // The explicit click authorizes one start. Check global collector ownership first.
        const latest = await loadJob({ schedule: false });
        if (!alive || !latest) return;
        if (busy(latest)) { state.jobError = "A collection is already running. Follow its progress below."; return; }
        if (mode === "resume" && (latest.job_id !== resumeJobId || latest.dataset_id !== datasetId || !["paused", "partial"].includes(latest.state))) {
          state.jobError = "The resumable job changed. Review its current status before resuming."; return;
        }
        ++jobRequestId;
        const job = await jobRequest("/api/workspace/collect", { dataset_id: datasetId, mode });
        if (!alive) return;
        if (job.dataset_id !== datasetId || !job.job_id) throw new Error("Collection start returned a different dataset or an unknown job identity.");
        acceptJob(job);
        if (!busy(job)) reloadSaved();
      } catch (error) {
        if (!alive) return;
        state.jobKnown = false;
        if (error.httpStatus === 409) await loadJob({ schedule: false });
        state.jobError = `Could not ${mode === "resume" ? "resume" : "start"} collection. ${error.message} The start was not retried.`;
      } finally {
        if (alive) { state.action = null; state.jobLoading = false; updateJobView(); schedulePoll(); }
      }
    }

    async function pauseCollection(jobId) {
      const currentJob = state.job;
      if (!alive || state.action || !state.jobKnown || !busy(currentJob) || currentJob.job_id !== jobId || currentJob.pause_supported === false || currentJob.pause_requested) return;
      state.action = "pause"; state.jobError = null; clearPoll(); ++jobRequestId; updateJobView();
      try {
        const job = await jobRequest("/api/workspace/pause", { job_id: jobId });
        if (!alive) return;
        if (job.job_id !== jobId || job.dataset_id !== currentJob.dataset_id) throw new Error("Pause returned a different collection identity.");
        acceptJob(job);
      } catch (error) {
        if (alive) { state.jobKnown = false; state.jobError = `Could not confirm the pause. ${error.message} Check collection status before taking another action.`; }
      } finally {
        if (alive) { state.action = null; updateJobView(); schedulePoll(); }
      }
    }

    function updateJobView() {
      if (fetchButton) {
        fetchButton.disabled = !current() || !state.jobKnown || busy(state.job) || Boolean(state.action);
        fetchButton.textContent = state.action === "fresh" ? "Starting collection…" : "Fetch fresh data";
      }
      if (!jobRegion) return;
      jobRegion.replaceChildren();
      const job = state.job;
      if (state.jobError) { const error = p(state.jobError, "rw-error"); error.setAttribute("role", "alert"); jobRegion.appendChild(error); }
      const panel = el("div", `rw-job-panel${busy(job) ? " rw-job-active" : ""}`);
      const heading = el("div", "rw-job-heading");
      const status = !state.jobKnown ? state.jobLoading ? "Checking status" : "Status unverified" : job ? human(job.state) : "Idle";
      append(heading, append(el("div"), el("h3", "", job && job.state !== "idle" ? jobDatasetName(job) : "Collection control"),
        p(job && job.state !== "idle" ? `${job.legacy ? "Other active collector" : `Job ${str(job.job_id)}`} · ${human(job.phase)}` : "Fresh collection checks the next 30 local arrival dates. View filters do not change its membership or guests.", "rw-job-subtitle")),
        badge(status, !state.jobKnown || busy(job) ? "unknown" : job && job.state === "complete" ? "quoted" : "indicative"));
      panel.appendChild(heading);
      if (job && job.state !== "idle") {
        const message = p(job.message || "Waiting for the next saved job update.", "rw-job-message"); message.setAttribute("role", "status"); message.setAttribute("aria-live", "polite"); panel.appendChild(message);
        if (job.context && Object.keys(job.context).length) {
          const context = job.context;
          const dates = context.start_date ? `${present(context.days) ? `${context.days} arrival dates from ` : "From "}${dateLabel(context.start_date)}` : [context.checkin, context.checkout].filter(present).map(value => dateLabel(value)).join(" → ");
          panel.appendChild(p(`${contextSummary(context)}${dates ? ` · ${dates}` : ""} · ${human(job.mode)}`, "rw-job-context"));
          const details = el("details", "rw-job-context-details"); append(details, el("summary", "", "Actual collection context"), el("pre", "rw-raw-evidence", JSON.stringify(context, null, 2))); panel.appendChild(details);
        }
        const progress = job.progress && typeof job.progress === "object" ? Object.entries(job.progress) : [];
        if (progress.length) {
          const list = el("dl", "rw-job-progress");
          progress.forEach(([key, value]) => append(list, append(el("div"), el("dt", "", human(key)), el("dd", "", summarize(value)))));
          panel.appendChild(list);
        }
        panel.appendChild(p(`Last job update: ${observedLabel(job.updated_at)}. Finishing a run or its budget does not mean every date has a verified price.`, "rw-job-note"));
      } else panel.appendChild(p("Aketa: one adult, one room, no children, INR. Airbnb: one adult in the saved subject and selected set, in its source currency. Calendars refresh before bounded one-night quote checks.", "rw-job-note"));
      const controls = el("div", "rw-job-actions");
      if (job && busy(job) && job.job_id && job.pause_supported !== false) {
        const pause = button(job.pause_requested ? "Pause requested…" : state.action === "pause" ? "Requesting pause…" : "Pause collection", () => pauseCollection(job.job_id));
        pause.disabled = !state.jobKnown || Boolean(state.action) || job.pause_requested === true;
        append(controls, pause, p("Pause takes effect between collection steps.", "rw-job-note"));
      }
      if (job && ["paused", "partial"].includes(job.state) && job.job_id && job.dataset_id) {
        const resume = button(state.action === "resume" ? "Resuming…" : "Resume collection", () => startCollection("resume", job.dataset_id, job.job_id), "rw-button rw-resume");
        resume.disabled = !state.jobKnown || Boolean(state.action) || busy(job);
        append(controls, resume, p(`Resumes ${jobDatasetName(job)}; changing the viewed dataset does not change this job.`, "rw-job-note"));
      }
      if (!state.jobKnown || (job && job.state === "interrupted")) {
        const check = button(state.jobLoading ? "Checking status…" : "Check collection status", () => loadJob()); check.disabled = state.jobLoading || Boolean(state.action); controls.appendChild(check);
      }
      if (controls.children.length) panel.appendChild(controls);
      jobRegion.appendChild(panel);
    }

    function coverageNote() {
      const payload = state.payload || {}, portfolio = payload.portfolio || {}, summary = portfolio.summary || {};
      const properties = Number.isInteger(summary.property_count) ? summary.property_count : array(portfolio.properties).length;
      const unlinked = Number.isInteger(summary.airbnb_listing_count) && Number.isInteger(summary.airbnb_linked_count) ? Math.max(0, summary.airbnb_listing_count - summary.airbnb_linked_count) : null;
      const airbnb = array(payload.datasets).find(item => item.id === "airbnb-compset");
      const hotel = array(payload.datasets).find(item => item.id === "aketa");
      const note = el("div", "rw-scope-note");
      note.appendChild(el("strong", "", "Current evidence coverage"));
      note.appendChild(p(`${properties} returned public BnBMe properties${unlinked !== null ? ` · ${unlinked} Airbnb records without a verified portfolio link` : " · Airbnb portfolio links not established here"}.`));
      if (airbnb) {
        const subjects = array(airbnb.entities).filter(item => item.role === "subject").length;
        const selected = array(airbnb.candidates).filter(candidateSelected).length;
        note.appendChild(p(`${subjects} saved Dubai subject${subjects === 1 ? "" : "s"} · ${selected} selected Airbnb competitors. Compsets for every BnBMe property have not been established.`));
      }
      if (hotel) note.appendChild(p(`Aketa: ${array(hotel.entities).length} observation sources · ${array(hotel.profiles).length} property profiles · ${array(hotel.candidates).length ? `${array(hotel.candidates).filter(candidateSelected).length} selected hotel competitors` : "no hotel competitor set collected"}.`));
      note.appendChild(p("Returned public properties do not establish complete corporate inventory."));
      return note;
    }

    function closeDialog(focus = true) {
      if (!dialog) return;
      dialog.remove(); dialog = null;
      if (focus) {
        const target = returnFocus && returnFocus.isConnected ? returnFocus : refreshButton;
        if (target && typeof target.focus === "function") target.focus();
      }
      returnFocus = null;
    }

    function openDialog(title, contents, trigger) {
      closeDialog(false);
      returnFocus = trigger || doc.activeElement;
      const mask = el("div", "rw-drawer-mask");
      const panel = el("section", "rw-drawer");
      panel.setAttribute("role", "dialog"); panel.setAttribute("aria-modal", "true"); panel.setAttribute("aria-labelledby", "rw-detail-title");
      const heading = el("h2", "", title); heading.id = "rw-detail-title";
      const close = button("Close ×", () => closeDialog(), "rw-button rw-close");
      append(panel, append(el("div", "rw-drawer-heading"), heading, close), contents);
      mask.appendChild(panel); mask.addEventListener("click", event => { if (event.target === mask) closeDialog(); });
      root.appendChild(mask); dialog = mask; close.focus();
    }

    function keyboard(event) {
      if (!dialog) return;
      if (event.key === "Escape") { event.preventDefault(); closeDialog(); }
      if (event.key === "Tab") {
        const focusable = Array.from(dialog.querySelectorAll("button, a[href], input, select, [tabindex='0']")).filter(node => !node.disabled && !node.hidden);
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (!first) return;
        if (event.shiftKey && doc.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && doc.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    }
    doc.addEventListener("keydown", keyboard);

    function offerCard(offer, index) {
      const card = el("section", "rw-offer");
      const amount = priceLabel({ ...offer, state: offer.precision === "exact" || offer.precision === "source_exact" ? "quoted" : "indicative", display_amount: offer.display_amount || offer.display });
      append(card, append(el("div", "rw-offer-heading"), el("h4", "", offer.room_name || offer.room_type || offer.room || `Offer ${index + 1}`), el("strong", "rw-offer-amount", amount)));
      const fields = [
        ["Rate plan", offer.rate_plan_name || offer.rate_plan || offer.provider_rate_plan_id],
        ["Basis / precision", [offer.amount_basis || offer.amount_type, offer.precision].filter(present).map(human).join(" · ") || null],
        ["Displayed supplier", sourceName(offer.channel || offer.supplier || offer.source)],
        ["Meals", offer.meal_plan || offer.meals || (present(offer.breakfast_included) ? { breakfast_included: offer.breakfast_included } : null)],
        ["Taxes included", offer.taxes_included], ["Fees included", offer.fees_included],
        ["Tax amount", offer.taxes], ["Fee amount", offer.fees],
        ["Taxes / fees", offer.taxes_and_fees || offer.tax_details || offer.fee_details],
        ["Cancellation", offer.cancellation_policy || offer.cancellation_terms || offer.cancellation || (present(offer.refundable) ? { refundable: offer.refundable } : null)],
        ["Payment", offer.payment_terms || offer.payment],
        ["Membership required", offer.membership_required],
        ["Membership terms", offer.membership],
        ["Offer conditions", offer.conditions],
        ["Discount conditions", offer.discount_conditions],
        ["Coupon", offer.coupon],
        ["Observed stay context", offer.observed_context],
        ["Context verified", offer.context_verified],
        ["Observed", observedLabel(offer.observed_at)],
      ];
      append(card, facts(fields));
      if (array(offer.rate_options).length) {
        const alternatives = el("div", "rw-rate-options");
        alternatives.appendChild(el("h4", "", "Reported rate options"));
        for (const option of offer.rate_options) {
          append(alternatives, append(el("section", "rw-rate-option"),
            append(el("div", "rw-offer-heading"), el("strong", "", option.rate_plan_name || option.rate_plan_id || "Rate option"),
              badge(option.is_selected === true ? "Selected quote" : "Alternative", option.is_selected === true ? "quoted" : "unknown")),
            facts([["Amount", present(option.amount) ? `${str(option.currency, "")} ${option.amount}` : "Not observed"],
              ["Basis", human(option.amount_basis)], ["Cancellation", option.cancellation_terms],
              ["Taxes included", option.taxes_included], ["Fees included", option.fees_included],
              ["Observed", observedLabel(option.observed_at)]])));
        }
        card.appendChild(alternatives);
      }
      const details = el("details", "rw-evidence");
      append(details, el("summary", "", "All saved offer fields"), el("pre", "", JSON.stringify(offer, null, 2)));
      card.appendChild(details);
      return card;
    }

    function showCell(dataset, entity, cell, trigger) {
      const body = el("div", "rw-drawer-body");
      append(body, append(el("div", "rw-detail-status"), badge(STATE_LABELS[stateOf(cell)], stateOf(cell)), el("strong", "", priceLabel(cell))),
        p(`${dateLabel(cell.date)} → ${dateLabel(cell.checkout)} · ${sourceName(entity.source)}`),
        p(cell.selection_note || (array(cell.offers).length > 1 ? "The grid summarizes observed offers for this source and stay. Room, meal and payment conditions can differ; every saved alternative is below." : "This observation applies only to its recorded stay and guest context."), "rw-callout"),
        facts([["Observed", observedLabel(cell.observed_at)], ["Freshness", ageLabel(cell.observed_at)], ["Price basis", human(cell.amount_basis)], ["Precision", human(cell.precision)], ["Reason", human(cell.reason)], ["Request context", dataset.context], ["Source", sourceName(entity.source)]]));
      if (stateOf(cell) === "unavailable") body.appendChild(p("No offer was available for this source and requested stay. This does not establish that the property is booked.", "rw-callout"));
      if (stateOf(cell) === "restricted") body.appendChild(p("The requested stay does not meet the observed calendar rules. A minimum stay or arrival restriction is not a booking.", "rw-callout"));
      if (stateOf(cell) === "unknown") body.appendChild(p("A usable result was not observed. The missing price is not zero and does not establish availability.", "rw-callout"));
      const offers = array(cell.offers);
      body.appendChild(el("h3", "rw-detail-subtitle", `${offers.length} saved offer${offers.length === 1 ? "" : "s"}`));
      offers.forEach((offer, i) => body.appendChild(offerCard(offer, i)));
      if (!offers.length) body.appendChild(empty("No offer details for this date."));
      body.appendChild(link(entity.source_url, "Open public property page ↗"));
      openDialog(entity.label, body, trigger);
    }

    function changeDataset(id) {
      state.dataset = id; state.page = 0; state.source = "all"; state.evidence = "all"; state.query = ""; state.listPage = 0;
      closeDialog(false); render();
    }

    function download(dataset) {
      const csv = exportCsv(dataset, options());
      const blob = new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const anchor = el("a"); anchor.href = url;
      const view = visibleModel(dataset, options());
      anchor.download = `${dataset.id}-${view.dates[0] || "undated"}-${view.dates[view.dates.length - 1] || "undated"}-evidence.csv`;
      root.appendChild(anchor); anchor.click(); anchor.remove();
      global.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    function metricCards(dataset) {
      const metrics = el("div", "rw-metrics");
      metrics.setAttribute("aria-label", "Full saved date window coverage; unaffected by view filters");
      const values = dataset.summary || {};
      const definitions = [["date_cells", "Planned cells", "Source × date", "total"], ["quoted_cells", "Exact quotes", "Original stated basis", "quoted"], ["indicative_cells", "Indicative prices", "Display or calendar", "indicative"], ["unavailable_cells", "Unavailable", "Requested stay only", "unavailable"], ["restricted_cells", "Stay restricted", "Calendar rules", "restricted"], ["unknown_cells", "Unknown", "No usable observation", "unknown"]];
      for (const [key, label, note, style] of definitions) append(metrics, append(el("div", `rw-metric rw-metric-${style}`), el("span", "rw-metric-label", label), el("strong", "", count(values[key])), el("small", "", note)));
      return metrics;
    }

    function render() {
      if (!alive) return;
      closeDialog(false);
      root.replaceChildren(); root.classList.add("rw-root");
      root.setAttribute("aria-busy", state.loading ? "true" : "false");
      const shell = el("div", "rw-shell"); root.appendChild(shell);
      const dataset = current();
      const top = el("div", "rw-topline");
      const actions = el("div", "rw-top-actions");
      if (state.payload) actions.appendChild(field("Property / dataset", select(array(state.payload.datasets).map(item => [item.id, item.label]), state.dataset, changeDataset)));
      const dataActions = el("div", "rw-data-actions");
      fetchButton = button("Fetch fresh data", () => startCollection("fresh", state.dataset), "rw-button rw-fetch");
      refreshButton = button(state.loading ? "Reading saved data…" : "↻  Reload saved data", refresh);
      refreshButton.disabled = state.loading;
      append(dataActions, fetchButton, refreshButton); actions.appendChild(dataActions); top.appendChild(actions); shell.appendChild(top);
      jobRegion = el("div", "rw-job-region"); shell.appendChild(jobRegion); updateJobView();
      if (state.error) { const message = p(state.error, "rw-error"); message.setAttribute("role", "alert"); shell.appendChild(message); }
      if (settings.collectionOnly) {
        root.classList.add("rw-collection-only");
        actions.replaceChildren();
        append(actions, append(el("div"), el("strong", "rw-dataset-title", dataset ? dataset.label : "Selected hotel · collection not configured"),
          p(!dataset ? "This imported hotel's rate collection is not configured. Existing job status and Resume retain their original property." : state.dataset === "airbnb-compset" ? "Fetch covers the saved Dubai Airbnb comparison set. The direct-site portfolio and view filters are outside this collection." : "Fetch checks Aketa's saved OTA profiles for the next 30 arrival dates. View filters do not change the collection.")), dataActions);
        return;
      }
      if (!dataset) { shell.appendChild(empty(state.loading ? "Reading saved evidence from your local workspace…" : "No saved dataset is available. Use the collection views to gather source evidence, then refresh here.")); return; }
      append(shell, append(el("div", "rw-dataset-line"), append(el("div"), el("strong", "rw-dataset-title", dataset.label), el("span", "rw-context", `Saved request: ${contextSummary(dataset.context, dataset.currency)}`)),
        append(el("div", "rw-observed"), el("span", "", `Latest source observation · ${observedLabel(dataset.observed_at)}`), el("small", "", "Reload saved data reads files. Fetch fresh data starts a new bounded collection."))));
      shell.appendChild(coverageNote());
      shell.appendChild(metricCards(dataset));
      const nav = el("nav", "rw-tabs"); nav.setAttribute("aria-label", "Rate intelligence sections");
      for (const [id, label] of [["rates", "Rate calendar"], ["competitors", "Competitor set"], ["sources", "Sources & profiles"], ["portfolio", "Portfolio overview"]]) {
        const item = button(label, () => { state.tab = id; render(); }, `rw-tab${state.tab === id ? " is-active" : ""}`);
        item.setAttribute("aria-pressed", String(state.tab === id)); nav.appendChild(item);
      }
      shell.appendChild(nav);
      const region = el("section", "rw-content"); shell.appendChild(region);
      if (state.tab === "rates") renderRates(region, dataset);
      if (state.tab === "competitors") renderCompetitors(region, dataset);
      if (state.tab === "sources") renderSources(region, dataset);
      if (state.tab === "portfolio") renderPortfolio(region);
      const warnings = [...array(state.payload.warnings), ...array(dataset.warnings)].filter(present);
      if (warnings.length) {
        const details = el("details", "rw-warnings"); append(details, el("summary", "", `${warnings.length} evidence note${warnings.length === 1 ? "" : "s"}`));
        const list = el("ul"); warnings.forEach(value => list.appendChild(el("li", "", summarize(value)))); details.appendChild(list); shell.appendChild(details);
      }
      append(shell, p("Evidence stays in its original currency and context. Missing observations are never treated as zero prices or bookings.", "rw-footnote"));
    }

    function renderRates(region, dataset) {
      const head = el("div", "rw-rate-heading");
      append(head, append(el("div"), el("h3", "", dataset.kind === "hotel" ? "Prices by observation source" : "Prices across your selected set"), p("Click a date cell to inspect its offers, conditions and evidence.")));
      const modes = el("div", "rw-segment"); modes.setAttribute("role", "group"); modes.setAttribute("aria-label", "Rate display format");
      for (const [id, label] of [["calendar", "Calendar"], ["list", "List"]]) { const node = button(label, () => { state.mode = id; state.listPage = 0; render(); }, state.mode === id ? "is-active" : ""); node.setAttribute("aria-pressed", String(state.mode === id)); modes.appendChild(node); }
      append(head, modes); region.appendChild(head);
      const toolbar = el("div", "rw-toolbar");
      const sources = [...new Set(array(dataset.entities).map(entity => entity.source))];
      append(toolbar, field("Observation source", select([["all", "All sources"], ...sources.map(value => [value, sourceName(value)])], state.source, value => { state.source = value; state.listPage = 0; render(); })),
        field("Date evidence", select([["all", "All evidence"], ...STATES.map(value => [value, STATE_LABELS[value]])], state.evidence, value => { state.evidence = value; state.listPage = 0; render(); })));
      const resultRegion = el("div", "rw-results");
      const input = search(state.query, dataset.kind === "hotel" ? "Find a source…" : "Find a listing…", value => { state.query = value; state.listPage = 0; renderRateResults(resultRegion, dataset); });
      append(toolbar, field(dataset.kind === "hotel" ? "Find source" : "Find listing", input), button("Export filtered window ↓", () => download(dataset), "rw-button rw-export"));
      append(region, toolbar, p(dataset.comparison_note || "A comparable market rank requires matching stay, room, meal, tax, cancellation and guest conditions.", "rw-comparison-note"), resultRegion);
      renderRateResults(resultRegion, dataset);
    }

    function renderRateResults(region, dataset) {
      region.replaceChildren();
      const view = visibleModel(dataset, options()); state.page = view.page;
      const pager = el("div", "rw-window-pager");
      const previous = button("←", () => { state.page -= 1; state.listPage = 0; renderRateResults(region, dataset); }, "rw-icon-button");
      previous.disabled = view.page === 0; previous.setAttribute("aria-label", "Previous seven days");
      const next = button("→", () => { state.page += 1; state.listPage = 0; renderRateResults(region, dataset); }, "rw-icon-button");
      next.disabled = view.page === view.lastPage; next.setAttribute("aria-label", "Next seven days");
      append(pager, append(el("div", "rw-pager-controls"), previous, el("strong", "", view.dates.length ? `${dateLabel(view.dates[0], true)} – ${dateLabel(view.dates[view.dates.length - 1])}` : "No dates saved"), next), el("span", "rw-muted", `Window ${view.page + 1} of ${view.lastPage + 1} · ${view.cells.length} matching date cells`));
      region.appendChild(pager);
      if (!view.cells.length) { region.appendChild(empty("No saved date cells match these view filters. Adjust the source, evidence or search filter.")); return; }
      if (state.mode === "calendar") renderGrid(region, dataset, view); else renderList(region, dataset, view);
      const legend = el("div", "rw-legend");
      STATES.forEach(value => legend.appendChild(badge(STATE_LABELS[value], value)));
      append(region, legend, p("Each cell retains its reported price basis or selected quote. Where offers share a source, stay and basis, the lowest observed display may be summarized. Click through before comparing conditions. Coverage counts above refer to the full saved window.", "rw-footnote"));
    }

    function renderGrid(region, dataset, view) {
      const { scroll, node, body } = table([dataset.kind === "hotel" ? "Observation source" : "Property", ...view.dates.map(value => dateLabel(value, true))], "Seven-day saved rate grid");
      node.classList.add("rw-grid");
      for (const row of view.rows) {
        const tr = el("tr", row.entity.role === "subject" ? "rw-subject-row" : "");
        const heading = el("th", "rw-entity-cell"); heading.scope = "row";
        append(heading, el("strong", "", row.entity.label), el("small", "", row.entity.role === "subject" ? "Your subject property" : dataset.kind === "hotel" ? sourceName(row.entity.source) : "Selected competitor"));
        tr.appendChild(heading);
        for (const cell of row.cells) {
          const td = el("td", "rw-grid-td");
          if (state.evidence !== "all" && stateOf(cell) !== state.evidence) {
            td.appendChild(el("span", "rw-filtered-cell", "Filtered")); tr.appendChild(td); continue;
          }
          const cellButton = button("", () => showCell(dataset, row.entity, cell, cellButton), `rw-rate-cell rw-cell-${stateOf(cell)}`);
          const offers = array(cell.offers).length;
          append(cellButton, el("strong", "", priceLabel(cell)), el("span", "", ["quoted", "indicative"].includes(stateOf(cell)) ? `${STATE_LABELS[stateOf(cell)]}${offers > 1 ? ` · ${offers} offers` : ""}` : human(cell.reason === "not_observed" ? "not_observed" : cell.reason).slice(0, 65)));
          cellButton.setAttribute("aria-label", `${row.entity.label}, ${dateLabel(cell.date)}: ${priceLabel(cell)}, ${STATE_LABELS[stateOf(cell)]}. Inspect evidence.`);
          cellButton.title = `${human(cell.amount_basis)} · ${observedLabel(cell.observed_at)}`;
          td.appendChild(cellButton); tr.appendChild(td);
        }
        body.appendChild(tr);
      }
      region.appendChild(scroll);
    }

    function renderList(region, dataset, view) {
      const pageSize = 50;
      const last = Math.max(0, Math.ceil(view.cells.length / pageSize) - 1); state.listPage = Math.max(0, Math.min(last, state.listPage));
      const { scroll, body } = table(["Property / source", "Requested stay", "Evidence", "Reported amount", "Basis", "Observed", "Details"], "Filtered saved rate observations");
      for (const { entity, cell } of view.cells.slice(state.listPage * pageSize, state.listPage * pageSize + pageSize)) {
        const tr = el("tr");
        append(tr, append(el("td"), el("strong", "rw-table-title", entity.label), el("small", "rw-muted", sourceName(entity.source))),
          append(el("td"), el("span", "", dateLabel(cell.date)), el("small", "rw-muted", `To ${dateLabel(cell.checkout)}`)),
          append(el("td"), badge(STATE_LABELS[stateOf(cell)], stateOf(cell))), el("td", "rw-money", priceLabel(cell)), el("td", "", human(cell.amount_basis)), el("td", "", observedLabel(cell.observed_at)));
        const inspect = button("Inspect →", () => showCell(dataset, entity, cell, inspect), "rw-text-button");
        tr.appendChild(append(el("td"), inspect)); body.appendChild(tr);
      }
      region.appendChild(scroll);
      const previous = button("←", () => { state.listPage -= 1; renderRateResults(region, dataset); }, "rw-icon-button"); previous.disabled = state.listPage === 0; previous.setAttribute("aria-label", "Previous list page");
      const next = button("→", () => { state.listPage += 1; renderRateResults(region, dataset); }, "rw-icon-button"); next.disabled = state.listPage === last; next.setAttribute("aria-label", "Next list page");
      region.appendChild(append(el("div", "rw-list-footer"), p(`Showing ${state.listPage * pageSize + 1}–${Math.min(view.cells.length, (state.listPage + 1) * pageSize)} of ${view.cells.length}. CSV includes all matches in this date window.`), append(el("div", "rw-pager-controls"), previous, el("span", "", `${state.listPage + 1} / ${last + 1}`), next)));
    }

    function candidateSelected(candidate) {
      return candidate.selected === true || candidate.selection === "selected" || candidate.selection_status === "selected";
    }

    function renderCompetitors(region, dataset) {
      const candidates = array(dataset.candidates);
      region.appendChild(sectionHead("Competitor selection evidence", "Review the saved match decisions, product attributes and operator evidence."));
      if (dataset.discovery_context) region.appendChild(p(`Discovery context: ${summarize(dataset.discovery_context)}. These selection inputs are separate from each saved rate's stay context.`, "rw-comparison-note"));
      if (!candidates.length) {
        region.appendChild(empty(dataset.kind === "hotel" ? "No hotel competitor set has been collected for Aketa. Its OTA profiles are distribution sources for the same hotel. Switch to Airbnb to inspect the saved apartment competitor set." : "No candidate selection evidence is saved for this dataset.")); return;
      }
      const content = el("div");
      const renderRows = () => {
        content.replaceChildren();
        const query = state.candidateQuery.trim().toLowerCase();
        const filtered = candidates.filter(item => (!query || `${item.title || item.label} ${item.id || item.listing_id} ${item.host_name || ""} ${item.host_id || ""} ${summarize(item.operator_name || item.operator_evidence)}`.toLowerCase().includes(query)) && (state.candidateFilter === "all" || (state.candidateFilter === "selected" ? candidateSelected(item) : !candidateSelected(item))));
        content.appendChild(p(`${filtered.length} shown · ${candidates.filter(candidateSelected).length} selected of ${candidates.length} saved candidates`, "rw-result-count"));
        const { scroll, body } = table(["Property", "Decision", "Product", "Location / distance", "Reviews", "Operator", "Match evidence"], "Saved competitor selection decisions");
        for (const item of filtered) {
          const tr = el("tr");
          const id = item.id || item.listing_id;
          const property = append(el("td"), link(item.source_url || item.url, item.title || item.label || id), el("small", "rw-muted", id));
          const decision = candidateSelected(item) ? "Selected" : human(item.selection || item.selection_status || item.eligibility || "not_selected");
          append(tr, property, append(el("td"), badge(decision, candidateSelected(item) ? "quoted" : "unknown")),
            el("td", "", `${str(item.bedrooms, "?")} bedrooms · ${str(item.bathrooms, "?")} baths${present(item.property_type) ? ` · ${item.property_type}` : ""}`),
            el("td", "", [item.location_name || item.location || item.city, present(item.circle_distance_km) ? `${item.circle_distance_km} km` : present(item.distance_km) ? `${item.distance_km} km` : null].filter(present).map(summarize).join(" · ") || "Not observed"),
            el("td", "", `${str(item.rating || item.review_score)}${present(item.review_count) ? ` · ${item.review_count} reviews` : ""}`),
            append(el("td"), el("span", "", summarize(item.operator_name || item.operator_evidence || item.operator || item.host_name)), el("small", "rw-muted", [item.operator_size, item.operator_size_basis].filter(present).map(human).join(" · "))));
          const inspect = button("Review match →", () => {
            const detail = el("div", "rw-drawer-body");
            append(detail, badge(decision, candidateSelected(item) ? "quoted" : "unknown"), facts([["Selection", item.selection || item.selection_status || item.selected], ["Eligibility", item.eligibility], ["Reasons", item.rejection_reasons || item.reasons || item.selection_reasons || item.audit_notes], ["Missing fields", item.missing_fields], ["Amenities", item.amenities], ["Operator evidence", item.operator_evidence || { name: item.operator_name || item.host_name, size: item.operator_size, basis: item.operator_size_basis, observed_host_listings: item.host_listing_count }], ["Rating", item.rating || item.review_score], ["Review count", item.review_count], ["Observed", observedLabel(item.observed_at)]]), el("h3", "rw-detail-subtitle", "Saved candidate fields"), el("pre", "rw-raw-evidence", JSON.stringify(item, null, 2)));
            openDialog(item.title || item.label || id, detail, inspect);
          }, "rw-text-button");
          tr.appendChild(append(el("td"), el("small", "rw-muted", summarize(array(item.rejection_reasons).length ? item.rejection_reasons : item.reasons || item.selection_reasons || item.eligibility)), inspect)); body.appendChild(tr);
        }
        content.appendChild(filtered.length ? scroll : empty("No candidates match this view filter."));
      };
      append(region, append(el("div", "rw-toolbar"), field("Candidate decision", select([["all", "All saved candidates"], ["selected", "Selected"], ["other", "Not selected"]], state.candidateFilter, value => { state.candidateFilter = value; renderRows(); })), field("Find candidate", search(state.candidateQuery, "Property, host or listing ID…", value => { state.candidateQuery = value; renderRows(); }))), content);
      renderRows();
    }

    function renderSources(region, dataset) {
      region.appendChild(sectionHead("Source health", "A source status belongs to its latest checked stay. It is not a whole-calendar availability claim."));
      const { scroll, body } = table(["Source", "Latest result", "Checked stay", "Source observation", "Reason"], "Source collection health");
      for (const item of array(dataset.source_states)) {
        const tr = el("tr");
        append(tr, append(el("td"), link(item.url || item.source_url, sourceName(item.source))), append(el("td"), badge(human(item.status), STATES.includes(item.status) ? item.status : "unknown")), el("td", "", typeof item.last_stay === "object" ? summarize(item.last_stay) : dateLabel(item.last_stay)), append(el("td"), el("span", "", observedLabel(item.observed_at)), el("small", "rw-muted", ageLabel(item.observed_at))), el("td", "", human(item.reason)));
        body.appendChild(tr);
      }
      region.appendChild(array(dataset.source_states).length ? scroll : empty("No source-health observation is saved for this dataset."));
      region.appendChild(sectionHead("Property profiles", "Separate profile IDs and branding are retained. Page presence alone does not confirm a sellable dated offer."));
      const profileTable = table(["Source / profile", "Property name", "Sale evidence", "Branding / inventory", "Observed"], "Property profile identity audit");
      for (const item of array(dataset.profiles)) {
        const tr = el("tr");
        const context = item.requested_context || {};
        append(tr, append(el("td"), link(item.url || item.source_url, sourceName(item.source)), el("small", "rw-muted", `ID ${str(item.provider_id, "not verified")}`)), el("td", "rw-table-title", item.name),
          append(el("td"), el("span", "", human(item.sale_status)), item.requested_context ? el("small", "rw-muted", `Requested ${dateLabel(context.checkin, true)} → ${dateLabel(context.checkout, true)} · ${contextSummary(context)}`) : null),
          append(el("td"), el("span", "", human(item.branding)), el("small", "rw-muted", item.inventory_mirror ? `Inventory mirror · ${summarize(item.inventory_mirror)}` : "Inventory relationship not established")),
          append(el("td"), el("span", "", `Source: ${observedLabel(item.observed_at)}`), item.audit_completed_at ? el("small", "rw-muted", `Profile audit: ${observedLabel(item.audit_completed_at)}`) : null));
        profileTable.body.appendChild(tr);
      }
      region.appendChild(array(dataset.profiles).length ? profileTable.scroll : empty("No duplicate-profile audit is saved for this dataset."));
    }

    function renderPortfolio(region) {
      const portfolio = state.payload.portfolio || {}, properties = array(portfolio.properties);
      region.appendChild(sectionHead("BnBMe portfolio", "Published property inventory, separate from the selected rate dataset and hotel source profiles.", el("span", "rw-muted", observedLabel(portfolio.observed_at))));
      if (!properties.length) { region.appendChild(empty("No property catalog observations saved.")); return; }
      const cities = [...new Set(properties.map(item => item.city).filter(present))].sort();
      const counts = el("div", "rw-portfolio-counts");
      append(counts, append(el("div"), el("strong", "", properties.length), el("span", "", "Saved properties")), append(el("div"), el("strong", "", cities.length), el("span", "", "Recorded cities")), append(el("div"), el("strong", "", [...new Set(properties.map(item => item.currency).filter(present))].join(" · ") || "Unknown"), el("span", "", "Source currencies · no conversion")));
      region.appendChild(counts);
      const content = el("div");
      const renderRows = () => {
        content.replaceChildren();
        const query = state.portfolioQuery.trim().toLowerCase();
        const filtered = properties.filter(item => (state.portfolioCity === "all" || item.city === state.portfolioCity) && (!query || `${item.title} ${item.id} ${item.operator_name} ${item.city} ${item.country}`.toLowerCase().includes(query)));
        content.appendChild(p(`${filtered.length} of ${properties.length} catalog properties · Publication does not establish dated availability.`, "rw-result-count"));
        const { scroll, body } = table(["Property", "Location", "Product", "Operator", "Publication / platform link", "Source observation"], "Published BnBMe inventory");
        for (const item of filtered) {
          const tr = el("tr");
          append(tr, append(el("td"), link(item.source_url, item.title || item.id), el("small", "rw-muted", item.id)), el("td", "", [item.city, item.country].filter(present).join(", ") || "Not observed"), el("td", "", `${str(item.bedrooms, "?")} bedrooms · ${str(item.bathrooms, "?")} baths · ${str(item.person_capacity, "?")} guests`), el("td", "", str(item.operator_name)), append(el("td"), el("span", "", human(item.publication_status)), el("small", "rw-muted", human(item.link_status))), el("td", "", observedLabel(item.observed_at)));
          body.appendChild(tr);
        }
        content.appendChild(filtered.length ? scroll : empty("No properties match this view filter."));
      };
      append(region, append(el("div", "rw-toolbar"), field("City", select([["all", "All cities"], ...cities.map(value => [value, value])], state.portfolioCity, value => { state.portfolioCity = value; renderRows(); })), field("Find property", search(state.portfolioQuery, "Property, city or operator…", value => { state.portfolioQuery = value; renderRows(); }))), content);
      renderRows();
    }

    async function reloadSaved() {
      if (!alive) return;
      // A job may finish during a saved read. Its newer evidence needs one
      // subsequent read, even when the first response was captured beforehand.
      if (state.loading) { queuedSavedReload = true; return; }
      state.loading = true; state.error = null; const requestId = ++state.requestId; render();
      try {
        if (settings.collectionOnly) {
          if (typeof settings.onReload === "function") await settings.onReload();
          return;
        }
        const response = await global.fetch("/api/workspace", { method: "GET", cache: "no-store", credentials: "same-origin", headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error(response.status === 404 ? "Restart CompSet Studio to load the new rate-workspace API." : `Saved evidence request returned HTTP ${response.status}.`);
        const payload = await response.json();
        if (!payload || payload.schema_version !== 1 || !Array.isArray(payload.datasets) || payload.datasets.some(item => !item || typeof item.id !== "string" || !Array.isArray(item.entities) || !Array.isArray(item.cells) || !Array.isArray(item.dates))) throw new Error("Saved evidence has an unsupported format.");
        if (!alive || requestId !== state.requestId) return;
        state.payload = payload;
        if (!payload.datasets.some(item => item.id === state.dataset)) state.dataset = payload.datasets[0] ? payload.datasets[0].id : "aketa";
      } catch (error) {
        if (alive && requestId === state.requestId) state.error = `Could not refresh saved evidence. ${error && error.message ? error.message : "Local service unavailable."}${state.payload ? " The previous saved view remains visible." : ""}`;
      } finally {
        if (alive && requestId === state.requestId) {
          state.loading = false; render();
          if (queuedSavedReload) { queuedSavedReload = false; await reloadSaved(); }
        }
      }
    }

    async function refresh() {
      // Both calls are reads. A page load or refresh never starts/resumes a job.
      await Promise.all([reloadSaved(), loadJob()]);
    }

    return { root, refresh, refreshStatus() { render(); return loadJob(); }, setDataset(datasetId) {
      if (datasetId !== null && !["aketa", "airbnb-compset"].includes(datasetId)) throw new TypeError("Unsupported collection dataset");
      if (!alive) return;
      state.dataset = datasetId; render();
    }, destroy() { alive = false; queuedSavedReload = false; state.requestId += 1; jobRequestId += 1; clearPoll(); closeDialog(false); doc.removeEventListener("keydown", keyboard); } };
  }

  const api = { mount, mountCollection, refresh: () => controller ? controller.refresh() : Promise.resolve(), model: Object.freeze({ STATES, STATE_LABELS, safeUrl, visibleModel, exportCsv, csvField, priceLabel, contextSummary, observedLabel, ageLabel }) };
  global.CompSetRates = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window === "undefined" ? globalThis : window);
