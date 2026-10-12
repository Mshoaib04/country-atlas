"use strict";

const $ = (selector) => document.querySelector(selector);
const state = { countries: [], summary: null, pipeline: null, view: "overview", scale: "log", editing: null, detail: null, deleting: null };
const flags = new Map([
  ["Andorra", "🇦🇩"], ["United Arab Emirates", "🇦🇪"], ["Afghanistan", "🇦🇫"],
  ["Antigua and Barbuda", "🇦🇬"], ["Anguilla", "🇦🇮"], ["Albania", "🇦🇱"],
  ["Armenia", "🇦🇲"], ["Angola", "🇦🇴"], ["Antarctica", "🇦🇶"], ["Argentina", "🇦🇷"],
  ["American Samoa", "🇦🇸"], ["Austria", "🇦🇹"], ["Australia", "🇦🇺"], ["Aruba", "🇦🇼"],
  ["Åland", "🇦🇽"], ["Azerbaijan", "🇦🇿"], ["Bosnia and Herzegovina", "🇧🇦"],
  ["Barbados", "🇧🇧"], ["Bangladesh", "🇧🇩"], ["Belgium", "🇧🇪"],
]);
const integerFormat = new Intl.NumberFormat("en-US");
const decimalFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
const shortFormat = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const density = (country) => country.population / country.area;
const flag = (name) => flags.get(name) || "◎";
let toastTimer;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, signal: AbortSignal.timeout(15000) });
  if (!response.ok) {
    let message = `Request failed (HTTP ${response.status})`;
    try {
      const payload = await response.json();
      message = Array.isArray(payload.detail)
        ? payload.detail.map((item) => `${item.loc.slice(1).join(".")}: ${item.msg}`).join(" · ")
        : payload.detail || message;
    } catch { /* Keep the HTTP error if the server returned a non-JSON response. */ }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function toast(message) {
  clearTimeout(toastTimer);
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  toastTimer = setTimeout(() => { $("#toast").hidden = true; }, 4000);
}

function showView(view, { scroll = true } = {}) {
  state.view = view;
  const titles = new Map([
    ["overview", ["Overview", "A wider perspective.", "Twenty places. Four data points. A world of connections."]],
    ["records", ["Country records", "The places behind the data.", "Explore, sort, and shape your country dataset."]],
    ["pipeline", ["Data pipeline", "From source to story.", "A transparent path from the original page to every chart."]],
  ]);
  const [breadcrumb, title, subtitle] = titles.get(view);
  $("#breadcrumb-current").textContent = breadcrumb;
  $("#page-title").textContent = title;
  $("#page-subtitle").textContent = subtitle;
  document.querySelectorAll("[data-show]").forEach((section) => { section.hidden = !section.dataset.show.split(" ").includes(view); });
  document.querySelectorAll("[data-nav]").forEach((button) => {
    const active = button.dataset.nav === view;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  if (scroll) window.scrollTo({ top: 0, behavior: "instant" });
}

async function loadData() {
  $("#retry-button").disabled = true;
  try {
    const [countries, summary, pipeline] = await Promise.all([
      api("/countries"), api("/analytics/summary"), api("/pipeline/status"),
    ]);
    state.countries = countries;
    state.summary = summary;
    state.pipeline = pipeline;
    $("#connection-dot").classList.add("online");
    $("#connection-label").textContent = pipeline.read_only ? "Read-only demo" : "Database connected";
    $("#error-banner").hidden = true;
    $("#add-button").disabled = pipeline.read_only;
    $("#add-button").title = pipeline.read_only ? "This demo is read-only" : "Add a new country";
    $("#compare-button").disabled = countries.length < 2;
    renderSummary();
    renderLeaders();
    renderTable();
    renderScatter();
    renderPipeline();
  } catch (error) {
    $("#connection-dot").classList.remove("online");
    $("#connection-label").textContent = "Connection unavailable";
    $("#error-message").textContent = `Could not load the dataset. ${error.message}`;
    $("#error-banner").hidden = false;
    if (!state.countries.length) $("#table-caption").textContent = "The API is unavailable. Use Try again to reconnect.";
    throw error;
  } finally {
    $("#retry-button").disabled = false;
  }
}

function renderSummary() {
  const summary = state.summary;
  $("#metric-count").textContent = integerFormat.format(summary.count);
  $("#nav-count").textContent = summary.count;
  $("#metric-population").textContent = shortFormat.format(summary.total_population);
  $("#metric-population").title = `${integerFormat.format(summary.total_population)} people`;
  $("#metric-area").textContent = shortFormat.format(summary.total_area);
  $("#metric-area").title = `${decimalFormat.format(summary.total_area)} km²`;
  $("#metric-density").textContent = decimalFormat.format(summary.median_density);
  $("#scope-caption").textContent = summary.count === 20 ? "20 stored entries · initial scope: 20" : `${summary.count} stored · initial scope: 20`;
}

function renderLeaders() {
  const container = $("#density-leaders");
  container.replaceChildren();
  const leaders = [...state.countries].sort((a, b) => density(b) - density(a)).slice(0, 5);
  if (!leaders.length) {
    container.append(element("p", "modal-description", "Add a country to start exploring."));
    $("#density-insight").textContent = "Your first record will begin the story.";
    return;
  }
  leaders.forEach((country) => {
    const row = element("div", "leader-row");
    const top = element("div", "leader-top");
    top.append(element("span", null, flag(country.country_name)), element("span", "leader-name", country.country_name), element("strong", null, decimalFormat.format(density(country))));
    const track = element("div", "leader-track");
    const fill = element("div", "leader-fill");
    fill.style.width = `${Math.max(0, density(country) / Math.max(density(leaders[0]), 1) * 100)}%`;
    track.append(fill);
    row.append(top, track);
    container.append(row);
  });
  $("#density-insight").textContent = `${leaders[0].country_name} leads this sample at ${decimalFormat.format(density(leaders[0]))} people per km². Density tells a different story from size.`;
}

function filteredCountries() {
  const term = $("#search").value.trim().toLocaleLowerCase();
  const rows = state.countries.filter((country) => `${country.country_name} ${country.capital}`.toLocaleLowerCase().includes(term));
  const sort = $("#sort").value;
  if (sort === "name") rows.sort((a, b) => a.country_name.localeCompare(b.country_name));
  else if (sort === "density") rows.sort((a, b) => density(b) - density(a));
  else if (sort === "population" || sort === "area") rows.sort((a, b) => b[sort] - a[sort]);
  return rows;
}

function renderTable() {
  const rows = filteredCountries();
  const body = $("#country-rows");
  body.replaceChildren();
  rows.forEach((country) => {
    const row = element("tr");
    const nameCell = element("td");
    const nameButton = element("button", "country-name-button");
    nameButton.setAttribute("aria-label", `Explore ${country.country_name}`);
    const index = state.countries.findIndex((item) => item.country_name === country.country_name) + 1;
    nameButton.append(element("span", "country-index", String(index).padStart(2, "0")), element("span", "flag", flag(country.country_name)), element("span", null, country.country_name));
    nameButton.addEventListener("click", () => showDetail(country));
    nameCell.append(nameButton);
    const capital = country.capital === "None" ? "No capital (source)" : country.capital;
    row.append(nameCell, element("td", null, capital), element("td", "numeric", integerFormat.format(country.population)), element("td", "numeric", decimalFormat.format(country.area)));
    const densityCell = element("td", "numeric");
    densityCell.append(element("span", `density-badge${density(country) >= 200 ? " high" : ""}`, decimalFormat.format(density(country))));
    const actions = element("td");
    const edit = element("button", "row-edit", "↗");
    edit.setAttribute("aria-label", `Edit ${country.country_name}`);
    edit.title = "Edit country";
    edit.disabled = state.pipeline?.read_only;
    edit.addEventListener("click", () => showRecordForm(country));
    actions.append(edit);
    row.append(densityCell, actions);
    body.append(row);
  });
  $("#table-count").textContent = state.countries.length;
  $("#table-caption").textContent = `Showing ${rows.length} of ${state.countries.length} records`;
  $("#table-empty").hidden = rows.length > 0;
}

function svgElement(tag, attributes = {}, text) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderScatter() {
  const svg = $("#scatter-chart");
  svg.replaceChildren();
  const width = 760, height = 330, left = 62, right = 32, top = 22, bottom = 50;
  const plotWidth = width - left - right, plotHeight = height - top - bottom;
  const log = state.scale === "log";
  const transform = (value) => log ? Math.log1p(value) : value;
  const maxPopulation = Math.max(...state.countries.map((country) => country.population), 1) * 1.10;
  const maxArea = Math.max(...state.countries.map((country) => country.area), 1) * 1.13;
  const x = (value) => left + transform(value) / transform(maxPopulation) * plotWidth;
  const y = (value) => top + plotHeight - transform(value) / transform(maxArea) * plotHeight;
  let xTicks, yTicks;
  if (log) {
    xTicks = [0, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9].filter((value) => value <= maxPopulation);
    yTicks = [0, 1e2, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 1e9].filter((value) => value <= maxArea);
  } else {
    const niceStep = (maximum) => {
      const rough = maximum / 4;
      const power = 10 ** Math.floor(Math.log10(rough));
      return [1, 2, 2.5, 5, 10].find((factor) => factor * power >= rough) * power;
    };
    const ticks = (maximum) => {
      const step = niceStep(maximum);
      return Array.from({ length: Math.floor(maximum / step) + 1 }, (_, i) => step * i);
    };
    xTicks = ticks(maxPopulation); yTicks = ticks(maxArea);
  }
  xTicks.forEach((value) => {
    svg.append(svgElement("line", { x1: x(value), x2: x(value), y1: top, y2: height - bottom, class: "chart-grid" }));
    svg.append(svgElement("text", { x: x(value), y: height - bottom + 19, "text-anchor": "middle", class: "chart-label" }, shortFormat.format(value)));
  });
  yTicks.forEach((value) => {
    svg.append(svgElement("line", { x1: left, x2: width - right, y1: y(value), y2: y(value), class: "chart-grid" }));
    svg.append(svgElement("text", { x: left - 12, y: y(value) + 3, "text-anchor": "end", class: "chart-label" }, shortFormat.format(value)));
  });
  svg.append(svgElement("text", { x: left + plotWidth / 2, y: height - 9, "text-anchor": "middle", class: "chart-axis-title" }, "POPULATION (PEOPLE)"));
  svg.append(svgElement("text", { transform: `translate(15 ${top + plotHeight / 2}) rotate(-90)`, "text-anchor": "middle", class: "chart-axis-title" }, "AREA (KM²)"));
  $("#scale-note").textContent = log ? "Log1p axes include zero population" : "Linear axes · Original values";
  $("#linear-button").classList.toggle("selected", !log);
  $("#log-button").classList.toggle("selected", log);
  $("#linear-button").setAttribute("aria-pressed", String(!log));
  $("#log-button").setAttribute("aria-pressed", String(log));
  if (!state.countries.length) {
    svg.append(svgElement("text", { x: width / 2, y: height / 2, "text-anchor": "middle", class: "chart-label" }, "Add a country to start exploring."));
    return;
  }
  const removeTooltip = () => svg.querySelector(".chart-tooltip")?.remove();
  state.countries.forEach((country) => {
    const cx = x(country.population), cy = y(country.area);
    const color = density(country) >= 200 ? "#287a68" : density(country) >= 30 ? "#63a28c" : "#b4cdbd";
    const circle = svgElement("circle", { cx, cy, r: 4.5, fill: color, stroke: "white", "stroke-width": 1.4, class: "chart-point", tabindex: 0, role: "button", "aria-label": `${country.country_name}: ${integerFormat.format(country.population)} people, ${decimalFormat.format(country.area)} square kilometers. Open details.` });
    circle.append(svgElement("title", {}, country.country_name));
    const showTooltip = () => {
      removeTooltip();
      const text = `${country.country_name} · ${shortFormat.format(country.population)} people`;
      const tooltipWidth = Math.min(text.length * 5.6 + 20, 360);
      const tx = Math.max(left, Math.min(cx - tooltipWidth / 2, width - right - tooltipWidth));
      const ty = cy < 45 ? cy + 13 : cy - 35;
      const group = svgElement("g", { class: "chart-tooltip", "pointer-events": "none" });
      group.append(svgElement("rect", { x: tx, y: ty, width: tooltipWidth, height: 26, rx: 5 }), svgElement("text", { x: tx + 10, y: ty + 17 }, text));
      svg.append(group);
    };
    circle.addEventListener("mouseenter", showTooltip);
    circle.addEventListener("focus", showTooltip);
    circle.addEventListener("mouseleave", removeTooltip);
    circle.addEventListener("blur", removeTooltip);
    circle.addEventListener("click", () => { removeTooltip(); showDetail(country); });
    circle.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); removeTooltip(); showDetail(country); }
    });
    svg.append(circle);
  });
  // Label just a few landmarks so small screens stay legible.
  const landmarks = new Set([state.summary.largest_country, state.summary.most_populous_country, "Australia"]);
  state.countries.filter((country) => landmarks.has(country.country_name)).forEach((country) => {
    const cx = x(country.population), cy = y(country.area);
    const rightAligned = cx > width - 135;
    svg.append(svgElement("text", { x: cx + (rightAligned ? -9 : 9), y: cy - 9, "text-anchor": rightAligned ? "end" : "start", class: "chart-label", "pointer-events": "none" }, country.country_name));
  });
}

