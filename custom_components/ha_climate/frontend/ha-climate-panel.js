/*
 * HA Climate – sidebar panel.
 *
 * A dependency-free web component (no build step, no CDN) that talks to the
 * integration through its WebSocket API. Styling uses the Home Assistant theme
 * variables, so light and dark themes work automatically.
 */

const TABS = [
  { id: "rooms", label: "Kamers", icon: "M10,20V14H14V20H19V12H22L12,3L2,12H5V20H10Z" },
  { id: "analytics", label: "Analyses", icon: "M22,21H2V3H4V19H6V10H10V19H12V6H16V19H18V14H22V21Z" },
  { id: "tips", label: "Tips", icon: "M12,2A7,7 0 0,0 5,9C5,11.38 6.19,13.47 8,14.74V17A1,1 0 0,0 9,18H15A1,1 0 0,0 16,17V14.74C17.81,13.47 19,11.38 19,9A7,7 0 0,0 12,2M9,21A1,1 0 0,0 10,22H14A1,1 0 0,0 15,21V20H9V21Z" },
  { id: "schedules", label: "Schema's", icon: "M12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22C6.47,22 2,17.5 2,12A10,10 0 0,1 12,2M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z" },
  { id: "settings", label: "Instellingen", icon: "M12,15.5A3.5,3.5 0 0,1 8.5,12A3.5,3.5 0 0,1 12,8.5A3.5,3.5 0 0,1 15.5,12A3.5,3.5 0 0,1 12,15.5M19.43,12.97C19.47,12.65 19.5,12.33 19.5,12C19.5,11.67 19.47,11.34 19.43,11L21.54,9.37C21.73,9.22 21.78,8.95 21.66,8.73L19.66,5.27C19.54,5.05 19.27,4.96 19.05,5.05L16.56,6.05C16.04,5.66 15.5,5.32 14.87,5.07L14.5,2.42C14.46,2.18 14.25,2 14,2H10C9.75,2 9.54,2.18 9.5,2.42L9.13,5.07C8.5,5.32 7.96,5.66 7.44,6.05L4.95,5.05C4.73,4.96 4.46,5.05 4.34,5.27L2.34,8.73C2.21,8.95 2.27,9.22 2.46,9.37L4.57,11C4.53,11.34 4.5,11.67 4.5,12C4.5,12.33 4.53,12.65 4.57,12.97L2.46,14.63C2.27,14.78 2.21,15.05 2.34,15.27L4.34,18.73C4.46,18.95 4.73,19.03 4.95,18.95L7.44,17.94C7.96,18.34 8.5,18.68 9.13,18.93L9.5,21.58C9.54,21.82 9.75,22 10,22H14C14.25,22 14.46,21.82 14.5,21.58L14.87,18.93C15.5,18.67 16.04,18.34 16.56,17.94L19.05,18.95C19.27,19.03 19.54,18.95 19.66,18.73L21.66,15.27C21.78,15.05 21.73,14.78 21.54,14.63L19.43,12.97Z" },
];

const STATUS = {
  heating: { label: "Verwarmen", color: "#ff7043" },
  preheating: { label: "Voorverwarmen", color: "#ffa726" },
  setback: { label: "Nachtverlaging", color: "#5c6bc0" },
  fireplace: { label: "Openhaard actief", color: "#e53935" },
  idle: { label: "Op temperatuur", color: "#43a047" },
  off: { label: "Uit", color: "#9e9e9e" },
  unavailable: { label: "Niet beschikbaar", color: "#9e9e9e" },
};

const COLORS = {
  gas: "#29b6f6",
  expected: "#ffa726",
  degreeDays: "#ab47bc",
  saved: "#66bb6a",
  savedEur: "#26a69a",
  cost: "#8d6e63",
  cooling: "#42a5f5",
  heating: "#ef5350",
  flow: "#ef5350",
  setpoint: "#ffa726",
  modulation: "#ab47bc",
  valve: "#26a69a",
  dhw: "#29b6f6",
  heat: "#ff7043",
};

const BOILER_FIELDS = [
  { key: "boiler_flame", label: "Brander / vlamstatus", domain: "binary_sensor", hint: "bijv. cv_vlam_status" },
  { key: "boiler_heat_request", label: "Warmtevraag", domain: "binary_sensor", hint: "bijv. ot_heat_request" },
  { key: "boiler_dhw", label: "Tapwater / warm water status", domain: "binary_sensor", hint: "bijv. cv_warm_water_status" },
  { key: "boiler_modulation", label: "Modulatie (%)", domain: "sensor", hint: "bijv. cv_degree_of_modulation" },
  { key: "boiler_flow_temp", label: "Werkelijke aanvoertemperatuur (°C)", domain: "sensor", hint: "bijv. cv_h1_water_temperatuur" },
  { key: "boiler_flow_setpoint", label: "Gevraagde aanvoertemperatuur (°C)", domain: "sensor", hint: "bijv. cv_h1_flow_setpoint_value" },
  { key: "boiler_pressure", label: "Waterdruk (bar)", domain: "sensor", hint: "bijv. cv_waterdruk" },
  { key: "boiler_error", label: "Foutcode", domain: "sensor", hint: "bijv. cv_error_code" },
  { key: "boiler_starts_today", label: "Starts vandaag (optioneel)", domain: "sensor", hint: "anders zelf geteld" },
  { key: "boiler_hours_today", label: "Branduren vandaag (optioneel)", domain: "sensor", hint: "anders zelf berekend" },
  { key: "boiler_avg_runtime", label: "Gem. looptijd (optioneel)", domain: "sensor", hint: "anders zelf berekend" },
];

