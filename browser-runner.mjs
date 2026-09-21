import { appendFileSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { createJoobleAdapter, joobleSource, JoobleBudgetError, JoobleChallengeError } from "./sources/jooble-adapter.mjs";

const ROOT = fileURLToPath(new URL(".", import.meta.url)).replace(/\/$/, "");
const SOURCE = joobleSource.name;
const VERSION = 7;
const SORT = "jooble-freshness-exhaustive";
const STEP_BUDGET_MS = 18_000;
const RUN_SOFT_BUDGET_MS = 20_000;
const RUN_HARD_BUDGET_MS = 26_000;
const MAX_TRANSITIONS = 5;
const RADAR_TIMEOUT_MS = 3_000;
class RunnerFailure extends Error {}
function compact(value, limit = 240) { return String(value ?? "").replace(/\s+/g, " ").trim().slice(0, limit); }
function safeError(value) { return compact(String(value ?? "").replace(/https?:\/\/[^\s,\]\}]+/g, "<url>")); }
function output(status, fields = {}) { return JSON.stringify({ status, ...fields }); }
function allowedStartArgs(args) { return Array.isArray(args) && (args.length === 0 || (args[0] === "--test-live" && (args.length === 1 || (args.length === 3 && args[1] === "--freshness" && ["24h", "3d", "7d"].includes(args[2]))))); }
function callRadar(args, receipt) { const child = spawnSync("python3", ["radar.py", ...args, ...(receipt === undefined ? [] : ["--receipt", "-"])], { cwd: ROOT, input: receipt === undefined ? undefined : JSON.stringify(receipt), encoding: "utf8", maxBuffer: 4 * 1024 * 1024, timeout: RADAR_TIMEOUT_MS, killSignal: "SIGTERM" }); if (child.error) return { ok: false, error: child.error.code === "ETIMEDOUT" ? "radar.py exceeded its 3-second deadline" : safeError(child.error.message) }; if (child.signal) return { ok: false, error: `radar.py stopped by ${child.signal}` }; const text = String(child.status === 0 ? child.stdout : child.stderr || child.stdout).trim(); if (child.status !== 0) return { ok: false, error: safeError(text) }; try { return { ok: true, value: JSON.parse(text) }; } catch { return { ok: false, error: "radar.py returned non-JSON output" }; } }
function appendDiagnostic(state, event, payload = {}) { if (!state.diagnosticsPath) return; try { mkdirSync(dirname(state.diagnosticsPath), { recursive: true }); appendFileSync(state.diagnosticsPath, `${JSON.stringify({ at: new Date().toISOString(), event, ...payload })}\n`, "utf8"); } catch {} }
function hydrateDiagnosticState(state) {
  if (!state.diagnosticsPath) return;
  let rows = [];
  try { rows = readFileSync(state.diagnosticsPath, "utf8").split(/\n+/).filter(Boolean).map((line) => { try { return JSON.parse(line); } catch { return null; } }).filter(Boolean); } catch { return; }
  const productionRoutes = new Set(Object.keys(joobleSource.routes));
  const completedProbes = new Set();
  for (const row of rows) {
    if ((row.event === "route-page" || row.event === "route-terminal") && productionRoutes.has(row.route) && Array.isArray(row.cards)) {
      for (const card of row.cards) { const id = String(card?.url || "").match(/\/jdp\/(-?\d+)/)?.[1]; if (id) state.productionIds.add(id); }
    }
    if (row.event === "diagnostic-sweep-route" && typeof row.query === "string") completedProbes.add(row.query);
  }
  const index = joobleSource.diagnosticRoutes.findIndex((target) => !completedProbes.has(target.query));
  const hydratedIndex = index < 0 ? joobleSource.diagnosticRoutes.length : index;
  if (!state.sweep || state.sweep.index < hydratedIndex) state.sweep = { index: hydratedIndex, list: null };
}
async function ensureTab(state) { state.tab ??= await state.browser.tabs.new(); return state.tab; }
async function discardTab(state) { if (state.tab) { try { await state.tab.close(); } catch {} state.tab = null; } }
async function captureFailureDiagnostic(state, source, stage, error) { let snapshot = {}; if (state.tab) { try { snapshot = await state.tab.playwright.evaluate(() => { const clean = (value) => String(value || "").replace(/\s+/g, " ").trim(); const body = clean(document.body.innerText); return { url: location.href, title: document.title, body: body.slice(0, 5000), challenge: /performing security verification|captcha|verification|перевірка безпеки|проверка безопасности/i.test(`${document.title} ${body.slice(0, 1600)}`), jdp: [...document.querySelectorAll('a[href*="/jdp/"],link[href*="/jdp/"]')].slice(0, 8).map((node) => ({ href: node.href, text: clean(node.textContent) })) }; }); } catch {} } appendDiagnostic(state, "failure", { source, stage, reason: safeError(error?.message || error), snapshot }); }