function renderPipeline() {
  const pipeline = state.pipeline;
  const scrape = pipeline.last_scrape;
  $("#store-step").textContent = `${pipeline.stored_count} records stored`;
  $("#scrape-step").textContent = scrape ? `${scrape.record_count} entries validated` : "No live scrape recorded";
  $("#scraped-at").textContent = scrape ? new Date(scrape.scraped_at).toLocaleString(undefined, { dateStyle: "long", timeStyle: "short" }) : "No scrape recorded";
  $("#import-scope").textContent = `First ${pipeline.scope} entries in source order · ${pipeline.stored_count} currently stored`;
  $("#source-hash").textContent = scrape?.source_sha256 || "No source checksum available";
  $("#copy-hash").disabled = !scrape;
}

function showRecordForm(country = null) {
  if (state.pipeline?.read_only) return;
  state.editing = country;
  $("#record-form").reset();
  $("#form-error").hidden = true;
  $("#record-dialog-title").textContent = country ? `Edit ${country.country_name}` : "Add a country";
  $("#record-dialog-description").textContent = country ? "The country name is a permanent natural key. Update the details below." : "Make this dataset your own. All four fields are required.";
  $("#field-name").disabled = Boolean(country);
  if (country) {
    $("#field-name").value = country.country_name;
    $("#field-capital").value = country.capital;
    $("#field-population").value = country.population;
    $("#field-area").value = country.area;
  }
  $("#record-dialog").showModal();
}