const minutesText = (value) => {
  if (value === null || value === undefined) return "–";
  if (value < 60) return `${fmt(value, 0)} min`;
  return `${Math.floor(value / 60)}u ${String(Math.round(value % 60)).padStart(2, "0")}m`;
};

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const fmt = (value, digits = 1, unit = "") => {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  const text = new Intl.NumberFormat("nl-NL", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
  return unit ? `${text} ${unit}` : text;
};

// Saved gas (expected − actual): positive = saved (green), negative = used more than expected (red).
const savedClass = (value, deadband = 0) =>
  value === null || value === undefined || Number.isNaN(value) ? "" : value > deadband ? "good" : value < -deadband ? "bad" : "";
const savedNote = (value) =>
  value === null || value === undefined || Number.isNaN(value) ? "" : value > 0 ? "bespaard" : value < 0 ? "meer verbruikt dan verwacht" : "";

const euro = (value) =>
  value === null || value === undefined ? "–" : new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR" }).format(value);

// Times are shown in the Home Assistant time zone (not the browser's).
let SERVER_TZ;
const timeOf = (iso) => {
  if (!iso) return "–";
  const d = new Date(iso);
  const opts = { hour: "2-digit", minute: "2-digit" };
  try {
    return d.toLocaleTimeString("nl-NL", SERVER_TZ ? { ...opts, timeZone: SERVER_TZ } : opts);
  } catch (err) {
    return d.toLocaleTimeString("nl-NL", opts);
  }
};

const dayLabel = (iso) => {
  const d = new Date(`${iso}T12:00:00`);
  return d.toLocaleDateString("nl-NL", { day: "numeric", month: "short" });
};

const dateLabel = (iso) => {
  if (!iso) return "–";
  const d = iso.length <= 10 ? new Date(`${iso}T12:00:00`) : new Date(iso);
  const opts = { day: "numeric", month: "short", year: "numeric" };
  try {
    return d.toLocaleDateString("nl-NL", iso.length > 10 && SERVER_TZ ? { ...opts, timeZone: SERVER_TZ } : opts);
  } catch (err) {
    return d.toLocaleDateString("nl-NL", opts);
  }
};

const daysBetween = (fromIso, toIso) =>
  Math.round((new Date(`${toIso}T12:00:00`) - new Date(`${fromIso}T12:00:00`)) / 86400000);

/*
 * Combine the change log of a day into readable lines: a night setting that
 * was changed for the whole house and every room at the same moment becomes
 * one line, and internal baseline bookkeeping is left out.
 */
const summarizeEvents = (list) => {
  const out = [];
  const groups = new Map();
  for (const e of list || []) {
    if (e.type === "baseline") continue;
    const m = e.type === "settings" && /^Nachtverlaging(?: (.+?))? (ingesteld|aangepast): (.+)$/.exec(e.text);
    if (!m) {
      out.push({ time: e.time, text: e.text });
      continue;
    }
    const key = `${timeOf(e.time)}|${m[3]}`;
    let g = groups.get(key);
    if (!g) {
      g = { time: e.time, verb: m[2], desc: m[3], rooms: [], global: false };
      groups.set(key, g);
      out.push(g);
    }
    if (m[1]) g.rooms.push(m[1]);
    else g.global = true;
  }
  return out.map((g) => {
    if (g.desc === undefined) return g;
    let who = "";
    if (g.global) who = g.rooms.length ? ` (algemeen + ${g.rooms.length} kamer${g.rooms.length === 1 ? "" : "s"})` : " (algemeen)";
    else who = g.rooms.length > 2 ? ` (${g.rooms.length} kamers)` : ` (${g.rooms.join(", ")})`;
    return { time: g.time, text: `Nachtverlaging ${g.verb}: ${g.desc}${who}` };
  });
};

const hhmm = (value, fallback = "") => (value ? String(value).slice(0, 5) : fallback);

const numOrNull = (value) => {
  if (value === "" || value === null || value === undefined) return null;
  const n = Number(String(value).replace(",", "."));
  return Number.isFinite(n) ? n : null;
};

class HaClimatePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = this._loadTab();
    this._state = null;
    this._history = null;
    this._days = 60;
    this._dialog = null;
    this._error = null;
    this._busy = false;
    this._dirty = false;
    this._chartUnit = "m3";
    this._pendingTemp = {};
    this._pendingAirco = {};
    this._tempTimers = {};
    this._boilerTrace = null;
    this._hourly = null;
    this._hourlyDay = null;
    this._advice = null;
    this._editing = false;
  }

  /* ---------- Home Assistant properties ---------- */
  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    SERVER_TZ = hass?.config?.time_zone;
    if (first) {
      this._render();
      this._refresh();
    }
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) menu.hass = hass;
  }

  set narrow(narrow) {
    this._narrow = narrow;
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) menu.narrow = narrow;
  }

  set panel(panel) {
    this._panel = panel;
  }

  connectedCallback() {
    this._timer = setInterval(() => {
      if (!this._dialog && !this._dirty && !this._busy && !this._editing && document.visibilityState === "visible") this._refresh(true);
    }, 30000);
    this._resize = new ResizeObserver(() => {
      if (this._tab === "analytics") this._renderCharts();
    });
    this._resize.observe(this);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    this._resize?.disconnect();
  }

  _loadTab() {
    try {
      return localStorage.getItem("ha-climate-tab") || "rooms";
    } catch (err) {
      return "rooms";
    }
  }

  _saveTab() {
    try {
      localStorage.setItem("ha-climate-tab", this._tab);
    } catch (err) {
      /* ignore */
    }
  }

  /* ---------- Data ---------- */
  async _ws(msg) {
    return this._hass.callWS(msg);
  }

  async _refresh(silent = false) {
    if (!this._hass) return;
    try {
      this._state = await this._ws({ type: "ha_climate/state" });
      this._error = null;
      if (this._tab === "analytics") await this._loadHistory();
      if (this._tab === "tips") await this._loadAdvice();
    } catch (err) {
      this._error = err?.message || "HA Climate is niet geladen.";
    }
    if (!silent || !this._dirty) this._render();
  }

  async _loadHistory() {
    try {
      const [result, trace] = await Promise.all([
        this._ws({ type: "ha_climate/history", days: this._days }),
        this._state?.boiler ? this._ws({ type: "ha_climate/boiler/trace" }).catch(() => ({ points: [] })) : null,
        this._loadHourly(),
      ]);
      this._history = result.days;
      this._boilerTrace = trace ? trace.points : null;
    } catch (err) {
      this._history = [];
      this._toast(err?.message || "Kon historie niet laden", true);
    }
  }

  async _loadHourly() {
    try {
      const msg = { type: "ha_climate/hourly" };
      if (this._hourlyDay) msg.day = this._hourlyDay;
      this._hourly = await this._ws(msg);
    } catch (err) {
      this._hourly = { hours: [], summary: null, baseline: null };
    }
  }

  async _loadAdvice(refresh = false) {
    try {
      this._advice = await this._ws({ type: "ha_climate/advice", refresh });
      this._adviceError = null;
    } catch (err) {
      this._adviceError = err?.message || "Tips konden niet worden berekend";
    }
  }

  async _call(msg, success) {
    this._busy = true;
    this._renderBusy();
    try {
      const result = await this._ws(msg);
      if (success) this._toast(success);
      this._dirty = false;
      await this._refresh();
      return result;
    } catch (err) {
      this._toast(err?.message || "Er ging iets mis", true);
      return null;
    } finally {
      this._busy = false;
      this._renderBusy();
    }
  }

  get _admin() {
    return this._state?.is_admin ?? this._hass?.user?.is_admin;
  }

  /* ---------- Entity helpers ---------- */
  _entities(filter) {
    return Object.values(this._hass.states)
      .filter(filter)
      .map((s) => ({ id: s.entity_id, name: s.attributes.friendly_name || s.entity_id }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  _options(list, selected, allowEmpty = false) {
    const opts = allowEmpty ? ['<option value="">— geen —</option>'] : [];
    let found = !selected;
    for (const item of list) {
      if (item.id === selected) found = true;
      opts.push(`<option value="${esc(item.id)}" ${item.id === selected ? "selected" : ""}>${esc(item.name)} (${esc(item.id)})</option>`);
    }
    if (!found) opts.push(`<option value="${esc(selected)}" selected>${esc(selected)}</option>`);
    return opts.join("");
  }

  /* ---------- Rendering ---------- */
  _render() {
    const root = this.shadowRoot;
    if (!root.getElementById("app")) {
      // Toast and busy bar live outside the re-rendered part, so a message
      // shown right before a refresh stays visible.
      root.innerHTML = `
        <style>${STYLE}</style>
        <div id="app"></div>
        <div class="toast" id="toast" role="status" aria-live="polite"></div>
        <div class="busy"><div class="spinner"></div></div>`;
    }
    root.querySelector(".busy").classList.toggle("show", this._busy);
    root.getElementById("app").innerHTML = `
      <div class="toolbar">
        <ha-menu-button></ha-menu-button>
        <div class="title">HA Climate</div>
        <div class="spacer"></div>
        <button class="icon-btn" data-action="refresh" title="Vernieuwen">
          <svg viewBox="0 0 24 24"><path d="M17.65,6.35C16.2,4.9 14.21,4 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20C15.73,20 18.84,17.45 19.73,14H17.65C16.83,16.33 14.61,18 12,18A6,6 0 0,1 6,12A6,6 0 0,1 12,6C13.66,6 15.14,6.69 16.22,7.78L13,11H20V4L17.65,6.35Z"/></svg>
        </button>
      </div>
      <nav class="tabs">
        ${TABS.map(
          (t) => `<button class="tab ${t.id === this._tab ? "active" : ""}" data-tab="${t.id}">
            <svg viewBox="0 0 24 24"><path d="${t.icon}"/></svg><span>${t.label}</span></button>`
        ).join("")}
      </nav>
      <main class="content">${this._renderContent()}</main>
      ${this._dialog ? this._renderDialog() : ""}
    `;
    const menu = root.querySelector("ha-menu-button");
    if (menu) {
      menu.hass = this._hass;
      menu.narrow = this._narrow;
    }
    this._bind();
    if (this._tab === "analytics") this._renderCharts();
  }

  _renderBusy() {
    this.shadowRoot.querySelector(".busy")?.classList.toggle("show", this._busy);
  }

  _renderContent() {
    if (this._error) {
      return `<div class="card empty"><h2>HA Climate niet beschikbaar</h2><p>${esc(this._error)}</p>
        <p>Controleer of de integratie is toegevoegd en geladen onder Instellingen → Apparaten &amp; diensten.</p></div>`;
    }
    if (!this._state) return `<div class="card empty"><div class="spinner"></div><p>Laden…</p></div>`;
    switch (this._tab) {
      case "analytics":
        return this._renderAnalytics();
      case "schedules":
        return this._renderSchedules();
      case "settings":
        return this._renderSettings();
      case "tips":
        return this._renderTips();
      default:
        return this._renderRooms();
    }
  }

  /* ----- Rooms ----- */
  _renderRooms() {
    const s = this._state;
    const fp = s.fireplace;
    const admin = this._admin;
    const rooms = s.rooms
      .map((room) => {
        const status = STATUS[room.status] || STATUS.idle;
        const loops = room.loops
          .map(
            (l) => `<li><span>${esc(l.name || l.entity_id)}</span>
            <span class="muted">${fmt(l.current_temperature, 1, "°C")} → ${fmt(l.target_temperature, 1, "°C")}
            ${l.hvac_action === "heating" ? '<span class="dot heat" title="verwarmt"></span>' : ""}</span></li>`
          )
          .join("");
        const preheat = room.schedule.optimum_start && room.preheat.next_heating_start
          ? `<div class="row small"><span>Optimum start</span><span>${timeOf(room.preheat.next_heating_start)} (${room.preheat.method === "model" ? "model" : "veilige fallback"})</span></div>`
          : "";
        return `
        <div class="card room">
          <div class="room-head">
            <div>
              <div class="room-name">${esc(room.name)}${room.has_fireplace ? ' <span title="openhaard">🔥</span>' : ""}</div>
              <span class="chip" style="--chip:${status.color}">${status.label}</span>
            </div>
            <label class="switch" title="Nachtverlaging voor deze kamer">
              <input type="checkbox" data-action="room-enable" data-room="${room.id}" ${room.enabled ? "checked" : ""} ${admin ? "" : "disabled"}>
              <span class="slider"></span>
            </label>
          </div>
          <div class="temps">
            <div><div class="big">${fmt(room.current_temperature, 1)}<small>°C</small></div><div class="muted">huidig</div></div>
            <div class="setpoint" data-room-setpoint="${room.id}">
              <div class="thermo">
                ${admin ? `<button class="step-btn" data-action="room-temp" data-room="${room.id}" data-delta="-0.5" aria-label="Doeltemperatuur lager">−</button>` : ""}
                <button class="sp-btn" data-action="edit-temp" data-kind="room" data-room="${room.id}" ${admin ? 'title="Klik om een temperatuur in te typen"' : "disabled"}>
                  <span class="sp-value">${fmt(this._pendingTemp[room.id] ?? room.target_temperature, 1)}</span><small>°C</small></button>
                ${admin ? `<button class="step-btn" data-action="room-temp" data-room="${room.id}" data-delta="0.5" aria-label="Doeltemperatuur hoger">+</button>` : ""}
              </div>
              <div class="muted"><span class="sp-label">doel nu</span></div>
            </div>
            <div><div class="mid">${fmt(room.comfort_temperature, 1)}<small>°C</small></div><div class="muted">dag</div></div>
          </div>
          ${room.schedule.periods && room.schedule.periods.length
            ? `<div class="row small"><span>Comfort</span><span>${room.schedule.periods.map((p) => `${p.start}–${p.end}`).join(", ")};
            anders ${room.schedule.night_temp !== null ? fmt(room.schedule.night_temp, 1, "°C") : fmt(room.schedule.night_offset, 1, "°C")}</span></div>`
            : `<div class="row small"><span>Nacht</span><span>${room.schedule.night_start} – ${room.schedule.optimum_start ? room.schedule.comfort_time : room.schedule.night_end},
            ${room.schedule.night_temp !== null ? fmt(room.schedule.night_temp, 1, "°C") : fmt(room.schedule.night_offset, 1, "°C")}</span></div>`}
          ${preheat}
          ${room.valves && room.valves.length ? this._renderValves(room) : ""}
          ${room.aircos && room.aircos.length ? this._renderAirco(room, admin) : ""}
          <div class="row small"><span>Model</span><span>${this._confidenceBar(room.model.confidence)}</span></div>
          <details><summary>${room.loops.length} lus${room.loops.length === 1 ? "" : "sen"}</summary><ul class="loops">${loops}</ul></details>
          ${admin ? `<div class="actions">
            <button class="btn text" data-action="edit-room" data-room="${room.id}">Bewerken</button>
            <button class="btn text danger" data-action="delete-room" data-room="${room.id}">Verwijderen</button>
          </div>` : ""}
        </div>`;
      })
      .join("");
    return `
      <div class="summary">
        <div class="card stat">
          <div class="muted">Buiten</div><div class="big">${fmt(s.outdoor_temperature, 1)}<small>°C</small></div>
        </div>
        <div class="card stat">
          <div class="muted">Graaddagen vandaag</div><div class="big">${fmt(s.energy?.degree_days_today, 1)}</div>
          <div class="muted small">prognose ${fmt(s.energy?.degree_days_today_forecast, 1)}</div>
        </div>
        <div class="card stat">
          <div class="muted">Bespaard totaal</div><div class="big">${fmt(s.energy?.saved_total, 1)}<small>m³</small></div>
          <div class="muted small">${euro(s.energy?.saved_total === null || s.energy?.saved_total === undefined ? null : s.energy.saved_total * s.energy.gas_price)}</div>
        </div>
        <div class="card stat">
          <div class="muted">Openhaard</div>
          <div class="mid">${fp.configured ? (fp.active ? "🔥 Actief" : "Niet actief") : "Niet ingesteld"}</div>
          ${fp.configured ? `<div class="muted small">${fp.minutes_today} min vandaag</div>` : ""}
        </div>
      </div>
      <div class="bar">
        <label class="switch-label">
          <label class="switch"><input type="checkbox" data-action="master" ${s.master ? "checked" : ""} ${admin ? "" : "disabled"}><span class="slider"></span></label>
          <span>Alle thermostaten nachtverlaging</span>
        </label>
        <div class="spacer"></div>
        ${admin ? '<button class="btn" data-action="add-room">+ Kamer toevoegen</button>' : ""}
      </div>
      ${rooms ? `<div class="grid">${rooms}</div>` : `<div class="card empty"><h2>Nog geen kamers</h2><p>Voeg een kamer toe en koppel de vloerverwarmingslussen (climate-entiteiten).</p></div>`}
    `;
  }

  _renderValves(room) {
    const v = room.valve;
    const width = Math.max(0, Math.min(100, v ?? 0));
    const detail = room.valves
      .map((x) => `${esc(x.name || x.entity_id)}: ${x.position === null || x.position === undefined ? "–" : fmt(x.position, 0, "%")}`)
      .join("&#10;");
    const max = room.valves.length > 1 && room.valve_max !== null ? ` · max ${fmt(room.valve_max, 0, "%")}` : "";
    return `<div class="row small" title="${detail}"><span>Klepstand</span>
      <span class="conf"><span class="conf-bar"><span style="width:${width}%;background:${COLORS.valve}"></span></span>${v === null || v === undefined ? "–" : fmt(v, 0, "%")}${max}</span></div>`;
  }

  _renderAirco(room, admin) {
    const MODES = { off: "Uit", cool: "Koelen", heat: "Verwarmen", heat_cool: "Auto", auto: "Auto", dry: "Drogen", fan_only: "Ventilator" };
    const ACTIONS = { cooling: "koelt", heating: "verwarmt", idle: "inactief", off: "uit", drying: "droogt", fan: "ventileert" };
    const list = room.aircos
      .map((a) => {
        if (!a.available) return `<div class="airco-line muted">${esc(a.name || a.entity_id)}: niet beschikbaar</div>`;
        const action = a.hvac_action ? ACTIONS[a.hvac_action] || a.hvac_action : "";
        return `<div class="airco-line"><span>${esc(a.name || a.entity_id)}</span>
          <span class="muted">${MODES[a.hvac_mode] || esc(a.hvac_mode)}${action ? ` · ${action}` : ""} · ${fmt(a.current_temperature, 1, "°C")} → ${fmt(this._pendingAirco[room.id] ?? a.target_temperature, 1, "°C")}</span></div>`;
      })
      .join("");
    const mode = room.aircos.find((a) => a.available)?.hvac_mode;
    const btn = (m, label) => `<button class="seg ${mode === (m === "boost" ? "heat" : m) ? "active" : ""}" data-action="airco-mode" data-room="${room.id}" data-mode="${m}" ${admin ? "" : "disabled"}>${label}</button>`;
    return `<div class="airco">
      <div class="airco-head"><span class="airco-title">❄ Airco ${room.airco_active ? '<span class="chip" style="--chip:#29b6f6">actief · niet in model</span>' : ""}</span>
        ${admin && room.aircos.some((a) => a.available) ? `<span class="thermo small" data-airco-setpoint="${room.id}">
          <button class="step-btn" data-action="airco-temp" data-room="${room.id}" data-delta="-0.5" aria-label="Airco lager">−</button>
          <button class="sp-btn" data-action="edit-temp" data-kind="airco" data-room="${room.id}" title="Klik om een temperatuur in te typen">
            <span class="sp-value">${fmt(this._pendingAirco[room.id] ?? room.aircos.find((a) => a.available)?.target_temperature, 1)}</span><small>°C</small></button>
          <button class="step-btn" data-action="airco-temp" data-room="${room.id}" data-delta="0.5" aria-label="Airco hoger">+</button></span>` : ""}
      </div>
      ${list}
      <div class="segmented small airco-modes">${btn("off", "Uit")}${btn("cool", "Koelen")}${btn("boost", "Boost")}</div>
    </div>`;
  }

  _confidenceBar(value) {
    const v = Math.max(0, Math.min(100, value || 0));
    const color = v >= 70 ? "#43a047" : v >= 40 ? "#ffa726" : "#e53935";
    return `<span class="conf"><span class="conf-bar"><span style="width:${v}%;background:${color}"></span></span>${fmt(v, 0)}%</span>`;
  }

  /* ----- Room dialog ----- */
  _renderDialog() {
    const d = this._dialog;
    const room = d.room || { name: "", climates: [] };
    const usedElsewhere = new Set(
      this._state.rooms.filter((r) => r.id !== room.id).flatMap((r) => [...r.climates, ...(r.config.aircos || [])])
    );
    const roomAircos = d.aircos || room.config?.aircos || [];
    const roomValves = room.config?.valves || [];
    const usedValves = new Set(this._state.rooms.filter((r) => r.id !== room.id).flatMap((r) => r.config.valves || []));
    const valveSensors = this._entities(
      (s) =>
        s.entity_id.startsWith("sensor.") &&
        (roomValves.includes(s.entity_id) ||
          (s.attributes.unit_of_measurement === "%" && !["battery", "humidity", "moisture"].includes(s.attributes.device_class)) ||
          /stelgro|stelwaarde|klep|valve|command.?value/i.test(`${s.entity_id} ${s.attributes.friendly_name || ""}`))
    );
    // Valve sensors that match the room name first, so the right ones are easy to find.
    const roomWords = (room.name || "").toLowerCase().split(/[^a-z0-9]+/).filter((w) => w.length > 2 && !["en", "kamer"].includes(w));
    const matches = (c) => roomWords.some((w) => c.name.toLowerCase().includes(w) || c.id.includes(w));
    valveSensors.sort((a, b) => Number(matches(b)) - Number(matches(a)) || a.name.localeCompare(b.name));
    const climates = this._entities((s) => s.entity_id.startsWith("climate."));
    const list = climates
      .map((c) => {
        const used = usedElsewhere.has(c.id);
        const checked = (d.selected || room.climates).includes(c.id);
        return `<label class="check ${used ? "disabled" : ""}" data-name="${esc(c.name.toLowerCase())} ${esc(c.id)}">
          <input type="checkbox" name="climate" value="${esc(c.id)}" ${checked ? "checked" : ""} ${used ? "disabled" : ""}>
          <span>${esc(c.name)}<br><small class="muted">${esc(c.id)}${used ? " · in andere kamer" : ""}</small></span></label>`;
      })
      .join("");
    return `
      <div class="overlay" data-action="close-dialog-bg">
        <div class="dialog" role="dialog" aria-modal="true">
          <h2>${room.id ? "Kamer bewerken" : "Kamer toevoegen"}</h2>
          <label class="field"><span>Naam</span><input id="room-name" type="text" value="${esc(room.name)}" placeholder="bijv. Woonkamer en keuken"></label>
          <label class="field"><span>Vloerverwarmingslussen</span>
            <input id="climate-filter" type="search" placeholder="Zoeken…"></label>
          <div class="checklist" id="climate-list">${list || '<p class="muted">Geen climate-entiteiten gevonden.</p>'}</div>
          <label class="field"><span>Airco's (koelen / snel bijverwarmen) – optioneel</span></label>
          <div class="checklist short" id="airco-list">${climates
            .map((c) => {
              const used = usedElsewhere.has(c.id);
              return `<label class="check ${used ? "disabled" : ""}" data-name="${esc(c.name.toLowerCase())} ${esc(c.id)}">
                <input type="checkbox" name="airco" value="${esc(c.id)}" ${roomAircos.includes(c.id) ? "checked" : ""} ${used ? "disabled" : ""}>
                <span>${esc(c.name)}<br><small class="muted">${esc(c.id)}${used ? " · in andere kamer" : ""}</small></span></label>`;
            })
            .join("")}</div>
          <p class="muted small">Airco's doen niet mee met nachtverlaging, schema's of optimum start. Als een airco verwarmt of koelt, wordt die periode uitgesloten van het vloerverwarmingsmodel.</p>
          <label class="field"><span>Klepstand / stelgraad-sensoren (%) – optioneel</span></label>
          <div class="checklist short" id="valve-list">${valveSensors.length ? valveSensors
            .map((c) => {
              const used = usedValves.has(c.id);
              const state = this._hass.states[c.id];
              return `<label class="check ${used ? "disabled" : ""}" data-name="${esc(c.name.toLowerCase())} ${esc(c.id)}">
                <input type="checkbox" name="valve" value="${esc(c.id)}" ${roomValves.includes(c.id) ? "checked" : ""} ${used ? "disabled" : ""}>
                <span>${esc(c.name)}<br><small class="muted">${esc(c.id)} · ${esc(state?.state ?? "–")} ${esc(state?.attributes.unit_of_measurement ?? "")}${used ? " · in andere kamer" : ""}</small></span></label>`;
            })
            .join("") : '<p class="muted small">Geen klepstand-sensoren gevonden (sensor met eenheid % of met stelgrootte/klep in de naam).</p>'}</div>
          <p class="muted small">Bijv. KNX- of vloerverwarmingsactoren (0–100 %). Indien gekoppeld gebruikt HA Climate de gemiddelde klepopening voor het stookpercentage en het thermische model (opwarmsnelheid).</p>
          <p class="muted small">De schema's (dag-/nachttemperatuur, tijden, optimum start) stel je in op het tabblad Schema's.</p>
          <div class="actions">
            <button class="btn text" data-action="close-dialog">Annuleren</button>
            <button class="btn" data-action="save-room">Opslaan</button>
          </div>
        </div>
      </div>`;
  }

  /* ----- Analytics ----- */
  _renderAnalytics() {
    const s = this._state;
    const b = s.baseline;
    const e = s.energy || {};
    const rows = this._history || [];
    const periods = [14, 30, 60, 90, 365]
      .map((d) => `<button class="seg ${d === this._days ? "active" : ""}" data-action="days" data-days="${d}">${d} d</button>`)
      .join("");
    const sum = (key) => rows.reduce((acc, r) => acc + (r[key] ?? 0), 0);
    const costDays = rows.filter((r) => r.cost !== null && r.cost !== undefined).length;
    const periodCost = sum("cost");
    const periodVariable = sum("cost_variable");
    const periodGas = sum("gas");
    const fixed = e.fixed_costs ?? 0;
    const costTile = (title, total, gas, days) => `
      <div class="card stat"><div class="muted">${title}</div><div class="big">${euro(total)}</div>
        <div class="muted small">${gas !== null && gas !== undefined ? `${fmt(gas, 2, "m³")} × ${euro(e.gas_price)}` : "geen gasdata"}${fixed ? ` + ${euro(fixed * (days ?? 1))} vast` : ""}</div></div>`;
    const baselineFrom = b.first_day ? dateLabel(b.first_day) : "–";
    const excluded = [
      b.excluded_fireplace ? `${b.excluded_fireplace} openhaard` : "",
      b.excluded_setback ? `${b.excluded_setback} nachtverlaging` : "",
      b.excluded_warm ? `${b.excluded_warm} warm (&lt; 1 graaddag)` : "",
      b.excluded_invalid ? `${b.excluded_invalid} onvolledig` : "",
    ].filter(Boolean).join(", ");
    return `
      <div class="summary">
        <div class="card stat"><div class="muted">Baseline</div><div class="big">${fmt(b.m3_per_degree_day, 3)}<small>m³/gd</small></div>
          <div class="muted small">${b.days_used} dagen${b.first_day ? ` vanaf ${baselineFrom}` : ""}${b.reliable ? "" : " · nog onbetrouwbaar"}</div></div>
        ${costTile("Gaskosten vandaag", e.cost_today, e.gas_today, 1)}
        ${costTile("Gaskosten gisteren", e.cost_yesterday, e.gas_yesterday, 1)}
        <div class="card stat"><div class="muted">Gaskosten periode (${this._days} d)</div><div class="big">${rows.length ? euro(periodCost) : "–"}</div>
          <div class="muted small">${rows.length ? `${euro(periodVariable)} variabel + ${euro(fixed * costDays)} vast · ${fmt(periodGas, 1, "m³")}` : "laden…"}</div></div>
      </div>
      <div class="bar"><div class="segmented">${periods}</div><div class="spacer"></div>
        <button class="btn text" data-action="export">⬇ Exporteer CSV</button>
        ${this._admin ? '<button class="btn text" data-action="recalculate">Baseline herberekenen</button>' : ""}</div>
      ${this._renderMeasurement()}
      ${this._renderHourly()}
      <div class="card">
        <h3>Graaddagen vs. gasverbruik per dag</h3>
        <div class="legend">
          <span><i style="background:${COLORS.gas}"></i>Werkelijk gas (m³)</span>
          <span><i class="line" style="background:${COLORS.expected}"></i>Verwacht gas (m³)</span>
          <span><i class="line" style="background:${COLORS.degreeDays}"></i>Graaddagen</span>
          <span><i class="line start-key"></i>Start meting</span>
          <span><i class="event-key"></i>Instelling gewijzigd</span>
        </div>
        <div class="chart" id="chart-gas"></div>
        <p class="muted small">
          <b>Referentie (baseline):</b> ${fmt(b.m3_per_degree_day, 3, "m³ per graaddag")} geleerd uit <b>${b.days_used} dagen</b>
          ${b.first_day ? `van ${dateLabel(b.first_day)} t/m ${dateLabel(b.last_day)}` : ""}.
          ${b.overlap_start ? `Beide sensoren hebben data vanaf <b>${dateLabel(b.overlap_start)}</b>; ` : ""}${b.days_stored ? `${b.days_stored} dagen permanent opgeslagen.` : ""}
          ${excluded ? `Overgeslagen: ${excluded}.` : ""}
          ${b.indoor_correction ? `Graaddagen gecorrigeerd voor de comforttemperatuur t.o.v. ${fmt(b.reference_temperature, 1, "°C")}.` : ""}
          ${b.updated ? `Laatst berekend ${dateLabel(b.updated)} ${timeOf(b.updated)}.` : ""}
        </p>
      </div>
      <div class="card">
        <div class="card-head"><h3>Besparing sinds de start</h3>
          <div class="segmented small">
            <button class="seg ${this._chartUnit === "m3" ? "active" : ""}" data-action="unit" data-unit="m3">m³</button>
            <button class="seg ${this._chartUnit === "eur" ? "active" : ""}" data-action="unit" data-unit="eur">€</button>
          </div></div>
        <div class="chart" id="chart-savings"></div>
        <p class="muted small">Opgeteld vanaf de start van de meting (${dateLabel(b.measurement_start)}). Besparing = verwacht (referentie × graaddagen) − werkelijk,
          omgerekend met de variabele gasprijs; vaste leveringskosten tellen niet mee. Dagen met nachtverlaging zijn gearceerd.</p>
      </div>
      ${s.boiler ? this._renderBoiler() : ""}
      ${this._renderModelSection()}`;
  }

  /* ----- Hourly: what does the setback save, what does the reheat cost? ----- */
  _renderHourly() {
    const today = new Date();
    const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const days = Array.from({ length: 7 }, (_, i) => {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      return iso(d);
    });
    const selected = this._hourlyDay || days[0];
    const label = (d, i) => (i === 0 ? "Vandaag" : i === 1 ? "Gisteren" : dayLabel(d));
    const buttons = days
      .map((d, i) => `<button class="seg ${d === selected ? "active" : ""}" data-action="hourly-day" data-day="${d}">${label(d, i)}</button>`)
      .join("");
    const h = this._hourly;
    const price = this._state.energy?.gas_price ?? 0;
    let body = '<div class="spinner"></div>';
    if (h && (!h.hours || !h.hours.length)) {
      body = `<p class="muted">${h.baseline === null || h.baseline === undefined ? "Nog geen baseline: het verwachte verbruik per uur is nog niet bekend." : "Geen uurstatistieken gevonden voor deze dag."}</p>`;
    } else if (h) {
      const sm = h.summary;
      const val = (v) => `${v >= 0 ? "" : "−"}${fmt(Math.abs(v), 2, "m³")}`;
      const tile = (title, part, sub) => `<div class="tile ${part.saved < -0.05 ? "warn" : ""}"><div class="muted small">${title}</div>
        <div class="mid">${val(part.saved)}</div><div class="muted small">${euro(part.saved * price)} · ${part.hours} uur · ${fmt(part.gas, 2, "m³")} van ${fmt(part.expected, 2, "m³")} verwacht${sub ? ` · ${sub}` : ""}</div></div>`;
      const pair = sm.setback_and_recovery;
      let verdict;
      if (!sm.setback.hours) verdict = "In deze periode was er (volgens het huidige schema) geen verlaging actief.";
      else if (pair > 0.1) verdict = `<b>Verlagen loont hier:</b> de besparing tijdens de verlaging is groter dan het extra gas om weer op te warmen (netto ${val(pair)}, ${euro(pair * price)}).`;
      else if (pair < -0.1) verdict = `<b>Het opwarmen kost meer dan de verlaging bespaart</b> (netto ${val(pair)}). Kijk een paar dagen mee; blijft dit zo, verlaag dan minder diep of korter, of gebruik optimum start. Op het tabblad Tips verschijnt dan ook advies.`;
      else verdict = `<b>Ongeveer neutraal:</b> wat de verlaging bespaart gaat grotendeels op aan het opwarmen (netto ${val(pair)}).`;
      body = `
        <div class="tiles">${tile("Tijdens de verlaging", sm.setback)}${tile("Opwarmen (6 uur erna)", sm.recovery, "negatief = extra")}${tile("Verlaging + opwarmen", { ...sm.setback, saved: pair, hours: sm.setback.hours + sm.recovery.hours, gas: sm.setback.gas + sm.recovery.gas, expected: sm.setback.expected + sm.recovery.expected })}${tile("Hele periode", { saved: sm.net, hours: sm.setback.hours + sm.recovery.hours + sm.other.hours, gas: sm.setback.gas + sm.recovery.gas + sm.other.gas, expected: sm.setback.expected + sm.recovery.expected + sm.other.expected })}</div>
        <p class="small">${verdict}</p>
        <div class="legend">
          <span><i style="background:${COLORS.gas}"></i>Werkelijk gas per uur (m³)</span>
          <span><i class="line" style="background:${COLORS.expected}"></i>Verwacht zonder verlaging (m³)</span>
          <span><i class="line" style="background:${COLORS.saved}"></i>Opgeteld bespaard (m³)</span>
          <span><i class="shade-key"></i>Verlaagd</span>
        </div>
        <div class="chart" id="chart-hourly"></div>`;
    }
    return `
      <div class="card">
        <div class="card-head"><h3>Per uur: wat levert de verlaging op?</h3></div>
        <div class="segmented small scroll day-select">${buttons}</div>
        ${body}
        <p class="muted small">Van 12:00 de dag ervoor tot 24:00 (afgeronde uren). ${h && h.profile_days
          ? `Verwacht per uur = het verwachte dagverbruik, verdeeld over de uren zoals het huis vóór de start stookte (geleerd uit ${h.profile_days} koude dagen zonder verlaging).
             Vaste gewoontes zoals douchen en de ochtendpiek zitten daar al in, en tellen dus niet als opwarmkosten.`
          : `Verwacht per uur = baseline × (stookgrens − buitentemperatuur van dat uur) ÷ 24 (gelijk over de dag verdeeld; er zijn nog te weinig koude dagen zonder verlaging om het dagpatroon van het huis te leren).
             Let op: de ochtend lijkt daardoor duurder dan hij is, want douchen en de ochtendpiek vallen op vaste uren.`}
          Dit is wat het huis zonder verlaging zou verbruiken. Tijdens de verlaging hoort het verbruik lager te liggen; daarna stookt de ketel extra om weer op te warmen.
          Telt dat samen positief op, dan loont verlagen. Douchen en koken tellen mee, dus een enkel uur of een enkele dag zegt weinig – kijk naar meerdere dagen.
          Gearceerd = meer dan de helft van de lussen verlaagd volgens het huidige schema.</p>
      </div>`;
  }

  _renderHourlyChart() {
    const el = this.shadowRoot.getElementById("chart-hourly");
    const h = this._hourly;
    if (!el || !h || !h.hours || !h.hours.length) return;
    const rows = h.hours;
    el.innerHTML = chart({
      width: el.clientWidth || 700,
      labels: rows.map((r) => {
        const t = timeOf(r.start);
        return t === "00:00" ? `${dayLabel(r.start.slice(0, 10))}` : t;
      }),
      shade: rows.map((r) => r.lowered >= 0.5),
      shadeLabel: "verlaagd",
      labelWidth: 44,
      series: [
        { name: "Werkelijk", type: "bar", axis: "left", color: COLORS.gas, values: rows.map((r) => r.gas), unit: "m³", digits: 2 },
        { name: "Verwacht", type: "line", axis: "left", color: COLORS.expected, values: rows.map((r) => r.expected), unit: "m³", digits: 2 },
        { name: "Opgeteld bespaard", type: "line", axis: "right", color: COLORS.saved, values: rows.map((r) => r.cumulative_saved), unit: "m³", digits: 2 },
        { name: "Buiten", type: "tooltip", axis: "left", color: "#78909c", values: rows.map((r) => r.temperature), unit: "°C" },
        { name: "Verlaagd", type: "tooltip", axis: "left", color: "#9e9e9e", values: rows.map((r) => Math.round(r.lowered * 100)), unit: "%", digits: 0 },
      ],
    });
  }

  /* ----- Boiler & efficiency (only when configured) ----- */
  _renderBoiler() {
    const b = this._state.boiler;
    const t = b.today || {};
    const rows = (this._history || []).filter((r) => r.boiler);
    const ent = b.entities || {};
    const onOff = (value, on, off) => (value === null || value === undefined ? "–" : value ? on : off);
    const flameChip = b.flame === null || b.flame === undefined
      ? ""
      : `<span class="chip" style="--chip:${b.flame ? (b.dhw ? COLORS.dhw : COLORS.heat) : "#9e9e9e"}">${b.flame ? (b.dhw ? "Brandt · tapwater" : "Brandt · verwarming") : "Uit"}</span>`;
    const pressureColor = { low: "#e53935", high: "#fb8c00", ok: "#43a047" }[b.pressure_status] || "#9e9e9e";
    const pressureText = { low: "te laag – bijvullen", high: "hoog", ok: "in orde" }[b.pressure_status] || "";
    const errorOk = b.error === null || b.error === undefined || ["0", "none", "geen", "ok", "no error", "off"].includes(String(b.error).toLowerCase());
    const status = [];
    if (ent.boiler_flame) status.push(`<div class="bstat"><span class="muted small">Brander</span>${flameChip}
      ${b.current_run_minutes !== null && b.current_run_minutes !== undefined ? `<span class="muted small">loopt ${minutesText(b.current_run_minutes)}</span>` : ""}</div>`);
    if (ent.boiler_heat_request) status.push(`<div class="bstat"><span class="muted small">Warmtevraag</span><b>${onOff(b.heat_request, "Ja", "Nee")}</b></div>`);
    if (ent.boiler_dhw && !ent.boiler_flame) status.push(`<div class="bstat"><span class="muted small">Tapwater</span><b>${onOff(b.dhw, "Actief", "Niet actief")}</b></div>`);
    if (ent.boiler_modulation) status.push(`<div class="bstat"><span class="muted small">Modulatie</span><b>${fmt(b.modulation, 0, "%")}</b></div>`);
    if (ent.boiler_flow_temp || ent.boiler_flow_setpoint) {
      const diff = b.flow_temperature !== null && b.flow_setpoint !== null && b.flow_temperature !== undefined && b.flow_setpoint !== undefined
        ? b.flow_temperature - b.flow_setpoint : null;
      status.push(`<div class="bstat"><span class="muted small">Aanvoer / gevraagd</span><b>${fmt(b.flow_temperature, 1, "°C")} / ${fmt(b.flow_setpoint, 1, "°C")}</b>
        ${diff !== null ? `<span class="muted small">${diff >= 0 ? "+" : ""}${fmt(diff, 1, "°C")}</span>` : ""}</div>`);
    }
    if (ent.boiler_pressure) status.push(`<div class="bstat"><span class="muted small">Waterdruk</span>
      <span class="chip" style="--chip:${pressureColor}">${fmt(b.pressure, 1, "bar")}</span><span class="muted small">${pressureText}</span></div>`);
    if (ent.boiler_error) status.push(`<div class="bstat"><span class="muted small">Foutcode</span>
      <span class="chip" style="--chip:${errorOk ? "#43a047" : "#e53935"}">${errorOk ? "Geen storing" : esc(b.error)}</span></div>`);
    if (b.max_valve !== null && b.max_valve !== undefined) status.push(`<div class="bstat"><span class="muted small">Hoogste klepstand</span><b>${fmt(b.max_valve, 0, "%")}</b></div>`);

    // Period figures (completed + today's partial days).
    const sum = (key) => rows.reduce((acc, r) => acc + (r.boiler[key] ?? 0), 0);
    const daysWithStarts = rows.filter((r) => r.boiler.starts !== null && r.boiler.starts !== undefined);
    const periodStarts = sum("starts");
    const periodHours = sum("burn_hours");
    const runWeighted = rows.reduce((acc, r) => acc + (r.boiler.avg_run_minutes ?? 0) * (r.boiler.starts ?? 0), 0);
    const periodAvgRun = periodStarts ? runWeighted / periodStarts : null;
    const periodDhw = sum("dhw_minutes");
    const periodHeat = sum("heat_minutes");
    const flowRows = rows.filter((r) => r.boiler.flow_avg !== null && r.boiler.flow_avg !== undefined);
    const periodFlow = flowRows.length ? flowRows.reduce((a, r) => a + r.boiler.flow_avg, 0) / flowRows.length : null;
    const cyclingPeriod = periodStarts >= 3 && periodAvgRun !== null && periodAvgRun < 10;
    const tile = (title, value, sub, warn = false) => `<div class="tile ${warn === true ? "warn" : warn || ""}"><div class="muted small">${title}</div><div class="mid">${value}</div><div class="muted small">${sub}</div></div>`;
    const kpis = [
      tile("Branderstarts vandaag", t.starts ?? "–", daysWithStarts.length ? `gem. ${fmt(periodStarts / daysWithStarts.length, 1)} per dag (${daysWithStarts.length} d)` : ""),
      tile("Branduren vandaag", t.burn_hours !== null && t.burn_hours !== undefined ? `${fmt(t.burn_hours, 1)}<small>uur</small>` : "–", rows.length ? `${fmt(periodHours, 1)} uur in ${this._days} d` : ""),
      tile("Gem. brandtijd per start", minutesText(t.avg_run_minutes),
        b.cycling
          ? "⚠ pendelen: gemiddeld korter dan 10 min per start"
          : b.short_runs_warning
            ? `⚠ ${t.short_runs} van ${t.runs} afgeronde runs korter dan 10 min (vaak bij lage warmtevraag, bijv. tijdens de verlaging) · periode ${minutesText(periodAvgRun)}`
            : `${t.short_runs ? `${t.short_runs} korte runs vandaag · ` : ""}periode ${minutesText(periodAvgRun)}${cyclingPeriod ? " ⚠" : ""}`,
        b.cycling ? "warn" : b.short_runs_warning ? "note" : false),
      tile("Gem. aanvoertemperatuur", t.flow_avg !== null && t.flow_avg !== undefined ? `${fmt(t.flow_avg, 1)}<small>°C</small>` : "–",
        `tijdens branden${periodFlow !== null ? ` · periode ${fmt(periodFlow, 1, "°C")}` : ""}${t.modulation_avg !== null && t.modulation_avg !== undefined ? ` · modulatie ${fmt(t.modulation_avg, 0, "%")}` : ""}`),
    ].join("");

    const split = (dhw, heat) => {
      const total = (dhw ?? 0) + (heat ?? 0);
      if (!total) return '<span class="muted small">nog geen branduren</span>';
      const pct = (dhw / total) * 100;
      return `<div class="split"><span style="width:${pct}%;background:${COLORS.dhw}"></span><span style="width:${100 - pct}%;background:${COLORS.heat}"></span></div>
        <div class="muted small">Tapwater ${minutesText(dhw)} (${fmt(pct, 0)}%) · Verwarming ${minutesText(heat)} (${fmt(100 - pct, 0)}%)</div>`;
    };
    const dhwBlock = ent.boiler_dhw
      ? `<h3 class="sub">Tapwater vs. verwarming</h3>
        <div class="tiles">
          <div class="tile"><div class="muted small">Vandaag</div>${split(t.dhw_minutes, t.heat_minutes)}</div>
          <div class="tile"><div class="muted small">Periode (${this._days} d)</div>${split(periodDhw, periodHeat)}</div>
        </div>`
      : "";
    const hasTraceData = ent.boiler_flow_temp || ent.boiler_flow_setpoint || ent.boiler_modulation;
    const hasValves = this._state.rooms.some((r) => r.valves && r.valves.length);
    return `
      <div class="card boiler">
        <div class="card-head"><h3>Ketel &amp; efficiëntie</h3>
          ${b.cycling ? '<span class="chip" style="--chip:#e53935">Pendelen</span>' : b.short_runs_warning ? '<span class="chip" style="--chip:#fb8c00">Veel korte runs</span>' : ""}</div>
        ${status.length ? `<div class="bstatus">${status.join("")}</div>` : ""}
        <div class="tiles">${kpis}</div>
        <p class="muted small">${b.tracking_flame ? "Starts en branduren worden geteld vanuit de vlamstatus" : "Geen vlamstatus ingesteld: starts en branduren alleen uit de ketelsensoren"}${ent.boiler_starts_today || ent.boiler_hours_today || ent.boiler_avg_runtime ? "; de tellers van de ketel zelf gaan voor" : ""}.
          Bij gemiddeld minder dan 10 minuten per start (en minimaal 3 starts) wordt pendelen gemeld – vaak is de aanvoertemperatuur dan te hoog of het minimale vermogen te groot voor de warmtevraag.</p>
        ${dhwBlock}
        ${hasTraceData ? `<h3 class="sub">Aanvoer vs. gevraagd &amp; modulatie – laatste 24 uur</h3>
        <div class="legend">
          ${ent.boiler_flow_temp ? `<span><i class="line" style="background:${COLORS.flow}"></i>Aanvoer (°C)</span>` : ""}
          ${ent.boiler_flow_setpoint ? `<span><i class="line" style="background:${COLORS.setpoint}"></i>Gevraagd (°C)</span>` : ""}
          ${ent.boiler_modulation ? `<span><i class="line" style="background:${COLORS.modulation}"></i>Modulatie (%)</span>` : ""}
          ${hasValves ? `<span><i class="line" style="background:${COLORS.valve}"></i>Hoogste klepstand (%)</span>` : ""}
          ${ent.boiler_flame ? '<span><i class="shade-key"></i>Brander aan</span>' : ""}
        </div>
        <div class="chart" id="chart-boiler"></div>` : ""}
        ${rows.length ? `<h3 class="sub">Branderstarts &amp; branduren per dag</h3><div class="chart" id="chart-boiler-days"></div>` : ""}
      </div>`;
  }

  _renderRanking() {
    const ranking = this._state.ranking || [];
    if (!ranking.length) return "";
    const color = { "Hoog warmteverlies": "#e53935", "Stookt veel": "#fb8c00", Gemiddeld: "#f9a825", Zuinig: "#43a047" };
    const rows = ranking
      .map(
        (r) => `<tr>
          <td class="rank">${r.rank}</td>
          <td><b>${esc(r.name)}</b><br><span class="chip" style="--chip:${color[r.label] || "#9e9e9e"}">${esc(r.label)}</span>
            ${r.tags.filter((t) => t.toLowerCase() !== r.label.toLowerCase()).map((t) => `<span class="muted small"> · ${esc(t)}</span>`).join("")}</td>
          <td>${r.heat_loss !== null ? `${fmt(r.heat_loss, 4)}<br><small class="muted">°C/u per °C ΔT</small>` : "–"}</td>
          <td>${r.duty !== null ? `${fmt(r.duty * 100, 0)}%<br><small class="muted">${r.windows} blokken, ${r.days} d</small>` : `–<br><small class="muted">geen meetblokken in ${r.days} d</small>`}</td>
          <td>${r.score !== null ? `<span class="conf-bar wide"><span style="width:${Math.round(r.score * 100)}%;background:${color[r.label] || "#9e9e9e"}"></span></span>` : ""}</td>
        </tr>`
      )
      .join("");
    return `<div class="table-wrap"><table class="ranking">
      <thead><tr><th>#</th><th>Kamer</th><th>Warmteverlies</th><th>Stookpercentage</th><th>Energiescore</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
      <p class="muted small">Warmteverlies = geleerde afkoelcoëfficiënt (°C/uur per °C verschil met buiten). Stookpercentage = deel van de tijd dat de vloerverwarming actief verwarmde in de afgelopen ${ranking[0].days} dagen${this._state.rooms.some((r) => r.valves && r.valves.length) ? " (bij kamers met klepstand-sensoren: de gemiddelde klepopening)" : ""}. De energiescore combineert beide, relatief tot de slechtste kamer.</p>`;
  }

  _renderModelSection() {
    const rooms = this._state.rooms;
    if (!rooms.length) {
      return `<div class="card"><h3>Thermisch model per kamer</h3><p class="muted">Nog geen kamers.</p></div>`;
    }
    if (!rooms.some((r) => r.id === this._room)) this._room = rooms[0].id;
    const room = rooms.find((r) => r.id === this._room);
    const m = room.model;
    const st = room.model_status;
    const stage = st.stage;
    const steps = [
      ["Data verzamelen", "Meetblokken van 2 uur uit historie en live metingen"],
      ["Kamer leren", "Afkoel- en opwarmgedrag worden geschat"],
      ["Voorspellend regelen", "Optimum start gebruikt het geleerde model"],
    ]
      .map(([title, text], i) => {
        const n = i + 1;
        const cls = n < stage ? "done" : n === stage ? "current" : "";
        return `<div class="step ${cls}"><div class="step-dot">${n < stage ? "✓" : n}</div>
          <div><div class="step-title">${title}</div><div class="muted small">${text}</div></div></div>`;
      })
      .join('<div class="step-line"></div>');
    const backfill = st.backfill || {};
    const tau = st.time_constant;
    const select = rooms
      .map((r) => `<option value="${esc(r.id)}" ${r.id === room.id ? "selected" : ""}>${esc(r.name)}</option>`)
      .join("");
    return `
      <div class="card">
        <div class="card-head"><h3>Thermisch model per kamer</h3>
          <select class="room-select" data-action="room-select">${select}</select></div>
        <div class="model-status">
          <div class="model-head">
            <div>
              <div class="muted small">Model status</div>
              <div class="big">${fmt(st.confidence, 0)}<small>%</small></div>
              <div class="muted small">confidence · afkoelen ${fmt(st.cooling_confidence, 0)}% · opwarmen ${fmt(st.heating_confidence, 0)}%</div>
            </div>
            <div>
              <div class="muted small">Data points</div>
              <div class="big">${st.data_points}</div>
              <div class="muted small">${st.from_history} uit historie · ${st.from_live} live</div>
            </div>
          </div>
          <div class="steps">${steps}</div>
          <div class="tiles">
            <div class="tile">
              <div class="muted small">Afkoelsnelheid / warmteverlies</div>
              <div class="mid">${fmt(m.cooling_rate, 2)}<small>°C/u</small></div>
              <div class="muted small">bij ΔT ${fmt(m.delta_t, 1, "°C")} · ${fmt(st.cooling_coefficient, 4)} °C/u per °C</div>
            </div>
            <div class="tile">
              <div class="muted small">Opwarmsnelheid</div>
              <div class="mid">${fmt(m.heating_rate, 2)}<small>°C/u</small></div>
              <div class="muted small">netto bij volle verwarming · bruto ${fmt(st.heating_power, 2)} °C/u</div>
            </div>
            <div class="tile">
              <div class="muted small">Tijdconstante</div>
              <div class="mid">${tau ? fmt(tau, tau >= 100 ? 0 : 1) : "–"}<small>uur</small></div>
              <div class="muted small">τ = 1/k: hoe traag de kamer reageert</div>
            </div>
          </div>
          <p class="muted small">
            ${st.first ? `Data vanaf <b>${dateLabel(st.first)}</b> t/m ${dateLabel(st.last)}: <b>${st.data_points} meetpunten</b> over <b>${st.days} dagen</b>
              (${st.heating_points} met verwarming, ${st.cooling_points} afkoelend in de fit).`
              : st.data_points ? `${st.data_points} meetpunten uit een eerdere versie (zonder datum); nieuwe meetpunten krijgen een tijdstempel.` : "Nog geen meetpunten."}
            ${st.fit_points !== st.data_points && st.fit_first ? ` De fit gebruikt de laatste ${st.fit_points} meetpunten vanaf ${dateLabel(st.fit_first)} (meest recente seizoen).` : ""}
            ${backfill.analysed_at ? `<br>Recorder-historie ${backfill.start ? `vanaf ${dateLabel(backfill.start)} ${timeOf(backfill.start)}` : "(geen bruikbare historie)"} geanalyseerd op ${dateLabel(backfill.analysed_at)} ${timeOf(backfill.analysed_at)}: ${backfill.windows ?? 0} meetblokken, ${backfill.new ?? 0} nieuw.` : ""}
          </p>
          ${this._admin ? `<div class="actions"><button class="btn text small danger" data-action="reset-model" data-room="${room.id}">Model resetten</button></div>` : ""}
        </div>
        <h3 class="sub">Vergelijking kamers – van minst naar meest zuinig</h3>
        ${this._renderRanking()}
        <div class="chart" id="chart-rooms"></div>
      </div>`;
  }

  _renderCharts() {
    const root = this.shadowRoot;
    const gasEl = root.getElementById("chart-gas");
    if (!gasEl) return;
    const rows = this._history;
    if (!rows) {
      gasEl.innerHTML = '<div class="spinner"></div>';
      return;
    }
    if (!rows.length) {
      gasEl.innerHTML = '<p class="muted">Geen langetermijnstatistieken gevonden voor de gekozen sensoren.</p>';
      root.getElementById("chart-savings").innerHTML = "";
    } else {
      const labels = rows.map((r) => dayLabel(r.date) + (r.partial ? " (nu)" : ""));
      gasEl.innerHTML = chart({
        width: gasEl.clientWidth || 700,
        labels,
        marks: rows.map((r) => (r.fireplace ? "🔥" : "")),
        start: rows.findIndex((r) => r.date === this._state.baseline.measurement_start),
        series: [
          { name: "Werkelijk gas", type: "bar", axis: "left", color: COLORS.gas, values: rows.map((r) => r.gas), unit: "m³", digits: 2 },
          { name: "Verwacht gas", type: "line", axis: "left", color: COLORS.expected, values: rows.map((r) => r.expected), unit: "m³", digits: 2 },
          { name: "Graaddagen", type: "line", axis: "right", color: COLORS.degreeDays, values: rows.map((r) => r.degree_days), unit: "gd", digits: 1, dashed: true },
          { name: "Gaskosten", type: "tooltip", axis: "left", color: COLORS.cost, values: rows.map((r) => r.cost), unit: "€" },
          { name: "Buiten gem.", type: "tooltip", axis: "left", color: "#78909c", values: rows.map((r) => r.mean_temperature), unit: "°C" },
          { name: "Binnen gemeten", type: "tooltip", axis: "left", color: "#ef6c00", values: rows.map((r) => r.indoor_temperature), unit: "°C" },
          { name: "Binnen doel", type: "tooltip", axis: "left", color: "#8e24aa", values: rows.map((r) => r.indoor_target), unit: "°C" },
          { name: "Comfort (dag)", type: "tooltip", axis: "left", color: "#5e35b1", values: rows.map((r) => r.indoor_comfort), unit: "°C" },
          { name: "Stookgrens", type: "tooltip", axis: "left", color: "#9e9e9e", values: rows.map((r) => (this._state.baseline.indoor_correction ? r.heating_limit : null)), unit: "°C" },
        ],
        events: rows.map((r) => summarizeEvents(r.events)),
      });
      const savEl = root.getElementById("chart-savings");
      const eur = this._chartUnit === "eur";
      // Only the days since the start of the measurement.
      const startIso = this._state.baseline.measurement_start;
      const measured = rows.filter((r) => !startIso || r.date >= startIso);
      const complete = measured.filter((r) => !r.partial).length;
      if (!measured.length || (complete === 0 && measured.length <= 1)) {
        savEl.innerHTML = `<div class="placeholder"><b>De meting is ${complete === 0 && measured.length ? "vandaag" : ""} gestart op ${dateLabel(startIso)}.</b><br>
          <span class="muted">Morgen staat hier de eerste volledige dag: hoeveel gas er is verbruikt tegenover wat zonder maatregelen verwacht werd.
          ${measured.length ? `Vandaag tot nu: ${fmt(measured[0].gas, 2, "m³")} verbruikt, ${fmt(measured[0].expected, 2, "m³")} verwacht (voorlopig, de dag is nog niet om).` : ""}</span></div>`;
      } else savEl.innerHTML = chart({
        width: savEl.clientWidth || 700,
        labels: measured.map((r) => dayLabel(r.date) + (r.partial ? " (nu)" : "")),
        shade: measured.map((r) => r.setback),
        events: measured.map((r) => summarizeEvents(r.events)),
        series: [
          {
            name: eur ? "Cumulatief (€)" : "Cumulatief (m³)",
            type: "area",
            axis: "left",
            color: eur ? COLORS.savedEur : COLORS.saved,
            values: measured.map((r) => (eur ? r.cumulative_saved_eur : r.cumulative_saved)),
            unit: eur ? "€" : "m³",
            digits: 2,
          },
          {
            name: eur ? "Per dag (€)" : "Per dag (m³)",
            type: "bar",
            axis: "left",
            color: eur ? COLORS.savedEur : COLORS.saved,
            opacity: 0.35,
            values: measured.map((r) => (eur ? r.saved_eur : r.saved)),
            unit: eur ? "€" : "m³",
            digits: 2,
          },
        ],
      });
    }
    this._renderBoilerCharts();
    this._renderHourlyChart();
    const roomsEl = root.getElementById("chart-rooms");
    if (roomsEl) roomsEl.innerHTML = roomChart(this._state.rooms, roomsEl.clientWidth || 700);
    this._bindCharts();
  }

  _renderBoilerCharts() {
    const root = this.shadowRoot;
    const el = root.getElementById("chart-boiler");
    if (el) {
      const points = this._boilerTrace;
      if (!points) el.innerHTML = '<div class="spinner"></div>';
      else if (!points.length) el.innerHTML = '<p class="muted">Nog geen historie van de ketelsensoren in de recorder.</p>';
      else {
        const ent = this._state.boiler.entities || {};
        const series = [];
        const col = (key) => points.map((p) => (p[key] === undefined ? null : p[key]));
        if (ent.boiler_flow_temp) series.push({ name: "Aanvoer", type: "line", axis: "left", color: COLORS.flow, values: col("flow"), unit: "°C", digits: 1 });
        if (ent.boiler_flow_setpoint) series.push({ name: "Gevraagd", type: "line", axis: "left", color: COLORS.setpoint, values: col("setpoint"), unit: "°C", digits: 1, dashed: true });
        if (ent.boiler_modulation) series.push({ name: "Modulatie", type: "line", axis: "right", color: COLORS.modulation, values: col("modulation"), unit: "%", digits: 0 });
        if (points.some((p) => p.valve_max !== undefined && p.valve_max !== null)) {
          series.push({ name: "Hoogste klepstand", type: "line", axis: "right", color: COLORS.valve, values: col("valve_max"), unit: "%", digits: 0, dashed: true });
        }
        el.innerHTML = chart({
          width: el.clientWidth || 700,
          labels: points.map((p) => timeOf(p.ts)),
          series,
          shade: points.map((p) => p.flame === 1),
          shadeLabel: "brander aan",
          // Mark the start of every hot water period.
          marks: points.map((p, i) => (p.dhw === 1 && (i === 0 || points[i - 1].dhw !== 1) ? "💧" : "")),
          labelWidth: 48,
        });
      }
    }
    const daysEl = root.getElementById("chart-boiler-days");
    if (daysEl) {
      const rows = (this._history || []).filter((r) => r.boiler);
      daysEl.innerHTML = chart({
        width: daysEl.clientWidth || 700,
        labels: rows.map((r) => dayLabel(r.date) + (r.partial ? " (nu)" : "")),
        marks: rows.map((r) => (r.boiler.starts >= 3 && r.boiler.avg_run_minutes !== null && r.boiler.avg_run_minutes < 10 ? "⚠" : "")),
        series: [
          { name: "Starts", type: "bar", axis: "left", color: COLORS.heat, values: rows.map((r) => r.boiler.starts), unit: "", digits: 0 },
          { name: "Branduren", type: "line", axis: "right", color: COLORS.modulation, values: rows.map((r) => r.boiler.burn_hours), unit: "uur", digits: 1 },
          { name: "Gem. looptijd", type: "tooltip", axis: "left", color: "#78909c", values: rows.map((r) => r.boiler.avg_run_minutes), unit: "min", digits: 0 },
          { name: "Tapwater", type: "tooltip", axis: "left", color: COLORS.dhw, values: rows.map((r) => r.boiler.dhw_minutes), unit: "min", digits: 0 },
          { name: "Gem. aanvoer", type: "tooltip", axis: "left", color: COLORS.flow, values: rows.map((r) => r.boiler.flow_avg), unit: "°C", digits: 1 },
          { name: "Graaddagen", type: "tooltip", axis: "left", color: COLORS.degreeDays, values: rows.map((r) => r.degree_days), unit: "gd", digits: 1 },
        ],
      });
    }
  }

  /* ----- Tips ----- */
  _renderTips() {
    if (this._adviceError) {
      return `<div class="card empty"><h2>Tips niet beschikbaar</h2><p>${esc(this._adviceError)}</p>
        <button class="btn" data-action="advice-refresh">Opnieuw proberen</button></div>`;
    }
    const a = this._advice;
    if (!a) return `<div class="card empty"><div class="spinner"></div><p>Tips berekenen uit de laatste 10 dagen…</p></div>`;
    const basis = a.basis;
    const ICON = { measurement: "📏", result: "📊", night: "🌙", day: "🌡", room: "🏠", boiler: "🔥" };
    const CONF = { goed: "#43a047", redelijk: "#ffa726", laag: "#9e9e9e" };
    const tip = (t) => `
      <div class="card tip-card cat-${esc(t.category)}">
        <div class="tip-icon">${ICON[t.category] || "💡"}</div>
        <div class="tip-body">
          <div class="tip-head"><b>${esc(t.title)}</b></div>
          <p>${esc(t.text)}</p>
          ${t.details && t.details.length ? `<ul class="tip-details">${t.details.map((d) => `<li>${esc(d)}</li>`).join("")}</ul>` : ""}
          ${t.action && this._admin ? `<div class="actions left"><button class="btn" data-action="apply-tip" data-tip="${esc(t.id)}">${esc(t.action.label || "Toepassen")}</button></div>` : ""}
        </div>
        ${t.saving_eur_month !== null && t.saving_eur_month !== undefined ? `<div class="tip-saving">
          <div class="mid">${t.saving_eur_month > 0 ? "≈ " : ""}${euro(t.saving_eur_month)}</div>
          <div class="muted small">per maand · ${fmt(t.saving_m3_month, 1, "m³")}</div>
          <span class="chip" style="--chip:${CONF[t.confidence] || "#9e9e9e"}">zekerheid ${esc(t.confidence)}</span>
        </div>` : ""}
      </div>`;
    const head = (t) => t.category === "measurement" || t.category === "result";
    const top = a.tips.filter(head);
    const money = a.tips.filter((t) => !head(t) && t.saving_eur_month !== null && t.saving_eur_month !== undefined);
    const other = a.tips.filter((t) => !head(t) && (t.saving_eur_month === null || t.saving_eur_month === undefined));
    const rooms = a.rooms
      .map((r) => `<tr>
        <td><b>${esc(r.name)}</b></td>
        <td>${fmt(r.day_target, 1, "°C")}</td>
        <td>${fmt(r.night_target, 1, "°C")}</td>
        <td>${fmt(r.measured, 1, "°C")}</td>
        <td>${r.share !== null && r.share !== undefined ? fmt(r.share * 100, 0, "%") : "–"}</td>
        <td>${fmt(r.night_drop, 1, "°C")}${r.estimated_model ? ' <span class="muted small">(aanname)</span>' : ""}</td>
      </tr>`)
      .join("");
    return `
      ${top.map(tip).join("")}
      <div class="bar">
        <p class="muted small grow">Gebaseerd op de laatste ${basis.days} dagen: buiten gemiddeld ${fmt(basis.outdoor_mean, 1, "°C")},
          ongeveer ${fmt(basis.heating_gas_per_day, 1, "m³")} gas per dag voor verwarming (${euro((basis.heating_gas_per_day ?? 0) * basis.gas_price)}).
          Bedragen per maand gaan uit van weer zoals de afgelopen dagen; ‘Huidige instelling werkt’ toont wat de huidige nachtverlaging gemeten oplevert.
          ${basis.calibration !== 1 ? `Bijgesteld met de meting: factor ${fmt(basis.calibration, 2)}.` : ""}</p>
        <button class="btn text" data-action="advice-refresh">↻ Opnieuw berekenen</button>
      </div>
      <div class="card"><h3>Logboek: wat leverde elke instelling op?</h3>${this._renderPeriods(a.periods)}</div>
      ${money.length ? `<h3 class="section">Wat het kan opleveren</h3>${money.map(tip).join("")}` : ""}
      ${other.length ? `<h3 class="section">Opvallend</h3>${other.map(tip).join("")}` : ""}
      <div class="card">
        <h3>Per kamer – afgelopen ${basis.days} dagen</h3>
        <div class="table-wrap"><table class="ranking">
          <thead><tr><th>Kamer</th><th>Overdag ingesteld</th><th>'s Nachts ingesteld</th><th>Gemeten</th><th>Aandeel gas</th><th>Afkoeling per nacht</th></tr></thead>
          <tbody>${rooms}</tbody></table></div>
        <p class="muted small">Ingestelde en gemeten temperaturen komen uit de recorder (tijdgewogen gemiddelde). Het aandeel gas is geschat uit het aantal lussen
          en het verschil tussen binnen en buiten. De afkoeling per nacht volgt uit het geleerde model van de kamer; zonder model wordt een gemiddelde
          vloerverwarmingswoning aangenomen.</p>
      </div>
      <details class="card optional"><summary><h3>Hoe worden de tips berekend?</h3></summary>
        <p class="muted small">Een kamer verliest warmte in verhouding tot het verschil tussen binnen en buiten. Alles wat een kamer een tijd koeler houdt
          – overdag lager, of een nachtverlaging inclusief het weer opwarmen 's ochtends – bespaart dus het deel
          <i>graad-uren koeler ÷ (24 uur × verschil binnen/buiten)</i> van het gas voor die kamer. Hoe snel een kamer 's nachts afkoelt en weer opwarmt,
          leert HA Climate per kamer uit de metingen (tabblad Analyses → thermisch model). Zodra er ${3} of meer volledige dagen zijn gemeten sinds de
          startdatum, worden alle schattingen bijgesteld (per instelling wordt onthouden wat het model voorspelde, zodat ook na een wijziging verder geleerd wordt) met de verhouding tussen gemeten en voorspelde besparing; na twee weken telt de meting volledig.
          Zo wordt het advies steeds nauwkeuriger.</p>
      </details>`;
  }

  /* ----- Schedules ----- */
  /** Show, hide and grey out the schedule fields for the chosen schedule type. */
  _syncScheduleForm(form) {
    const get = (n) => form.querySelector(`[name="${n}"]`);
    const blocks = get("schedule_mode")?.value === "blocks";
    const mode = get("night_mode")?.value;
    form.querySelectorAll("[data-show]").forEach((f) => f.classList.toggle("hidden", f.dataset.show !== mode));
    form.querySelector('[data-sched="blocks"]')?.classList.toggle("hidden", !blocks);
    const night = form.querySelector('[data-sched="night"]');
    if (night) {
      night.classList.toggle("dimmed", blocks);
      if (this._admin) night.disabled = blocks;
    }
    form.querySelector("[data-night-note]")?.toggleAttribute("hidden", !blocks);
    const label = form.querySelector("[data-lowered-label]");
    if (label) label.textContent = blocks ? "Buiten de blokken" : "Nacht";
    if (this._admin) {
      const global = !blocks && get("use_global_night")?.checked;
      ["night_start", "night_end"].forEach((n) => get(n) && (get(n).disabled = !!global));
      // The general setback amount belongs to the general night window only.
      if (get("night_offset")) get("night_offset").disabled = !!global;
    }
  }

  _periodRow(p = { start: "17:00", end: "21:00" }, dis = "") {
    return `<div class="period-row">
      <input name="period_start" type="time" value="${esc(hhmm(p.start))}" ${dis} aria-label="Begin blok">
      <span class="muted">–</span>
      <input name="period_end" type="time" value="${esc(hhmm(p.end))}" ${dis} aria-label="Einde blok">
      ${dis ? "" : `<button class="btn text small danger" type="button" data-period-remove aria-label="Blok verwijderen">✕</button>`}
    </div>`;
  }

  _renderSchedules() {
    const s = this._state;
    const admin = this._admin;
    const dis = admin ? "" : "disabled";
    if (!s.rooms.length) return `<div class="card empty"><h2>Nog geen kamers</h2><p>Voeg eerst een kamer toe op het tabblad Kamers.</p></div>`;
    const cards = s.rooms
      .map((room) => {
        const c = room.config;
        const sch = room.schedule;
        const absolute = c.night_temp !== null && c.night_temp !== undefined;
        const global = c.use_global_night !== false;
        const periods = sch.periods || [];
        const blocks = periods.length > 0;
        return `
        <form class="card schedule" data-room="${room.id}">
          <div class="room-head"><div class="room-name">${esc(room.name)}</div>
            <span class="muted small">nu ${fmt(room.current_temperature, 1, "°C")}</span></div>
          <label class="field"><span>Schema</span>
            <select name="schedule_mode" ${dis}>
              <option value="night" ${blocks ? "" : "selected"}>Nachtverlaging (één venster per nacht)</option>
              <option value="blocks" ${blocks ? "selected" : ""}>Comfortblokken – daarbuiten verlaagd</option>
            </select></label>
          <div class="form-grid">
            <label class="field"><span>Dagtemperatuur</span>
              <input name="day_temp" type="number" step="0.5" min="5" max="30" value="${c.day_temp ?? ""}" placeholder="huidige stand" ${dis}></label>
            <label class="field"><span data-lowered-label>${blocks ? "Buiten de blokken" : "Nacht"}</span>
              <select name="night_mode" ${dis}>
                <option value="offset" ${absolute ? "" : "selected"}>Verlaging (relatief)</option>
                <option value="absolute" ${absolute ? "selected" : ""}>Vaste temperatuur</option>
              </select></label>
            <label class="field ${absolute ? "" : "hidden"}" data-show="absolute"><span>Verlaagde temperatuur</span>
              <input name="night_temp" type="number" step="0.5" min="5" max="30" value="${c.night_temp ?? ""}" ${dis}></label>
            <label class="field ${absolute ? "hidden" : ""}" data-show="offset"><span>Verlaging (°C)</span>
              <input name="night_offset" type="number" step="0.5" min="-10" max="0" value="${global ? sch.night_offset : c.night_offset ?? sch.night_offset}" ${dis}></label>
          </div>
          <div class="sched-section ${blocks ? "" : "hidden"}" data-sched="blocks">
            <p class="muted small">Alleen binnen deze blokken staat de kamer op dagtemperatuur; daarbuiten verlaagd zoals hierboven.
              Met optimum start begint het opwarmen vóór elk blok precies op tijd.</p>
            <div class="periods">${periods.map((p) => this._periodRow(p, dis)).join("")}</div>
            ${admin ? `<button class="btn text" type="button" data-period-add>+ Blok toevoegen</button>` : ""}
          </div>
          <fieldset class="sched-section" data-sched="night" ${dis}>
          <label class="check inline"><input type="checkbox" name="use_global_night" ${global ? "checked" : ""}>
            <span>Algemene tijden en verlaging gebruiken (${esc(hhmm(s.settings.night_start))} – ${esc(hhmm(s.settings.night_end))}, ${fmt(s.settings.night_offset, 1, "°C")})</span></label>
          <div class="form-grid">
            <label class="field"><span>Start nachtverlaging</span>
              <input name="night_start" type="time" value="${hhmm(global ? sch.night_start : c.night_start, sch.night_start)}"></label>
            <label class="field"><span>Herstel zonder optimum start</span>
              <input name="night_end" type="time" value="${hhmm(global ? sch.night_end : c.night_end, sch.night_end)}"></label>
            <label class="field"><span>Op temperatuur om</span>
              <input name="comfort_time" type="time" value="${hhmm(c.comfort_time, sch.comfort_time)}"></label>
          </div>
          <p class="muted small" data-night-note ${blocks ? "" : "hidden"}>Niet van toepassing: deze kamer volgt de comfortblokken.</p>
          </fieldset>
          <label class="check inline"><input type="checkbox" name="optimum_start" ${sch.optimum_start ? "checked" : ""} ${dis}>
            <span><b>Optimum start</b> – start de verwarming automatisch zo laat mogelijk, zodat de kamer op tijd op dagtemperatuur is${blocks ? " (vóór elk blok)" : ""}</span></label>
          <div class="info">
            <div><span class="muted">Geplande start</span><b>${sch.optimum_start ? timeOf(room.preheat.next_heating_start) : "–"}</b></div>
            <div><span class="muted">Opwarmtijd</span><b>${room.preheat.lead_minutes !== null ? `${Math.floor(room.preheat.lead_minutes / 60)}u ${String(room.preheat.lead_minutes % 60).padStart(2, "0")}m` : "–"}</b></div>
            <div><span class="muted">Methode</span><b>${room.preheat.method === "model" ? "Geleerd model" : "Veilige fallback"}</b></div>
            <div><span class="muted">Betrouwbaarheid</span>${this._confidenceBar(room.model.confidence)}</div>
          </div>
          ${admin ? `<div class="actions"><button class="btn" type="submit">Opslaan</button></div>` : ""}
        </form>`;
      })
      .join("");
    return `<p class="muted intro">Stel per kamer de dag- en nachttemperatuur in. Met <b>optimum start</b> berekent HA Climate met het geleerde opwarmmodel
      (huidige binnen- en buitentemperatuur) wanneer de verwarming moet starten. Zolang de betrouwbaarheid onder 50% ligt wordt een veilige,
      vroegere start gebruikt (0,5 °C per uur).</p><div class="grid wide">${cards}</div>`;
  }

  /* ----- Savings measurement ----- */
  _renderMeasurement() {
    const b = this._state.baseline;
    const e = this._state.energy || {};
    const admin = this._admin;
    const start = b.measurement_start;
    const today = (this._state.now || "").slice(0, 10);
    const days = start && today ? Math.max(0, daysBetween(start, today)) : 0;
    const price = e.gas_price;
    const status = days === 0
      ? "Vandaag gestart. Morgen staat hier de eerste volledige dag."
      : `${days} volledige dag${days === 1 ? "" : "en"} gemeten.`;
    return `<div class="card measure">
      <div class="measure-head">
        <div>
          <h3>Besparing meten sinds ${dateLabel(start)}</h3>
          <div class="muted small">${status}
            Vergeleken met hoe het huis vóór die datum stookte: ${fmt(b.m3_per_degree_day, 3)} m³ per graaddag
            (${b.days_used} dagen${b.first_day ? `, ${dateLabel(b.first_day)} – ${dateLabel(b.last_day)}` : ""}${b.reliable ? "" : ", nog onbetrouwbaar"}).</div>
        </div>
        ${admin ? `<div class="measure-start">
          <label class="field"><span>Startdatum</span><input name="savings_start_quick" type="date" value="${esc(b.savings_start || start || "")}" max="${esc(today)}"></label>
          <button class="btn text" data-action="savings-start">Wijzigen</button></div>` : ""}
      </div>
      <div class="tiles">
        <div class="tile"><div class="muted small">Totaal bespaard (${e.saved_total_days ?? 0} d)</div><div class="mid ${savedClass(e.saved_total)}">${fmt(e.saved_total, 2)}<small>m³</small></div>
          <div class="muted small">${e.saved_total === null || e.saved_total === undefined ? "nog geen volledige dag" : `${euro(e.saved_total * price)} · ${savedNote(e.saved_total)}`}</div></div>
        <div class="tile"><div class="muted small">Gisteren</div><div class="mid ${days >= 1 ? savedClass(e.saved_yesterday) : ""}">${days >= 1 ? fmt(e.saved_yesterday, 2) : "–"}<small>m³</small></div>
          <div class="muted small">${days >= 1 ? `${fmt(e.gas_yesterday, 2)} van ${fmt(e.expected_yesterday, 2)} m³ verwacht` : "vóór de start"}</div></div>
        <div class="tile"><div class="muted small">Vandaag tot nu (voorlopig)</div><div class="mid ${savedClass(e.saved_today)}">${fmt(e.saved_today, 2)}<small>m³</small></div>
          <div class="muted small">${fmt(e.gas_today, 2)} van ${fmt(e.expected_today, 2)} m³ verwacht</div></div>
      </div>
      ${this._renderFireplaceDays()}
      <h3 class="sub">Wat leverde elke instelling op?</h3>
      ${this._renderPeriods(this._state.periods)}
      <p class="muted small">Een enkele dag zegt weinig (zon, wind, tapwater, bezoek); kijk na een week naar het totaal. Een andere startdatum leert de vergelijking opnieuw uit de dagen daarvóór.</p>
    </div>`;
  }

  /* Every change of the night setting starts a new period; its measured result is kept. */
  _renderPeriods(periods) {
    if (!periods || !periods.length) return '<p class="muted small">Nog geen instellingen bijgehouden.</p>';
    const price = this._state.energy?.gas_price ?? 0;
    const rows = [...periods]
      .reverse()
      .map((p) => {
        const until = p.current ? "nu" : dateLabel(p.end);
        const pct = p.fraction === null || p.fraction === undefined ? null : p.fraction * 100;
        const early = p.days > 0 && p.days < 3;
        const color = pct === null || early ? "" : savedClass(pct, 0.5);
        const perMonth = p.per_day !== null && p.per_day !== undefined ? p.per_day * 30 * price : null;
        return `<tr class="${p.current ? "current" : ""}">
          <td>${dateLabel(p.start)} – ${until}</td>
          <td>${esc(p.text)}${p.current ? ' <span class="chip" style="--chip:var(--accent)">nu</span>' : ""}</td>
          <td class="num">${p.days}${p.fireplace_days ? `<br><small class="muted">+${p.fireplace_days} openhaard</small>` : ""}</td>
          <td class="num">${p.days ? `${fmt(p.actual, 1)} / ${fmt(p.expected, 1)} m³` : "–"}</td>
          <td class="num ${color}"><b>${pct === null ? "–" : `${pct > 0 ? "−" : "+"}${fmt(Math.abs(pct), 0)} %`}</b>${early ? '<br><small class="muted">voorlopig</small>' : ""}</td>
          <td class="num ${color}"><b>${perMonth === null ? "–" : euro(perMonth)}</b></td>
        </tr>`;
      })
      .join("");
    return `<div class="table-wrap"><table class="ranking periods">
      <thead><tr><th>Periode</th><th>Instelling</th><th class="num">Dagen</th><th class="num">Verbruikt / verwacht</th><th class="num">Verschil gas</th><th class="num">Bespaard per maand</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
      <p class="muted small">Elke wijziging van de nachtverlaging (tijden, verlaging, aan/uit, per kamer) start een nieuwe periode; een wijziging na 12:00 telt vanaf de
        volgende dag. Alleen volledige dagen tellen, dagen met de openhaard niet.
        <span class="good">Groen</span> = minder gas dan verwacht (bespaard), <span class="bad">rood</span> = meer gas dan verwacht; pas vanaf 3 dagen gekleurd.
        Of het opwarmen in de ochtend de nachtbesparing opeet, zie je per dag bij <i>Analyses → Per uur</i>.</p>`;
  }

  _renderFireplaceDays() {
    const fp = this._state.fireplace;
    const days = Object.entries(fp.recent || {});
    if (!fp.configured || !days.length) return "";
    return `<div class="fp-days muted small">🔥 Openhaard gedetecteerd: ${days
      .map(([d, m]) => `<span class="fp-day">${dateLabel(d)} ${m} min${this._admin ? ` <button class="btn text small" data-action="fireplace-clear" data-day="${d}">klopt niet</button>` : ""}</span>`)
      .join("")}
      <br>Dagen met ≥ 30 min openhaard tellen niet mee in de meting. Brandde hij niet (bijv. na het handmatig lager zetten)? Klik op <i>klopt niet</i>.</div>`;
  }

  /* ----- Settings ----- */
  _renderSettings() {
    const st = this._state.settings;
    const dis = this._admin ? "" : "disabled";
    const isTemp = (s) => s.entity_id.startsWith("sensor.") && s.attributes.device_class === "temperature";
    const temps = this._entities(isTemp);
    const gas = this._entities((s) => s.entity_id.startsWith("sensor.") && s.attributes.device_class === "gas");
    const prices = this._entities((s) => /^(sensor|input_number|number)\./.test(s.entity_id) && !["temperature", "gas"].includes(s.attributes.device_class));
    const climates = this._entities((s) => s.entity_id.startsWith("climate."));
    const perDay = st.gas_fixed_costs ? (st.gas_fixed_costs_unit === "day" ? st.gas_fixed_costs : st.gas_fixed_costs / 30.4375) : 0;
    const fireplace = !!(st.fireplace_climate || st.fireplace_temp_sensor);
    const advanced = st.degree_day_indoor_correction || Number(st.heating_limit) !== 18 || Number(st.baseline_days) !== 0;
    return `
      <form class="settings" id="settings-form">
        <section class="card">
          <h3>1 · Meters</h3>
          <div class="form-grid">
            <label class="field"><span>Buitentemperatuur</span><select name="outdoor_sensor" ${dis}>${this._options(temps, st.outdoor_sensor)}</select></label>
            <label class="field"><span>Gasmeter (m³)</span><select name="gas_sensor" ${dis}>${this._options(gas, st.gas_sensor)}</select></label>
          </div>
        </section>
        <section class="card">
          <h3>2 · Gasprijs</h3>
          <div class="form-grid">
            <label class="field"><span>Prijs per m³ (€)</span><input name="gas_price" type="number" step="0.0001" min="0" max="10" value="${st.gas_price ?? ""}" placeholder="${fmt(this._state.defaults.gas_price, 2)}" ${dis}></label>
            <label class="field"><span>Vaste kosten (€)</span><input name="gas_fixed_costs" type="number" step="0.01" min="0" max="500" value="${st.gas_fixed_costs ?? 0}" placeholder="0,00" ${dis}></label>
            <label class="field"><span>per</span><select name="gas_fixed_costs_unit" ${dis}>
              <option value="month" ${st.gas_fixed_costs_unit !== "day" ? "selected" : ""}>maand</option>
              <option value="day" ${st.gas_fixed_costs_unit === "day" ? "selected" : ""}>dag</option></select></label>
          </div>
          <p class="muted small">Vaste kosten (vastrecht, netbeheer) tellen mee in de gaskosten, niet in de besparing${perDay ? ` – ${euro(perDay)} per dag` : ""}.</p>
          <details class="optional" ${st.gas_price_entity ? "open" : ""}><summary>Dynamische prijs uit een entiteit</summary>
            <div class="form-grid"><label class="field"><span>Gasprijs-entiteit (gaat voor op de vaste prijs)</span><select name="gas_price_entity" ${dis}>${this._options(prices, st.gas_price_entity, true)}</select></label></div>
          </details>
        </section>
        <section class="card">
          <h3>3 · Nachtverlaging</h3>
          <div class="form-grid">
            <label class="field"><span>Van</span><input name="night_start" type="time" value="${hhmm(st.night_start)}" ${dis}></label>
            <label class="field"><span>Tot</span><input name="night_end" type="time" value="${hhmm(st.night_end)}" ${dis}></label>
            <label class="field"><span>Verlaging (°C)</span><input name="night_offset" type="number" step="0.5" min="-10" max="0" value="${st.night_offset}" ${dis}></label>
          </div>
          <p class="muted small">Geldt voor alle kamers. Per kamer afwijken of optimum start aanzetten doe je op het tabblad Schema's.</p>
        </section>
        <section class="card">
          <h3>4 · Besparing meten</h3>
          <div class="form-grid">
            <label class="field"><span>Meten vanaf</span><input name="savings_start" type="date" value="${esc(st.savings_start || "")}" ${dis}></label>
          </div>
          <p class="muted small">Kies de dag waarop je met besparen begon. Het verbruik vóór die dag is de vergelijking (referentie); vanaf die dag wordt de besparing geteld.</p>
        </section>
        <details class="card optional" ${fireplace ? "open" : ""}>
          <summary><h3>Openhaard (optioneel)</h3></summary>
          <div class="form-grid">
            <label class="field"><span>Thermostaat in de openhaard-ruimte</span><select name="fireplace_climate" ${dis}>${this._options(climates, st.fireplace_climate, true)}</select></label>
            <label class="field"><span>Of: losse temperatuursensor</span><select name="fireplace_temp_sensor" ${dis}>${this._options(temps, st.fireplace_temp_sensor, true)}</select></label>
            <label class="field"><span>Drempel (°C boven doel)</span><input name="fireplace_threshold" type="number" step="0.1" min="0.1" max="5" value="${st.fireplace_threshold}" ${dis}></label>
          </div>
          <p class="muted small">Dagen waarop de openhaard brandde tellen niet mee in de referentie.</p>
        </details>
        ${this._renderBoilerSettings(st, dis)}
        <details class="card optional" ${advanced ? "open" : ""}>
          <summary><h3>Geavanceerd: graaddagen</h3></summary>
          <div class="form-grid">
            <label class="field"><span>Stookgrens (°C)</span><input name="heating_limit" type="number" step="0.5" min="10" max="25" value="${st.heating_limit}" ${dis}></label>
            <label class="field"><span>Referentie: max. dagen terug (0 = alles)</span><input name="baseline_days" type="number" step="1" min="0" max="3650" value="${st.baseline_days}" ${dis}></label>
          </div>
          <label class="check inline"><input type="checkbox" name="degree_day_indoor_correction" ${st.degree_day_indoor_correction ? "checked" : ""} ${dis}>
            <span>Corrigeren voor de dagtemperatuur binnen</span></label>
          <div class="form-grid">
            <label class="field"><span>Dagtemperatuur in de referentieperiode (°C)</span><input name="degree_day_reference_temp" type="number" step="0.1" min="15" max="25" value="${st.degree_day_reference_temp ?? 20}" ${dis}></label>
          </div>
          <p class="muted small">Met de correctie stijgt het verwachte verbruik mee als je de kamers overdag warmer zet dan in de referentieperiode (en andersom).
            Nachtverlaging telt hierin niet mee en blijft dus als besparing zichtbaar.</p>
        </details>
        ${this._admin ? '<div class="save-bar"><button class="btn" type="submit">Opslaan</button></div>' : '<p class="muted">Alleen beheerders kunnen instellingen wijzigen.</p>'}
      </form>`;
  }

  _renderBoilerSettings(st, dis) {
    const binaries = this._entities((s) => s.entity_id.startsWith("binary_sensor."));
    const sensors = this._entities((s) => s.entity_id.startsWith("sensor."));
    const configured = BOILER_FIELDS.some((f) => st[f.key]);
    const field = (f) => `<label class="field"><span>${f.label}</span>
      <select name="${f.key}" ${dis}>${this._options(f.domain === "binary_sensor" ? binaries : sensors, st[f.key], true)}</select>
      <small class="muted">${esc(f.hint)}</small></label>`;
    return `<details class="card optional" ${configured ? "open" : ""}>
      <summary><h3>Ketel / OpenTherm (optioneel)</h3></summary>
      <p class="muted small">Voor branderstarts, pendelen, tapwater vs. verwarming en de aanvoertemperatuur op het tabblad Analyses.</p>
      <div class="form-grid">${BOILER_FIELDS.slice(0, 8).map(field).join("")}</div>
      <p class="muted small">Optioneel: tellers van de ketel zelf. Laat leeg om starts en branduren te berekenen vanuit de vlamstatus.</p>
      <div class="form-grid">${BOILER_FIELDS.slice(8).map(field).join("")}</div>
    </details>`;
  }

  /* ---------- Events ---------- */
  _bind() {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-tab]").forEach((el) =>
      el.addEventListener("click", async () => {
        this._tab = el.dataset.tab;
        this._saveTab();
        this._dirty = false;
        this._render();
        if (this._tab === "analytics") {
          this._history = null;
          await this._loadHistory();
          this._render();
        }
        if (this._tab === "tips") {
          await this._loadAdvice();
          this._render();
        }
      })
    );
    root.querySelectorAll("[data-action]").forEach((el) => {
      const action = el.dataset.action;
      const event = el.tagName === "INPUT" || el.tagName === "SELECT" ? "change" : "click";
      el.addEventListener(event, (ev) => this._onAction(action, el, ev));
    });
    root.querySelectorAll("form").forEach((form) => {
      form.addEventListener("input", () => (this._dirty = true));
      form.addEventListener("submit", (ev) => {
        ev.preventDefault();
        if (form.id === "settings-form") this._saveSettings(form);
        else this._saveSchedule(form);
      });
      const sync = () => this._syncScheduleForm(form);
      form.querySelector('[name="night_mode"]')?.addEventListener("change", sync);
      form.querySelector('[name="use_global_night"]')?.addEventListener("change", sync);
      const sched = form.querySelector('[name="schedule_mode"]');
      sched?.addEventListener("change", () => {
        const list = form.querySelector(".periods");
        if (sched.value === "blocks" && list && !list.children.length) {
          list.insertAdjacentHTML("beforeend", this._periodRow({ start: "06:30", end: "07:30" }) + this._periodRow({ start: "17:00", end: "21:00" }));
        }
        sync();
      });
      form.addEventListener("click", (ev) => {
        if (ev.target.closest("[data-period-add]")) {
          form.querySelector(".periods")?.insertAdjacentHTML("beforeend", this._periodRow());
          this._dirty = true;
        } else if (ev.target.closest("[data-period-remove]")) {
          ev.target.closest(".period-row")?.remove();
          this._dirty = true;
        }
      });
      if (sched) sync();
    });
    const filter = root.getElementById("climate-filter");
    filter?.addEventListener("input", () => {
      const q = filter.value.toLowerCase();
      root.querySelectorAll("#climate-list .check, #airco-list .check, #valve-list .check").forEach((el) => {
        el.style.display = el.dataset.name.includes(q) ? "" : "none";
      });
    });
  }

  _bindCharts() {
    this.shadowRoot.querySelectorAll(".chart svg").forEach((svg) => {
      const tip = svg.parentElement.querySelector(".tip");
      svg.querySelectorAll("[data-tip]").forEach((rect) => {
        rect.addEventListener("mousemove", (ev) => {
          tip.innerHTML = rect.dataset.tip;
          tip.style.display = "block";
          const box = svg.parentElement.getBoundingClientRect();
          let x = ev.clientX - box.left + 12;
          if (x + 180 > box.width) x = ev.clientX - box.left - 190;
          tip.style.left = `${x}px`;
          tip.style.top = `${ev.clientY - box.top - 10}px`;
        });
        rect.addEventListener("mouseleave", () => (tip.style.display = "none"));
      });
    });
  }

  async _onAction(action, el, ev) {
    const s = this._state;
    switch (action) {
      case "refresh":
        await this._refresh();
        break;
      case "master":
        await this._call({ type: "ha_climate/master/set", enabled: el.checked }, el.checked ? "Nachtverlaging ingeschakeld" : "Nachtverlaging uitgeschakeld");
        break;
      case "room-enable":
        await this._call({ type: "ha_climate/room/enable", room_id: el.dataset.room, enabled: el.checked });
        break;
      case "add-room":
        this._dialog = { room: null };
        this._render();
        this.shadowRoot.getElementById("room-name")?.focus();
        break;
      case "edit-room":
        this._dialog = { room: s.rooms.find((r) => r.id === el.dataset.room) };
        this._render();
        break;
      case "close-dialog-bg":
        if (ev.target !== el) return;
      // falls through
      case "close-dialog":
        this._dialog = null;
        this._render();
        break;
      case "save-room":
        await this._saveRoom();
        break;
      case "delete-room": {
        const room = s.rooms.find((r) => r.id === el.dataset.room);
        if (room && confirm(`Kamer "${room.name}" verwijderen? Verlaagde lussen worden hersteld.`)) {
          await this._call({ type: "ha_climate/room/delete", room_id: room.id }, "Kamer verwijderd");
        }
        break;
      }
      case "hourly-day":
        this._hourlyDay = el.dataset.day;
        this._hourly = null;
        this._render();
        await this._loadHourly();
        this._render();
        break;
      case "days":
        this._days = Number(el.dataset.days);
        this._history = null;
        this._render();
        await this._loadHistory();
        this._render();
        break;
      case "unit":
        this._chartUnit = el.dataset.unit;
        this.shadowRoot.querySelectorAll('[data-action="unit"]').forEach((b) => b.classList.toggle("active", b === el));
        this._renderCharts();
        break;
      case "room-temp":
        this._stepRoomTemp(el.dataset.room, Number(el.dataset.delta));
        break;
      case "airco-temp":
        this._stepAircoTemp(el.dataset.room, Number(el.dataset.delta));
        break;
      case "airco-mode": {
        const labels = { off: "Airco uit", cool: "Airco koelt", boost: "Airco: snel bijverwarmen" };
        await this._call({ type: "ha_climate/airco", room_id: el.dataset.room, mode: el.dataset.mode }, labels[el.dataset.mode]);
        break;
      }
      case "savings-start": {
        const start = this.shadowRoot.querySelector('[name="savings_start_quick"]')?.value;
        if (!start) {
          this._toast("Kies een startdatum", true);
          break;
        }
        await this._call({ type: "ha_climate/settings/save", settings: { savings_start: start } }, `Besparing gemeten vanaf ${dateLabel(start)}`);
        await this._loadHistory();
        this._render();
        break;
      }
      case "edit-temp":
        this._editTemp(el, el.dataset.kind, el.dataset.room);
        break;
      case "fireplace-clear":
        if (confirm(`Openhaard-minuten van ${dateLabel(el.dataset.day)} wissen?`)) {
          await this._call({ type: "ha_climate/fireplace/clear", day: el.dataset.day }, "Openhaard-dag gewist");
          if (this._tab === "analytics") {
            await this._loadHistory();
            this._render();
          }
        }
        break;
      case "apply-tip": {
        const tip = this._advice?.tips.find((t) => t.id === el.dataset.tip);
        const act = tip?.action;
        if (!act) break;
        const what = act.master === false ? "nachtverlaging uit" : `${fmt(act.night_offset, 1, "°C")}, ${act.night_start}–${act.night_end}`;
        if (!confirm(`Nachtverlaging terugzetten naar: ${what}?`)) break;
        if (act.master !== false) {
          await this._call({ type: "ha_climate/settings/save", settings: { night_start: act.night_start, night_end: act.night_end, night_offset: act.night_offset } });
        }
        if (act.master !== undefined && act.master !== this._state.master) {
          await this._call({ type: "ha_climate/master/set", enabled: act.master });
        }
        this._toast("Instelling teruggezet; dit start een nieuwe meetperiode");
        await this._loadAdvice(true);
        this._render();
        break;
      }
      case "advice-refresh":
        this._advice = null;
        this._render();
        await this._loadAdvice(true);
        this._render();
        break;
      case "export":
        await this._exportCsv();
        break;
      case "room-select":
        this._room = el.value;
        this._render();
        break;
      case "reset-model": {
        const room = s.rooms.find((r) => r.id === el.dataset.room);
        if (room && confirm(`Geleerd model van "${room.name}" wissen?`)) {
          await this._call({ type: "ha_climate/model/reset", room_id: room.id }, "Model gewist");
        }
        break;
      }
      case "recalculate":
        await this._call(
          { type: "ha_climate/baseline/recalculate" },
          "Baseline en kamermodellen herberekend uit de historie"
        );
        break;
      default:
        break;
    }
  }

  /* Click on a setpoint: type a value (Enter / leaving the field saves, Esc cancels). */
  _editTemp(button, kind, roomId) {
    const room = this._state.rooms.find((r) => r.id === roomId);
    if (!room || !this._admin) return;
    const airco = kind === "airco";
    const current = airco
      ? this._pendingAirco[roomId] ?? room.aircos.find((a) => a.available)?.target_temperature
      : this._pendingTemp[roomId] ?? room.target_temperature;
    const [min, max] = airco ? [10, 32] : [5, 30];
    const input = document.createElement("input");
    Object.assign(input, { type: "number", step: "0.5", min, max, value: current ?? "", className: "sp-input" });
    input.setAttribute("inputmode", "decimal");
    input.setAttribute("aria-label", "Doeltemperatuur");
    button.replaceWith(input);
    input.focus();
    input.select();
    this._editing = true;
    let done = false;
    const finish = (save) => {
      if (done) return;
      done = true;
      this._editing = false;
      const value = numOrNull(input.value);
      if (!save || value === null || value === current) {
        this._render();
        return;
      }
      const next = Math.min(max, Math.max(min, Math.round(value * 10) / 10));
      if (airco) {
        this._pendingAirco[roomId] = next;
        this._render();
        this._sendAircoTemp(roomId, next, 0);
      } else {
        this._pendingTemp[roomId] = next;
        this._render();
        this._sendRoomTemp(roomId, next, 0);
      }
    };
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") finish(true);
      else if (ev.key === "Escape") finish(false);
    });
    input.addEventListener("blur", () => finish(true));
  }

  /* Optimistic setpoint changes: update the number immediately, send after a short pause. */
  _stepRoomTemp(roomId, delta) {
    const room = this._state.rooms.find((r) => r.id === roomId);
    if (!room) return;
    const base = this._pendingTemp[roomId] ?? room.target_temperature ?? room.comfort_temperature ?? 20;
    const next = Math.min(30, Math.max(5, Math.round((base + delta) * 2) / 2));
    this._pendingTemp[roomId] = next;
    this._sendRoomTemp(roomId, next);
  }

  _sendRoomTemp(roomId, next, delay = 700) {
    const room = this._state.rooms.find((r) => r.id === roomId);
    const box = this.shadowRoot.querySelector(`[data-room-setpoint="${roomId}"]`);
    if (box) {
      box.querySelector(".sp-value").textContent = fmt(next, 1);
      box.querySelector(".sp-label").textContent = "instellen…";
      box.classList.add("pending");
    }
    clearTimeout(this._tempTimers[roomId]);
    this._tempTimers[roomId] = setTimeout(async () => {
      try {
        const res = await this._ws({ type: "ha_climate/room/set_temperature", room_id: roomId, temperature: next });
        this._toast(`${room.name}: ${fmt(next, 1)} °C op ${res.entities.length} lus${res.entities.length === 1 ? "" : "sen"}`);
      } catch (err) {
        this._toast(err?.message || "Instellen mislukt", true);
      }
      delete this._pendingTemp[roomId];
      await this._refresh();
    }, delay);
  }

  _stepAircoTemp(roomId, delta) {
    const room = this._state.rooms.find((r) => r.id === roomId);
    const airco = room?.aircos.find((a) => a.available);
    if (!airco) return;
    const base = this._pendingAirco[roomId] ?? airco.target_temperature ?? 21;
    const next = Math.min(32, Math.max(10, Math.round((base + delta) * 2) / 2));
    this._pendingAirco[roomId] = next;
    this._render();
    this._sendAircoTemp(roomId, next);
  }

  _sendAircoTemp(roomId, next, delay = 700) {
    const room = this._state.rooms.find((r) => r.id === roomId);
    clearTimeout(this._tempTimers[`a-${roomId}`]);
    this._tempTimers[`a-${roomId}`] = setTimeout(async () => {
      try {
        await this._ws({ type: "ha_climate/airco", room_id: roomId, temperature: next });
        this._toast(`Airco ${room.name}: ${fmt(next, 1)} °C`);
      } catch (err) {
        this._toast(err?.message || "Instellen mislukt", true);
      }
      delete this._pendingAirco[roomId];
      await this._refresh();
    }, delay);
  }

  async _exportCsv() {
    let result;
    try {
      result = await this._ws({ type: "ha_climate/export" });
    } catch (err) {
      this._toast(err?.message || "Export mislukt", true);
      return;
    }
    const num = (v, d) => (v === null || v === undefined || Number.isNaN(v) ? "" : Number(v).toFixed(d));
    const cell = (v) => {
      const text = String(v ?? "");
      return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
    };
    const header = [
      "datum", "buiten_temp_gem_c", "binnen_temp_gem_c", "binnen_doel_gem_c", "binnen_comfort_gem_c", "stookgrens_c", "graaddagen",
      "gas_werkelijk_m3", "gas_verwacht_m3", "besparing_m3", "besparing_eur", "variabele_kosten_eur",
      "vaste_kosten_eur", "totale_kosten_eur", "openhaard_minuten", "nachtverlaging", "gedeeltelijke_dag", "gebeurtenissen",
    ];
    const boiler = result.days.some((r) => r.boiler);
    if (boiler) {
      header.push(
        "ketel_starts", "ketel_branduren", "ketel_gem_looptijd_min", "ketel_korte_runs",
        "ketel_tapwater_min", "ketel_verwarming_min", "ketel_tapwater_pct", "ketel_aanvoer_gem_c", "ketel_modulatie_gem_pct"
      );
    }
    const lines = [header.join(",")];
    for (const r of result.days) {
      const k = r.boiler || {};
      const extra = boiler
        ? [
            k.starts ?? "", num(k.burn_hours, 2), num(k.avg_run_minutes, 1), k.short_runs ?? "",
            num(k.dhw_minutes, 0), num(k.heat_minutes, 0), num(k.dhw_share === null || k.dhw_share === undefined ? null : k.dhw_share * 100, 1),
            num(k.flow_avg, 1), num(k.modulation_avg, 1),
          ]
        : [];
      lines.push([
        r.date, num(r.mean_temperature, 2), num(r.indoor_temperature, 2), num(r.indoor_target, 2), num(r.indoor_comfort, 2), num(r.heating_limit, 2),
        num(r.degree_days, 2), num(r.gas, 3), num(r.expected, 3), num(r.saved, 3), num(r.saved_eur, 2),
        num(r.cost_variable, 2), num(r.cost_fixed, 2), num(r.cost, 2), r.fireplace_minutes ?? 0,
        r.setback ? "ja" : "nee", r.partial ? "ja" : "nee",
        summarizeEvents(r.events).map((e) => `${timeOf(e.time)} ${e.text}`).join(" | "),
        ...extra,
      ].map(cell).join(","));
    }
    const blob = new Blob(["\ufeff" + lines.join("\r\n") + "\r\n"], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `ha-climate-${new Date().toISOString().slice(0, 10)}.csv`;
    this.shadowRoot.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    this._toast(`${result.days.length} dagen geëxporteerd`);
  }

  async _saveRoom() {
    const root = this.shadowRoot;
    const name = root.getElementById("room-name").value.trim();
    const climates = [...root.querySelectorAll('#climate-list input[name="climate"]:checked')].map((i) => i.value);
    const aircos = [...root.querySelectorAll('#airco-list input[name="airco"]:checked')].map((i) => i.value);
    if (aircos.some((a) => climates.includes(a))) {
      this._toast("Een entiteit kan niet tegelijk lus en airco zijn", true);
      return;
    }
    const valves = [...root.querySelectorAll('#valve-list input[name="valve"]:checked')].map((i) => i.value);
    const room = { name, climates, aircos, valves };
    if (this._dialog.room?.id) room.id = this._dialog.room.id;
    const result = await this._call({ type: "ha_climate/room/save", room }, room.id ? "Kamer opgeslagen" : "Kamer toegevoegd");
    if (result) {
      this._dialog = null;
      this._render();
    }
  }

  async _saveSchedule(form) {
    const f = new FormData(form);
    const get = (n) => form.querySelector(`[name="${n}"]`);
    const absolute = f.get("night_mode") === "absolute";
    const blocks = get("schedule_mode")?.value === "blocks";
    // Comfort blocks use the room's own setback amount, not the general night window.
    const global = !blocks && get("use_global_night").checked;
    const room = {
      id: form.dataset.room,
      day_temp: numOrNull(get("day_temp").value),
      night_temp: absolute ? numOrNull(get("night_temp").value) : null,
      comfort_time: get("comfort_time").value,
      optimum_start: get("optimum_start").checked,
      use_global_night: global,
    };
    if (absolute && room.night_temp === null) {
      this._toast("Vul een nachttemperatuur in", true);
      return;
    }
    room.periods = blocks
      ? [...form.querySelectorAll(".period-row")].map((r) => ({
          start: r.querySelector('[name="period_start"]').value,
          end: r.querySelector('[name="period_end"]').value,
        }))
      : [];
    if (blocks && !room.periods.length) {
      this._toast("Voeg minimaal één comfortblok toe", true);
      return;
    }
    if (room.periods.some((p) => !p.start || !p.end || p.start === p.end)) {
      this._toast("Elk blok heeft een begin- en eindtijd nodig die verschillen", true);
      return;
    }
    if (!global) {
      room.night_start = get("night_start").value;
      room.night_end = get("night_end").value;
      if (!absolute) room.night_offset = numOrNull(get("night_offset").value) ?? -2;
    }
    await this._call({ type: "ha_climate/room/save", room }, "Schema opgeslagen");
  }

  async _saveSettings(form) {
    const get = (n) => form.querySelector(`[name="${n}"]`).value;
    const settings = {
      outdoor_sensor: get("outdoor_sensor"),
      gas_sensor: get("gas_sensor"),
      heating_limit: numOrNull(get("heating_limit")),
      baseline_days: numOrNull(get("baseline_days")),
      gas_price: numOrNull(get("gas_price")),
      gas_price_entity: get("gas_price_entity") || null,
      gas_fixed_costs: numOrNull(get("gas_fixed_costs")) ?? 0,
      gas_fixed_costs_unit: get("gas_fixed_costs_unit"),
      savings_start: get("savings_start") || null,
      degree_day_indoor_correction: form.querySelector('[name="degree_day_indoor_correction"]').checked,
      degree_day_reference_temp: numOrNull(get("degree_day_reference_temp")),
      night_start: get("night_start"),
      night_end: get("night_end"),
      night_offset: numOrNull(get("night_offset")),
      fireplace_climate: get("fireplace_climate") || null,
      fireplace_temp_sensor: get("fireplace_temp_sensor") || null,
      fireplace_threshold: numOrNull(get("fireplace_threshold")),
    };
    for (const f of BOILER_FIELDS) settings[f.key] = get(f.key) || null;
    for (const key of ["heating_limit", "baseline_days", "night_offset", "fireplace_threshold", "degree_day_reference_temp"]) {
      if (settings[key] === null) delete settings[key];
    }
    await this._call({ type: "ha_climate/settings/save", settings }, "Instellingen opgeslagen");
  }

  _toast(message, error = false) {
    const el = this.shadowRoot.getElementById("toast");
    if (!el) return;
    el.textContent = message;
    el.className = `toast show ${error ? "error" : ""}`;
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => (el.className = "toast"), 3500);
  }
}

/* ---------------------------------------------------------------------------
 * SVG charts
 * ------------------------------------------------------------------------- */
function niceMax(value) {
  if (!value || value <= 0) return 1;
  const exp = Math.pow(10, Math.floor(Math.log10(value)));
  const f = value / exp;
  const nice = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10;
  return nice * exp;
}

function chart({ width, labels, series, marks = [], shade = [], events = [], shadeLabel = "nachtverlaging", labelWidth = 64, start = -1 }) {
  const height = 260;
  const pad = { top: events.some((e) => e && e.length) || start >= 0 ? 22 : 16, right: series.some((s) => s.axis === "right") ? 44 : 14, bottom: 34, left: 48 };
  const w = Math.max(280, width);
  const innerW = w - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const n = labels.length;
  const step = innerW / Math.max(1, n);
  const axisRange = (axis) => {
    const vals = series.filter((s) => s.axis === axis && s.type !== "tooltip").flatMap((s) => s.values).filter((v) => v !== null && v !== undefined);
    if (!vals.length) return null;
    const min = Math.min(0, ...vals);
    const max = Math.max(0, ...vals);
    const top = niceMax(max);
    const bottom = min < 0 ? -niceMax(-min) : 0;
    return { min: bottom, max: top === bottom ? bottom + 1 : top };
  };
  const ranges = { left: axisRange("left"), right: axisRange("right") };
  const pad2 = series.some((s) => s.axis === "right" && s.type !== "tooltip");
  if (!pad2) pad.right = 14;
  const y = (axis, v) => {
    const r = ranges[axis];
    return pad.top + innerH - ((v - r.min) / (r.max - r.min)) * innerH;
  };
  const x = (i) => pad.left + step * i + step / 2;
  let svg = `<svg viewBox="0 0 ${w} ${height}" width="100%" height="${height}" role="img">`;
  // shading (e.g. night setback days)
  shade.forEach((on, i) => {
    if (on) svg += `<rect x="${pad.left + step * i}" y="${pad.top}" width="${step}" height="${innerH}" class="shade"/>`;
  });
  // grid + axes
  for (const axis of ["left", "right"]) {
    const r = ranges[axis];
    if (!r) continue;
    for (let t = 0; t <= 4; t += 1) {
      const v = r.min + ((r.max - r.min) * t) / 4;
      const yy = y(axis, v);
      if (axis === "left") svg += `<line x1="${pad.left}" x2="${w - pad.right}" y1="${yy}" y2="${yy}" class="grid"/>`;
      const label = fmt(v, Math.abs(r.max - r.min) < 5 ? 1 : 0);
      svg += axis === "left"
        ? `<text x="${pad.left - 6}" y="${yy + 4}" class="axis" text-anchor="end">${label}</text>`
        : `<text x="${w - pad.right + 6}" y="${yy + 4}" class="axis">${label}</text>`;
    }
  }
  if (ranges.left && ranges.left.min < 0) {
    svg += `<line x1="${pad.left}" x2="${w - pad.right}" y1="${y("left", 0)}" y2="${y("left", 0)}" class="zero"/>`;
  }
  // x labels: evenly spaced, the last one always shown (right aligned) and
  // any label that would collide with it is dropped.
  const labelW = labelWidth;
  const every = Math.max(1, Math.ceil(labelW / step));
  const lastX = x(n - 1);
  const lastWidth = Math.max(labelW, String(labels[n - 1] || "").length * 6.5);
  labels.forEach((label, i) => {
    const isLast = i === n - 1;
    const regular = i % every === 0 && !isLast && x(i) + labelW / 2 < lastX - lastWidth - 4;
    if (regular) {
      svg += `<text x="${x(i)}" y="${height - 12}" class="axis" text-anchor="middle">${esc(label)}</text>`;
    } else if (isLast) {
      svg += `<text x="${Math.min(w - pad.right, lastX + step / 2)}" y="${height - 12}" class="axis" text-anchor="end">${esc(label)}</text>`;
    }
    if (marks[i]) svg += `<text x="${x(i)}" y="${pad.top + 10}" text-anchor="middle" font-size="10">${marks[i]}</text>`;
  });
  // start of the savings measurement: everything left of it is the reference
  if (start > 0) {
    const sx = pad.left + step * start;
    svg += `<rect x="${pad.left}" y="${pad.top}" width="${sx - pad.left}" height="${innerH}" class="reference"/>`;
    svg += `<line x1="${sx}" x2="${sx}" y1="${pad.top - 6}" y2="${pad.top + innerH}" class="start-line"/>`;
    if (sx > w - pad.right - 70) {
      svg += `<text x="${sx - 4}" y="${pad.top - 8}" class="start-label" text-anchor="end">referentie ◂ ▸ meting</text>`;
    } else {
      svg += `<text x="${sx - 4}" y="${pad.top - 8}" class="start-label" text-anchor="end">referentie</text>`;
      svg += `<text x="${sx + 4}" y="${pad.top - 8}" class="start-label">meting ▸</text>`;
    }
  }
  // change markers (night setback on/off, changed settings): one small flag per day
  events.forEach((list, i) => {
    if (!list || !list.length) return;
    const ex = x(i);
    svg += `<line x1="${ex}" x2="${ex}" y1="${pad.top + 6}" y2="${pad.top + innerH}" class="event-line"/>`;
    svg += `<path class="event-flag" d="M${ex},${pad.top + innerH} V${pad.top + innerH - 10} h6 l-2,3 l2,3 h-6"/>`;
  });
  // series
  const bars = series.filter((s) => s.type === "bar");
  const barW = Math.max(1, (step * 0.7) / Math.max(1, bars.length));
  bars.forEach((s, bi) => {
    s.values.forEach((v, i) => {
      if (v === null || v === undefined) return;
      const y0 = y(s.axis, 0);
      const yv = y(s.axis, v);
      const bx = x(i) - (barW * bars.length) / 2 + barW * bi;
      svg += `<rect x="${bx}" y="${Math.min(y0, yv)}" width="${barW}" height="${Math.max(0.5, Math.abs(y0 - yv))}" rx="1.5" fill="${s.color}" opacity="${s.opacity ?? 0.85}"/>`;
    });
  });
  series
    .filter((s) => s.type === "line" || s.type === "area")
    .forEach((s) => {
      const pts = s.values.map((v, i) => (v === null || v === undefined ? null : [x(i), y(s.axis, v)]));
      const segments = [];
      let cur = [];
      pts.forEach((p) => {
        if (p) cur.push(p);
        else if (cur.length) {
          segments.push(cur);
          cur = [];
        }
      });
      if (cur.length) segments.push(cur);
      for (const seg of segments) {
        const d = seg.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("");
        if (s.type === "area") {
          const base = y(s.axis, Math.max(0, ranges[s.axis].min));
          svg += `<path d="${d}L${seg[seg.length - 1][0].toFixed(1)},${base}L${seg[0][0].toFixed(1)},${base}Z" fill="${s.color}" opacity="0.18"/>`;
        }
        svg += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="2.2" ${s.dashed ? 'stroke-dasharray="5 4"' : ""} stroke-linejoin="round"/>`;
        if (seg.length < 40) seg.forEach((p) => (svg += `<circle cx="${p[0]}" cy="${p[1]}" r="2.6" fill="${s.color}"/>`));
      }
    });
  // hover targets
  labels.forEach((label, i) => {
    const lines = series
      .filter((s) => s.values[i] !== null && s.values[i] !== undefined)
      .map((s) => `<div><i style="background:${s.color}"></i>${esc(s.name)}: <b>${s.unit === "€" ? euro(s.values[i]) : fmt(s.values[i], s.digits ?? 1, s.unit)}</b></div>`)
      .join("");
    const evs = (events[i] || [])
      .map((e) => `<div class="tip-event">⚑ ${timeOf(e.time)} ${esc(e.text)}</div>`)
      .join("");
    const tip = `<div class="tip-title">${esc(label)}${marks[i] ? " " + marks[i] : ""}${shade[i] ? ` · ${shadeLabel}` : ""}</div>${lines}${evs}`;
    svg += `<rect x="${pad.left + step * i}" y="${pad.top}" width="${step}" height="${innerH}" fill="transparent" data-tip="${esc(tip)}"/>`;
  });
  svg += "</svg>";
  return `${svg}<div class="tip"></div>`;
}

function roomChart(rooms, width) {
  if (!rooms.length) return "";
  const w = Math.max(280, width);
  const rowH = 46;
  const labelW = Math.min(160, w * 0.3);
  const height = rooms.length * rowH + 30;
  const rates = rooms.flatMap((r) => [r.model.cooling_rate, r.model.heating_rate]).filter((v) => v !== null && v !== undefined);
  const max = niceMax(Math.max(0.5, ...rates.map(Math.abs)));
  const innerW = w - labelW - 70;
  const sx = (v) => labelW + (Math.max(0, v) / max) * innerW;
  let svg = `<svg viewBox="0 0 ${w} ${height}" width="100%" height="${height}">`;
  for (let t = 0; t <= 4; t += 1) {
    const v = (max * t) / 4;
    svg += `<line x1="${sx(v)}" x2="${sx(v)}" y1="4" y2="${height - 22}" class="grid"/><text x="${sx(v)}" y="${height - 6}" class="axis" text-anchor="middle">${fmt(v, 1)}</text>`;
  }
  rooms.forEach((r, i) => {
    const y0 = i * rowH + 8;
    svg += `<text x="${labelW - 8}" y="${y0 + 18}" class="label" text-anchor="end">${esc(r.name.length > 22 ? r.name.slice(0, 21) + "…" : r.name)}</text>`;
    const bars = [
      ["Afkoelen", r.model.cooling_rate, COLORS.cooling],
      ["Opwarmen", r.model.heating_rate, COLORS.heating],
    ];
    bars.forEach(([name, v, color], bi) => {
      const yy = y0 + bi * 15;
      if (v === null || v === undefined) {
        svg += `<text x="${labelW + 4}" y="${yy + 11}" class="axis">${name}: nog geen data</text>`;
        return;
      }
      const tip = `<div class="tip-title">${esc(r.name)}</div><div><i style="background:${color}"></i>${name}: <b>${fmt(v, 2, "°C/u")}</b></div><div>Betrouwbaarheid: <b>${fmt(r.model.confidence, 0)}%</b></div>`;
      svg += `<rect x="${labelW}" y="${yy}" width="${Math.max(1, sx(v) - labelW)}" height="12" rx="3" fill="${color}" opacity="${0.35 + 0.65 * (r.model.confidence / 100)}" data-tip="${esc(tip)}"/>`;
      svg += `<text x="${sx(v) + 6}" y="${yy + 10}" class="axis">${fmt(v, 2)}</text>`;
    });
  });
  svg += "</svg>";
  return `${svg}<div class="tip"></div><div class="legend"><span><i style="background:${COLORS.cooling}"></i>Afkoelsnelheid (°C/u)</span><span><i style="background:${COLORS.heating}"></i>Opwarmsnelheid (°C/u)</span><span class="muted">dekking = betrouwbaarheid</span></div>`;
}

/* ---------------------------------------------------------------------------
 * Styles (Home Assistant theme variables)
 * ------------------------------------------------------------------------- */
const STYLE = `
  :host {
    display: block;
    min-height: 100vh;
    background: var(--primary-background-color, #fafafa);
    color: var(--primary-text-color, #212121);
    font-family: var(--paper-font-body1_-_font-family, Roboto, "Noto Sans", sans-serif);
    --card: var(--ha-card-background, var(--card-background-color, #fff));
    --radius: var(--ha-card-border-radius, 12px);
    --border: var(--divider-color, rgba(0,0,0,.12));
    --muted: var(--secondary-text-color, #727272);
    --accent: var(--primary-color, #03a9f4);
  }
  * { box-sizing: border-box; }
  .toolbar {
    display: flex; align-items: center; height: var(--header-height, 56px); padding: 0 12px;
    background: var(--app-header-background-color, var(--primary-color));
    color: var(--app-header-text-color, var(--text-primary-color, #fff));
    position: sticky; top: 0; z-index: 3;
  }
  .toolbar .title { font-size: 20px; margin-left: 12px; font-weight: 400; }
  .spacer { flex: 1; }
  .icon-btn { background: none; border: 0; color: inherit; cursor: pointer; padding: 8px; border-radius: 50%; }
  .icon-btn:hover { background: rgba(255,255,255,.12); }
  .icon-btn svg { width: 24px; height: 24px; fill: currentColor; display: block; }
  .tabs {
    display: flex; gap: 4px; padding: 0 12px; overflow-x: auto;
    background: var(--app-header-background-color, var(--primary-color));
    position: sticky; top: var(--header-height, 56px); z-index: 2;
  }
  .tab {
    display: flex; align-items: center; gap: 8px; padding: 12px 16px; background: none; border: 0;
    color: var(--app-header-text-color, #fff); opacity: .75; cursor: pointer; font-size: 14px;
    border-bottom: 3px solid transparent; white-space: nowrap; font-family: inherit;
  }
  .tab svg { width: 20px; height: 20px; fill: currentColor; }
  .tab.active { opacity: 1; border-bottom-color: var(--app-header-text-color, #fff); font-weight: 500; }
  .content { padding: 16px; max-width: 1400px; margin: 0 auto; }
  .card {
    background: var(--card); border-radius: var(--radius); padding: 16px; margin-bottom: 16px;
    box-shadow: var(--ha-card-box-shadow, 0 2px 2px rgba(0,0,0,.08)); border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--border));
  }
  .card h3 { margin: 0 0 12px; font-weight: 500; font-size: 16px; }
  .card h3 + .form-grid { margin-top: 0; }
  .settings h3 { margin-top: 20px; }
  .settings h3:first-child { margin-top: 0; }
  .card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .empty { text-align: center; padding: 40px 16px; }
  .empty h2 { font-weight: 400; }
  .grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); }
  .grid.wide { grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); }
  .grid .card { margin: 0; }
  .summary { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); margin-bottom: 16px; }
  .summary .card { margin: 0; }
  .stat .big { margin-top: 4px; }
  .big { font-size: 32px; font-weight: 300; line-height: 1.1; }
  .mid { font-size: 22px; font-weight: 300; line-height: 1.2; }
  .big small, .mid small { font-size: 14px; margin-left: 2px; color: var(--muted); }
  .muted { color: var(--muted); }
  .small { font-size: 12px; }
  .intro { margin: 0 0 16px; line-height: 1.5; }
  .bar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
  .room-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 12px; }
  .room-name { font-size: 18px; font-weight: 500; margin-bottom: 6px; }
  .chip {
    display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 12px; font-size: 12px;
    background: color-mix(in srgb, var(--chip) 18%, transparent); color: var(--chip); font-weight: 500;
  }
  .chip::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--chip); }
  .temps { display: grid; grid-template-columns: 1fr 1.4fr 0.8fr; gap: 8px; margin-bottom: 12px; align-items: end; }
  .temps .muted { font-size: 12px; }
  .row { display: flex; justify-content: space-between; gap: 8px; padding: 6px 0; border-top: 1px solid var(--border); }
  details { border-top: 1px solid var(--border); padding-top: 6px; font-size: 13px; }
  summary { cursor: pointer; color: var(--muted); }
  .loops { list-style: none; padding: 0; margin: 6px 0 0; }
  .loops li { display: flex; justify-content: space-between; gap: 8px; padding: 3px 0; }
  .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-left: 4px; }
  .dot.heat { background: #ff7043; }
  .actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
  .btn {
    background: var(--accent); color: var(--text-primary-color, #fff); border: 0; border-radius: 18px; padding: 8px 18px;
    font-size: 14px; font-weight: 500; cursor: pointer; font-family: inherit;
  }
  .btn:hover { filter: brightness(1.08); }
  .btn.text { background: none; color: var(--accent); padding: 8px 12px; }
  .btn.text:hover { background: color-mix(in srgb, var(--accent) 10%, transparent); }
  .btn.danger { color: var(--error-color, #db4437); }
  .btn.small { padding: 4px 8px; font-size: 12px; }
  .switch { position: relative; display: inline-block; width: 40px; height: 22px; flex: none; }
  .switch input { opacity: 0; width: 0; height: 0; }
  .slider { position: absolute; inset: 0; background: var(--switch-unchecked-track-color, #9e9e9e); border-radius: 22px; transition: .2s; cursor: pointer; opacity: .6; }
  .slider::before { content: ""; position: absolute; width: 18px; height: 18px; left: 2px; top: 2px; background: var(--switch-unchecked-button-color, #fafafa); border-radius: 50%; transition: .2s; box-shadow: 0 1px 3px rgba(0,0,0,.3); }
  .switch input:checked + .slider { background: var(--switch-checked-track-color, var(--accent)); opacity: .9; }
  .switch input:checked + .slider::before { transform: translateX(18px); background: var(--switch-checked-button-color, var(--accent)); filter: brightness(1.15); }
  .switch input:disabled + .slider { cursor: default; opacity: .3; }
  .switch-label { display: flex; align-items: center; gap: 10px; font-weight: 500; }
  .conf { display: inline-flex; align-items: center; gap: 6px; }
  .conf-bar { display: inline-block; width: 70px; height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; }
  .conf-bar span { display: block; height: 100%; }
  .segmented.day-select { max-width: 100%; overflow-x: auto; margin-bottom: 10px; }
  .segmented.day-select .seg { white-space: nowrap; }
  .segmented { display: inline-flex; border: 1px solid var(--border); border-radius: 18px; overflow: hidden; }
  .seg { background: none; border: 0; padding: 6px 12px; cursor: pointer; color: var(--primary-text-color); font-family: inherit; font-size: 13px; }
  .seg.active { background: var(--accent); color: var(--text-primary-color, #fff); }
  .legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
  .legend i, .tip i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; vertical-align: middle; }
  .legend i.line { height: 3px; }
  .chart { position: relative; width: 100%; min-height: 60px; }
  .chart svg { display: block; overflow: visible; }
  .chart .grid { stroke: var(--border); stroke-width: 1; }
  .chart .zero { stroke: var(--muted); stroke-width: 1; }
  .chart .shade { fill: #5c6bc0; opacity: .08; }
  .chart .axis { fill: var(--muted); font-size: 11px; }
  .chart .label { fill: var(--primary-text-color); font-size: 13px; }
  .tip {
    position: absolute; display: none; pointer-events: none; z-index: 2; min-width: 160px;
    background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 12px;
    box-shadow: 0 4px 12px rgba(0,0,0,.2);
  }
  .tip-title { font-weight: 500; margin-bottom: 4px; }
  .table-wrap { overflow-x: auto; margin-top: 8px; }
  .room-select { width: auto; min-width: 180px; }
  .setpoint { position: relative; }
  .setpoint.pending .sp-value { color: var(--accent); }
  .stepper { display: inline-flex; gap: 6px; margin-top: 4px; }
  .step-btn { width: 30px; height: 30px; border-radius: 50%; border: 1px solid var(--border); background: var(--card);
    color: var(--primary-text-color); font-size: 18px; line-height: 1; cursor: pointer; font-family: inherit; }
  .step-btn:hover { border-color: var(--accent); color: var(--accent); }
  .step-btn:active { transform: scale(.92); }
  .airco { border-top: 1px solid var(--border); padding: 8px 0 4px; font-size: 13px; }
  .airco-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
  .airco-title { font-weight: 500; display: flex; gap: 6px; align-items: center; }
  .airco-line { display: flex; justify-content: space-between; gap: 8px; padding: 2px 0; }
  .airco-modes { margin-top: 6px; }
  .checklist.short { max-height: 170px; }
  /* thermostat style setpoint: − value + ; click the value to type */
  .thermo { display: inline-flex; align-items: center; gap: 6px; }
  .thermo.small .step-btn { width: 26px; height: 26px; font-size: 16px; }
  .sp-btn { background: none; border: 0; border-bottom: 1px dashed transparent; color: inherit; font: inherit; font-size: 22px; font-weight: 300;
    padding: 0 2px; cursor: text; line-height: 1.2; }
  .sp-btn:hover:not(:disabled) { border-bottom-color: var(--accent); }
  .sp-btn:disabled { cursor: default; }
  .sp-btn small { font-size: 14px; margin-left: 2px; color: var(--muted); }
  .thermo.small .sp-btn { font-size: 15px; }
  .sp-input::-webkit-inner-spin-button, .sp-input::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
  .sp-input { -moz-appearance: textfield; width: 84px; font-size: 20px; padding: 2px 6px; text-align: center; border-radius: 6px; border: 1px solid var(--accent);
    background: var(--card); color: var(--primary-text-color); font-family: inherit; }
  /* savings measurement */
  .measure-head { display: flex; gap: 16px; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; margin-bottom: 8px; }
  .measure-head > div:first-child { flex: 1; min-width: 240px; line-height: 1.5; }
  .measure-head h3 { margin-bottom: 4px; }
  .measure-start { display: flex; align-items: flex-end; gap: 4px; }
  .measure-start .field { min-width: 160px; }
  .placeholder { padding: 32px 16px; text-align: center; line-height: 1.6; border: 1px dashed var(--border); border-radius: 8px; }
  /* chart markers */
  .chart .reference { fill: var(--primary-text-color); opacity: .035; }
  .chart .start-line { stroke: var(--accent); stroke-width: 2; }
  .chart .start-label { fill: var(--accent); font-size: 10px; font-weight: 500; }
  .legend .start-key { background: var(--accent); }
  .chart .event-line { stroke: var(--muted); stroke-width: 1; stroke-dasharray: 2 3; opacity: .6; }
  .chart .event-flag { fill: var(--muted); }
  .legend .event-key { width: 8px; height: 10px; background: var(--muted); clip-path: polygon(0 0, 100% 0, 70% 50%, 100% 100%, 0 100%); }
  .tip-event { margin-top: 4px; padding-top: 4px; border-top: 1px solid var(--border); color: var(--muted); }
  /* settings */
  .settings > .card h3 { margin-top: 0; }
  details.card.optional { margin-top: 0; padding-top: 4px; }
  .save-bar { position: sticky; bottom: 0; display: flex; justify-content: flex-end; padding: 12px 0;
    background: linear-gradient(transparent, var(--primary-background-color, #fafafa) 40%); }
  .good, table.periods td.good b { color: #43a047; }
  .bad, table.periods td.bad b { color: #e53935; }
  table.periods th.num, table.periods td.num { text-align: right; white-space: nowrap; }
  table.periods tr.current td { background: color-mix(in srgb, var(--accent) 7%, transparent); }
  .fp-days { margin: 8px 0; line-height: 1.8; }
  .fp-day { margin-right: 12px; white-space: nowrap; }
  .actions.left { justify-content: flex-start; }
  /* tips */
  .section { margin: 8px 4px 12px; font-weight: 500; font-size: 16px; }
  .grow { flex: 1; min-width: 240px; margin: 0; }
  .tip-card { display: flex; gap: 14px; align-items: flex-start; }
  .tip-card.cat-measurement { border-left: 4px solid var(--accent); }
  .tip-icon { font-size: 22px; line-height: 1; padding-top: 2px; }
  .tip-body { flex: 1; min-width: 0; }
  .tip-body p { margin: 6px 0 0; line-height: 1.5; color: var(--muted); font-size: 14px; }
  .tip-details { margin: 6px 0 0; padding-left: 18px; color: var(--muted); font-size: 13px; }
  .tip-saving { text-align: right; min-width: 130px; display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
  table.ranking td.rank { font-size: 20px; font-weight: 300; width: 32px; }
  .conf-bar.wide { width: 110px; }
  h3.sub { margin-top: 20px; font-size: 14px; color: var(--muted); }
  .model-status { border: 1px solid var(--border); border-radius: 10px; padding: 16px; margin-top: 8px; }
  .model-head { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 16px; }
  .steps { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
  .step { display: flex; gap: 10px; align-items: flex-start; flex: 1; min-width: 170px; opacity: .55; }
  .step.done, .step.current { opacity: 1; }
  .step-dot { flex: none; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    border: 2px solid var(--border); font-weight: 500; font-size: 13px; }
  .step.done .step-dot { background: #43a047; border-color: #43a047; color: #fff; }
  .step.current .step-dot { border-color: var(--accent); color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 20%, transparent); }
  .step-title { font-weight: 500; font-size: 14px; }
  .step-line { width: 24px; height: 2px; background: var(--border); margin-top: 14px; flex: none; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin-bottom: 8px; }
  .tile { background: var(--secondary-background-color, rgba(0,0,0,.04)); border-radius: 8px; padding: 12px; display: flex; flex-direction: column; gap: 4px; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { text-align: left; padding: 8px; border-bottom: 1px solid var(--border); vertical-align: top; }
  th { font-weight: 500; color: var(--muted); font-size: 12px; }
  .sched-section { border: 0; padding: 0; margin: 4px 0; min-width: 0; }
  .sched-section.hidden { display: none; }
  .sched-section.dimmed { opacity: 0.4; }
  div.periods { display: flex; flex-direction: column; gap: 6px; margin: 6px 0; }
  .period-row { display: flex; align-items: center; gap: 8px; }
  .period-row input[type="time"] { max-width: 130px; }
  .form-grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); margin: 8px 0; align-items: end; }
  .field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
  .field.hidden { display: none; }
  input[type=text], input[type=number], input[type=time], input[type=date], input[type=search], select {
    font: inherit; font-size: 14px; padding: 9px 10px; border-radius: 6px; border: 1px solid var(--border);
    background: var(--input-fill-color, var(--secondary-background-color, transparent)); color: var(--primary-text-color); width: 100%;
  }
  input:focus, select:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
  input:disabled, select:disabled { opacity: .55; }
  .check { display: flex; gap: 10px; align-items: flex-start; padding: 8px; border-radius: 6px; cursor: pointer; font-size: 14px; }
  .check:hover { background: color-mix(in srgb, var(--accent) 6%, transparent); }
  .check.disabled { opacity: .5; cursor: default; }
  .check.inline { padding: 8px 0; }
  .check input { margin-top: 3px; accent-color: var(--accent); }
  .checklist { max-height: 300px; overflow-y: auto; border: 1px solid var(--border); border-radius: 8px; padding: 4px; }
  .info { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; background: var(--secondary-background-color, rgba(0,0,0,.04)); border-radius: 8px; padding: 10px 12px; margin-top: 8px; font-size: 13px; }
  .info > div { display: flex; flex-direction: column; gap: 2px; }
  .overlay { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 10; padding: 16px; }
  .dialog { background: var(--card); border-radius: var(--radius); padding: 20px 24px; width: min(520px, 100%); max-height: 90vh; overflow-y: auto; box-shadow: 0 10px 30px rgba(0,0,0,.35); }
  .dialog h2 { margin: 0 0 16px; font-weight: 400; }
  .dialog .field { margin-bottom: 12px; }
  .toast {
    position: fixed; left: 50%; bottom: 24px; transform: translate(-50%, 100px); background: #323232; color: #fff;
    padding: 12px 20px; border-radius: 8px; transition: transform .25s, opacity .25s; z-index: 20; font-size: 14px; max-width: 90vw;
    opacity: 0; visibility: hidden;
  }
  .toast.show { transform: translate(-50%, 0); opacity: 1; visibility: visible; }
  .toast.error { background: var(--error-color, #db4437); }
  .busy { position: fixed; top: 0; left: 0; right: 0; height: 3px; overflow: hidden; z-index: 30; display: none; }
  .busy.show { display: block; }
  .busy .spinner { width: 30%; height: 3px; border: 0; border-radius: 0; background: var(--accent); animation: slide 1s infinite linear; margin: 0; }
  .spinner { width: 28px; height: 28px; border: 3px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 1s linear infinite; margin: 16px auto; }
  details.optional { border-top: 1px solid var(--border); margin-top: 20px; padding-top: 4px; font-size: 14px; }
  details.optional summary { list-style: revert; color: var(--primary-text-color); }
  details.optional summary h3 { display: inline-block; margin: 12px 0 8px 4px; }
  details.optional .field small { font-size: 11px; }
  .bstatus { display: flex; flex-wrap: wrap; gap: 10px 24px; padding: 12px; margin-bottom: 12px; border-radius: 8px;
    background: var(--secondary-background-color, rgba(0,0,0,.04)); }
  .bstat { display: flex; flex-direction: column; gap: 4px; align-items: flex-start; min-width: 110px; }
  .tile.warn { box-shadow: inset 3px 0 0 #e53935; }
  .tile.note { box-shadow: inset 3px 0 0 #fb8c00; }
  .split { display: flex; height: 10px; border-radius: 5px; overflow: hidden; background: var(--border); margin: 6px 0 2px; }
  .split span { display: block; height: 100%; }
  .legend .shade-key { width: 12px; height: 10px; background: #5c6bc0; opacity: .25; border-radius: 2px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  @keyframes slide { from { transform: translateX(-100%); } to { transform: translateX(400%); } }
  @media (max-width: 600px) {
    .step-line { display: none; }
    .content { padding: 8px; }
    .grid.wide { grid-template-columns: 1fr; }
    .tab span { display: none; }
    .tab { flex: 1; justify-content: center; }
    .big { font-size: 26px; }
    .info { grid-template-columns: 1fr 1fr; }
    .tip-card { flex-wrap: wrap; }
    .tip-saving { min-width: 0; width: 100%; flex-direction: row; justify-content: flex-end; align-items: baseline; gap: 8px; }
  }
`;

if (!customElements.get("ha-climate-panel")) {
  customElements.define("ha-climate-panel", HaClimatePanel);
}