export function createRunner({ browser, startArgs = [] }) {
  if (!browser || !allowedStartArgs(startArgs)) throw new RunnerFailure("browser and supported startArgs are required");
  const state = { browser, startArgs: [...startArgs], cli: null, freshness: null, diagnosticsPath: null, tab: null, list: null, details: null, sweep: null, productionIds: new Set(), failures: new Map(), finished: false, adapter: null };
  state.adapter = createJoobleAdapter({ appendDiagnostic: (event, payload) => appendDiagnostic(state, event, payload) });
  async function browserFailure(error, source, stage, { preserveDetails = false } = {}) { await captureFailureDiagnostic(state, source, stage, error); const key = `${source}:${stage}`; const message = safeError(error?.message || error); const first = state.failures.get(key); state.list = null; if (!preserveDetails) state.details = null; await discardTab(state); if (!first) { state.failures.set(key, message); return output("CONTINUE", { source, stage, recovery: true, reason: message }); } const blocked = callRadar(["block", "--source", source, "--reason", message], { attempts: [{ route: stage, error: first }, { route: stage, error: message }] }); if (!blocked.ok) return output("RUNNER_ERROR", { source, stage, reason: blocked.error }); state.circuitBreaker = true; state.failures.delete(key); state.cli = blocked.value; appendDiagnostic(state, "production-circuit-breaker", { source, stage, reason: message }); return output("BLOCKED", { source, stage, reason: message, next_source: state.cli.next_source ?? null }); }
  function newList(route, url) { return { source: SOURCE, route, pages: [], seen: new Set(), visitedPages: new Set(), started: false, url, filterProof: null, filterMode: null, freshnessMode: null, carrierCandidates: null, carrierIndex: 0, resolvedCards: new Map() }; }
  async function observe(deadline) { const route = state.cli.next_route; if (state.cli.next_source !== SOURCE || !route || !joobleSource.routes[route]) return output("RUNNER_ERROR", { source: state.cli.next_source, stage: route || "LIST", reason: "unsupported Jooble route" }); state.list ??= newList(route, joobleSource.routes[route]); try { const collected = await state.adapter.collectList({ tab: await ensureTab(state), url: joobleSource.routes[route], route, deadline, freshness: state.freshness, list: state.list }); state.list = collected.list; if (!collected.done) return output("CONTINUE", { source: SOURCE, stage: route, processed: state.list.pages.length }); const receipt = { version: VERSION, sort: SORT, routes: [{ name: route, filter_proof: { param: String(state.freshness.param), evidence: state.list.filterProof || "" }, pages: state.list.pages }] }; const observed = callRadar(["observe", "--source", SOURCE], receipt); if (!observed.ok) { appendDiagnostic(state, "validation-error", { route, reason: observed.error }); return browserFailure(new Error(observed.error), SOURCE, route); } state.cli = observed.value; for (const page of state.list.pages) for (const card of page.cards || []) { const id = String(card.url || "").match(/\/jdp\/(-?\d+)/)?.[1]; if (id) state.productionIds.add(id); } appendDiagnostic(state, "completeness", { level: "DISCOVERY_COMPLETE", route, pages: state.list.pages.length, production_unique_ids: state.productionIds.size }); state.list = null; state.failures.delete(`${SOURCE}:${route}`); return output("PROGRESS", { source: SOURCE, stage: route, next_source: state.cli.next_source ?? null, next_route: state.cli.next_route ?? null }); } catch (error) { return browserFailure(error, SOURCE, route); } }
  async function resolve(deadline) {
    if (state.cli.next_source !== SOURCE) return output("RUNNER_ERROR", { source: state.cli.next_source, stage: "DETAILS", reason: "unsupported source" });
    const preDetailProbeCount = joobleSource.diagnosticRoutes.length;
    if (state.startArgs.length > 0 && (state.sweep?.index ?? 0) < preDetailProbeCount) {
      if (!(await sweepStep(deadline, preDetailProbeCount))) return output("CONTINUE", { source: SOURCE, stage: "DIAGNOSTIC_PREDETAIL", processed: state.sweep?.index ?? 0, total: preDetailProbeCount });
    }
    state.details ??= { source: SOURCE, pending: state.cli.pending || [], index: 0, facts: [], blocked: [], recoveryAttempts: new Set(), challengeStreak: 0 };
    while (state.details.index < state.details.pending.length && performance.now() + 10_500 <= deadline) {
      const item = state.details.pending[state.details.index];
      const tab = await ensureTab(state);
      try {
        state.details.facts.push(await state.adapter.collectDetail(tab, item.url, deadline, item));
        state.details.index += 1;
        state.details.challengeStreak = 0;
      } catch (error) {
        const isChallenge = error instanceof JoobleChallengeError || /security verification|captcha|challenge/i.test(String(error?.message || error));
        if (error instanceof JoobleBudgetError) return output("CONTINUE", { source: SOURCE, stage: "DETAILS", processed: state.details.index, total: state.details.pending.length, budget: true });
        if (!isChallenge) return browserFailure(error, SOURCE, "DETAILS", { preserveDetails: true });
        const recoveryUsed = state.details.recoveryAttempts.has(item.url);
        appendDiagnostic(state, "challenge", { url: item.url, title: item.title, index: state.details.index, recovery_used: recoveryUsed });
        if (!recoveryUsed) {
          state.details.recoveryAttempts.add(item.url);
          try { await state.adapter.recoverDetail(tab, item); continue; } catch (recoveryError) { appendDiagnostic(state, "challenge-recovery-failed", { url: item.url, reason: safeError(recoveryError?.message || recoveryError) }); }
        }
        state.details.blocked.push({ url: item.url, title: item.title, company: item.company });
        state.details.index += 1;
        state.details.challengeStreak += 1;
        await discardTab(state);
        if (state.details.challengeStreak >= 2) {
          state.circuitBreaker = true;
          appendDiagnostic(state, "detail-circuit-breaker", { blocked_url: item.url, consecutive_blocked_challenges: state.details.challengeStreak, remaining: state.details.pending.slice(state.details.index).map((candidate) => candidate.url) });
          break;
        }
        appendDiagnostic(state, "detail-challenge-skip", { blocked_url: item.url, consecutive_blocked_challenges: state.details.challengeStreak, remaining: state.details.pending.length - state.details.index });
        continue;
      }
    }
    if (state.details.index < state.details.pending.length && !state.circuitBreaker) return output("CONTINUE", { source: SOURCE, stage: "DETAILS", processed: state.details.index, total: state.details.pending.length });
    appendDiagnostic(state, "completeness", { level: "DETAILS_COMPLETE", resolved: state.details.facts.length, blocked: state.details.blocked.length });
    const resolved = callRadar(["resolve", "--source", SOURCE], { version: VERSION, details: state.details.facts, blocked: state.details.blocked });
    if (!resolved.ok) return output("RUNNER_ERROR", { source: SOURCE, stage: "DETAILS", reason: resolved.error });
    state.cli = resolved.value;
    appendDiagnostic(state, "completeness", { level: "CLASSIFICATION_COMPLETE", counts: resolved.value.counts, blocked: state.details.blocked.length });
    state.details = null;
    return output("PROGRESS", { source: SOURCE, stage: "DETAILS", next_source: state.cli.next_source ?? null, next_route: state.cli.next_route ?? null, counts: resolved.value.counts, circuit_breaker: Boolean(state.circuitBreaker) });
  }
  async function sweepStep(deadline, targetCount = joobleSource.diagnosticRoutes.length) {
    if (state.startArgs.length === 0) return true;
    state.sweep ??= { index: 0, list: null };
    const boundedTarget = Math.min(targetCount, joobleSource.diagnosticRoutes.length);
    if (state.sweep.index >= boundedTarget) return true;
    if (state.circuitBreaker) return true;
    const target = joobleSource.diagnosticRoutes[state.sweep.index];
    state.sweep.list ??= newList(target.query, target.url);
    try {
      const collected = await state.adapter.collectList({ tab: await ensureTab(state), url: target.url, route: target.query, deadline, freshness: state.freshness, list: state.sweep.list, allowUnprovenRemote: true, allowUrlOnlyFreshness: true });
      state.sweep.list = collected.list;
      if (!collected.done) return false;
      const cards = state.sweep.list.pages.flatMap((page) => page.cards || []);
      const ids = [...new Set(cards.map((card) => String(card.url || "").match(/\/jdp\/(-?\d+)/)?.[1]).filter(Boolean))];
      const outsideProduction = ids.filter((id) => !state.productionIds.has(id));
      const filterMode = state.sweep.list.filterMode || "UNKNOWN";
      const freshnessMode = state.sweep.list.freshnessMode || "UNKNOWN";
      const urlOnlyFreshness = freshnessMode === "URL_PARAM_ONLY";
      const unfilteredLocation = filterMode === "UNFILTERED_LOCATION";
      const status = urlOnlyFreshness
        ? (unfilteredLocation ? "SCANNED_URL_FRESHNESS_ONLY_UNFILTERED_LOCATION" : "SCANNED_URL_FRESHNESS_ONLY")
        : (unfilteredLocation ? "SCANNED_UNFILTERED_LOCATION" : "SCANNED");
      appendDiagnostic(state, "diagnostic-sweep-route", { query: target.query, status, filter_mode: filterMode, freshness_mode: freshnessMode, freshness_proven: freshnessMode === "URL_AND_UI", freshness_url_proven: freshnessMode === "URL_AND_UI" || freshnessMode === "URL_PARAM_ONLY", remote_proven: filterMode === "FILTERED_REMOTE", pages: state.sweep.list.pages.length, terminal: "NO_NEXT", unique_jdp: ids.length, incremental_unique_jdp: outsideProduction.length, outside_production_ids: outsideProduction, cards });
      state.sweep.index += 1;
      state.sweep.list = null;
      return state.sweep.index >= boundedTarget;
    } catch (error) {
      appendDiagnostic(state, "diagnostic-sweep-route", { query: target.query, status: "BLOCKED", reason: safeError(error?.message || error), incremental_unique_jdp: null });
      state.sweep.index += 1;
      state.sweep.list = null;
      await discardTab(state);
      return state.sweep.index >= boundedTarget;
    }
  }
  async function advanceOne(hardDeadline) { if (state.finished) return output("DONE", { reason: "runner already finished" }); if (!state.cli) { const started = callRadar(["start", ...state.startArgs]); if (!started.ok) return output("RUNNER_ERROR", { stage: "START", reason: started.error }); state.cli = started.value; state.circuitBreaker ||= started.value.source_status === "BLOCKED"; state.freshness = started.value.freshness; state.diagnosticsPath = started.value.diagnostics || join(ROOT, "results", "radar-jooble.diagnostics.jsonl"); hydrateDiagnosticState(state); appendDiagnostic(state, "run-start", { mode: started.value.mode, from: started.value.from, until: started.value.until, freshness: state.freshness, next_route: state.cli.next_route, source_status: started.value.source_status, hydrated_production_ids: state.productionIds.size, hydrated_probe_index: state.sweep?.index ?? 0 }); } if (state.cli.next_step === "observe") return observe(Math.min(performance.now() + STEP_BUDGET_MS, hardDeadline)); if (state.cli.next_step === "resolve") return resolve(hardDeadline); if (state.cli.next_step === "finish") { if (!(await sweepStep(hardDeadline))) return output("CONTINUE", { source: SOURCE, stage: "DIAGNOSTIC_SWEEP", processed: state.sweep.index, total: joobleSource.diagnosticRoutes.length }); const finished = callRadar(["finish"]); if (!finished.ok) return output("RUNNER_ERROR", { stage: "FINISH", reason: finished.error }); await discardTab(state); state.finished = true; const result = { markdown: finished.value.markdown, jsonl: finished.value.jsonl, markdown_link: `[Markdown](<${finished.value.markdown}>)`, jsonl_link: `[JSONL](<${finished.value.jsonl}>)`, diagnostics: finished.value.diagnostics, counts: finished.value.counts, elapsed_seconds: finished.value.elapsed_seconds, sources: finished.value.sources, completeness: finished.value.status === "COMPLETE" ? "COMPLETE" : "PARTIAL", navigation_metrics: state.adapter.metrics }; if (finished.value.calibration_bundle) { result.calibration_bundle = finished.value.calibration_bundle; result.calibration_bundle_link = `[Calibration ZIP](<${finished.value.calibration_bundle}>)`; } return output("DONE", result); } return output("RUNNER_ERROR", { stage: state.cli.next_step || "UNKNOWN", reason: "radar.py returned an unsupported next_step" }); }
  async function run() { const startedAt = performance.now(); const softDeadline = startedAt + RUN_SOFT_BUDGET_MS; const hardDeadline = startedAt + RUN_HARD_BUDGET_MS; let transitions = 0; let result; do { result = JSON.parse(await advanceOne(hardDeadline)); transitions += 1; if (result.status !== "PROGRESS") break; } while (transitions < MAX_TRANSITIONS && performance.now() < softDeadline && performance.now() + RADAR_TIMEOUT_MS <= hardDeadline); const { status, ...fields } = result; return output(status, { ...fields, transitions, elapsed_ms: Math.round(performance.now() - startedAt) }); }
  return Object.freeze({ run });
}