function showDetail(country) {
  state.detail = country;
  $("#detail-title").textContent = `${flag(country.country_name)} ${country.country_name}`;
  $("#detail-capital").textContent = country.capital === "None" ? "The source lists no capital for this entry." : `Capital · ${country.capital}`;
  const metrics = $("#detail-metrics");
  metrics.replaceChildren();
  [["POPULATION", integerFormat.format(country.population)], ["AREA · KM²", decimalFormat.format(country.area)], ["PEOPLE PER KM²", decimalFormat.format(density(country))], ["POPULATION SHARE", `${state.summary.total_population ? (country.population / state.summary.total_population * 100).toFixed(1) : "0.0"}%`]].forEach(([label, value]) => {
    const stat = element("div", "detail-stat"); stat.append(element("span", null, label), element("strong", null, value)); metrics.append(stat);
  });
  const rank = [...state.countries].sort((a, b) => density(b) - density(a)).findIndex((item) => item.country_name === country.country_name) + 1;
  $("#detail-context").textContent = `${country.country_name} ranks ${rank} of ${state.countries.length} entries by population density in this dataset. Values reflect the educational source and your local edits.`;
  $("#detail-edit").disabled = state.pipeline.read_only;
  $("#detail-delete").disabled = state.pipeline.read_only;
  $("#detail-dialog").showModal();
}

function showDelete(country) {
  state.deleting = country;
  $("#delete-description").textContent = `This removes ${country.country_name} from your local database. A fresh scrape can restore original source entries.`;
  $("#delete-error").hidden = true;
  $("#delete-dialog").showModal();
}

function showComparison() {
  [$("#compare-first"), $("#compare-second")].forEach((select) => {
    select.replaceChildren();
    state.countries.forEach((country) => { const option = element("option", null, country.country_name); option.value = country.country_name; select.append(option); });
  });
  $("#compare-first").value = state.summary.densest_country;
  $("#compare-second").value = state.countries.some((country) => country.country_name === "Australia") ? "Australia" : state.countries.find((country) => country.country_name !== state.summary.densest_country).country_name;
  renderComparison();
  $("#compare-dialog").showModal();
}

function renderComparison() {
  const first = state.countries.find((country) => country.country_name === $("#compare-first").value);
  const second = state.countries.find((country) => country.country_name === $("#compare-second").value);
  if (!first || !second) return;
  const results = $("#comparison-results");
  results.replaceChildren();
  [["Population · people", (country) => country.population], ["Area · square kilometers", (country) => country.area], ["Density · people per km²", density]].forEach(([title, getValue]) => {
    const section = element("div", "comparison-metric");
    section.append(element("h3", null, title));
    const maximum = Math.max(getValue(first), getValue(second), 1);
    [first, second].forEach((country, index) => {
      const line = element("div", `comparison-line${index ? " second" : ""}`);
      const bar = element("div", "comparison-bar");
      bar.style.width = `${getValue(country) / maximum * 42}%`;
      line.append(element("span", null, country.country_name), bar, element("strong", null, decimalFormat.format(getValue(country))));
      section.append(line);
    });
    results.append(section);
  });
  if (first.country_name === second.country_name) $("#comparison-note").textContent = "Choose two different countries to explore their differences.";
  else {
    const denser = density(first) >= density(second) ? first : second;
    const other = denser === first ? second : first;
    $("#comparison-note").textContent = density(other) > 0
      ? `${denser.country_name} is ${(density(denser) / density(other)).toFixed(1)}× as densely populated as ${other.country_name}. Similar area does not mean similar population.`
      : `${other.country_name} has zero population in this source. A density ratio is undefined; its point remains visible in the Log1p chart.`;
  }
}

document.querySelectorAll("[data-nav]").forEach((button) => button.addEventListener("click", () => showView(button.dataset.nav)));
document.querySelectorAll(".close-modal").forEach((button) => button.addEventListener("click", () => button.closest("dialog").close()));
document.querySelectorAll("dialog").forEach((dialog) => dialog.addEventListener("click", (event) => { if (event.target === dialog) { const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close(); } }));
$("#explore-button").addEventListener("click", () => { showView("records"); $("#search").focus(); });
$("#search").addEventListener("input", renderTable);
$("#sort").addEventListener("change", renderTable);
$("#linear-button").addEventListener("click", () => { state.scale = "linear"; renderScatter(); });
$("#log-button").addEventListener("click", () => { state.scale = "log"; renderScatter(); });
$("#retry-button").addEventListener("click", () => { loadData().catch(() => {}); });
$("#add-button").addEventListener("click", () => showRecordForm());
$("#compare-button").addEventListener("click", showComparison);
$("#compare-first").addEventListener("change", renderComparison);
$("#compare-second").addEventListener("change", renderComparison);
$("#detail-edit").addEventListener("click", () => { $("#detail-dialog").close(); showRecordForm(state.detail); });
$("#detail-delete").addEventListener("click", () => { $("#detail-dialog").close(); showDelete(state.detail); });
$("#copy-hash").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText(state.pipeline.last_scrape.source_sha256); toast("Source checksum copied"); }
  catch { toast("Select the checksum text to copy it manually."); }
});
$("#record-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const editing = state.editing;
  const payload = { capital: $("#field-capital").value.trim(), population: Number($("#field-population").value), area: Number($("#field-area").value) };
  if (!editing) payload.country_name = $("#field-name").value.trim();
  $("#save-button").disabled = true;
  $("#save-button").textContent = "Saving…";
  $("#form-error").hidden = true;
  try {
    await api(editing ? `/countries/${encodeURIComponent(editing.country_name)}` : "/countries", { method: editing ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    $("#record-dialog").close();
    toast(editing ? "Country updated" : "Country added");
    await loadData();
  } catch (error) {
    if ($("#record-dialog").open) { $("#form-error").textContent = error.message; $("#form-error").hidden = false; }
  } finally { $("#save-button").disabled = false; $("#save-button").textContent = "Save country"; }
});
$("#confirm-delete").addEventListener("click", async () => {
  $("#confirm-delete").disabled = true;
  $("#delete-error").hidden = true;
  try {
    await api(`/countries/${encodeURIComponent(state.deleting.country_name)}`, { method: "DELETE" });
    $("#delete-dialog").close(); toast("Country deleted"); await loadData();
  } catch (error) { $("#delete-error").textContent = error.message; $("#delete-error").hidden = false; }
  finally { $("#confirm-delete").disabled = false; }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "/" && !document.querySelector("dialog[open]") && !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) {
    event.preventDefault(); showView("records"); $("#search").focus();
  }
});
showView("overview", { scroll: false });
loadData().catch(() => {});
