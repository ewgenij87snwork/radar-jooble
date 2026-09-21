const SOURCE = "Jooble";
const TRACKING = new Set(["ref", "sid", "fbclid", "gclid", "clickid", "source"]);
const DETAIL_TEXT_LIMIT = 20_000;

export const joobleSource = Object.freeze({
  name: SOURCE,
  hosts: ["ua.jooble.org", "www.ua.jooble.org"],
  identity: /^\/jdp\/-?\d+(?:[-/]|$)/,
  freshness: Object.freeze({ "24h": { key: "24h", param: "8", days: 1 }, "3d": { key: "3d", param: "2", days: 3 }, "7d": { key: "7d", param: "3", days: 7 } }),
  routes: Object.freeze({
    "angular developer": "https://ua.jooble.org/работа-angular-developer/Віддалено",
    "react developer": "https://ua.jooble.org/работа-react-developer/Віддалено",
    "frontend developer": "https://ua.jooble.org/работа-frontend-developer/Віддалено",
    "front end developer": "https://ua.jooble.org/работа-front-end-developer/Віддалено",
    "frontend engineer": "https://ua.jooble.org/работа-frontend-engineer/Віддалено",
    "typescript developer": "https://ua.jooble.org/работа-typescript-developer/Віддалено",
    "javascript developer": "https://ua.jooble.org/работа-javascript-developer/Віддалено",
    "full stack developer": "https://ua.jooble.org/работа-full-stack-developer/Віддалено",
    "fullstack engineer": "https://ua.jooble.org/работа-fullstack-engineer/Віддалено",
    "node.js developer": "https://ua.jooble.org/работа-node.js-developer/Віддалено",
    "nestjs developer": "https://ua.jooble.org/работа-nestjs-developer/Віддалено",
    "ai developer": "https://ua.jooble.org/работа-ai-developer/Віддалено",
    "ai engineer": "https://ua.jooble.org/работа-ai-engineer/Віддалено",
  }),
  diagnosticRoutes: Object.freeze([
    // Calibration-only semantic probes: test bare technology terms against the
    // role-qualified production routes without changing production coverage.
    // Keep both Node spellings because Jooble may canonicalize/search them differently.
    "nestjs", "nodejs", "node.js", "typescript", "javascript", "react", "angular",
  ].map((query) => ({ query, url: `https://ua.jooble.org/работа-${query.replace(/\s+/g, "-")}/Віддалено` }))),
});

export class JoobleAdapterError extends Error {}
export class JoobleChallengeError extends JoobleAdapterError {}
export class JoobleBudgetError extends JoobleAdapterError {
  constructor(message, latest = null) { super(message); this.latest = latest; }
}

const compact = (value, limit = 240) => String(value ?? "").replace(/\s+/g, " ").trim().slice(0, limit);
const carrierId = (url) => {
  try { return new URL(url).pathname.match(/\/(?:jdp|desc)\/(-?\d+)/)?.[1] ?? ""; }
  catch { return ""; }
};
const directId = (url) => {
  try { return new URL(url).pathname.match(/\/jdp\/(-?\d+)/)?.[1] ?? ""; }
  catch { throw new JoobleAdapterError(`Invalid identity URL: ${compact(url) || "<empty>"}`); }
};
const canonical = (value) => {
  let url;
  try { url = new URL(value); } catch { throw new JoobleAdapterError(`Invalid URL input: ${compact(value) || "<empty>"}`); }
  url.hash = "";
  url.pathname = url.pathname.replace(/\/{2,}/g, "/").replace(/\/$/, "") || "/";
  for (const key of [...url.searchParams.keys()]) if (TRACKING.has(key.toLowerCase()) || key.toLowerCase().startsWith("utm_")) url.searchParams.delete(key);
  url.searchParams.sort();
  return url.toString().replace(/\/$/, "");
};
const remotePathAliases = new Set(["віддалено", "удаленно", "remote"]);
const remotePathSegment = (value) => {
  try { return decodeURIComponent(new URL(value).pathname).split("/").filter(Boolean).find((segment) => remotePathAliases.has(segment.toLowerCase())) || ""; }
  catch { return ""; }
};
const hasRemotePath = (value) => Boolean(remotePathSegment(value));
const withFreshness = (base, freshness, { requireRemoteProof = true } = {}) => {
  let url;
  try { url = new URL(base); } catch { throw new JoobleAdapterError(`Invalid continuation URL: ${compact(base) || "<empty>"}`); }
  const legacyRemoteQuery = [...url.searchParams.keys()].some((key) => key.toLowerCase() === "l");
  if (requireRemoteProof && legacyRemoteQuery) throw new JoobleAdapterError("Legacy l=Remote query is not a Jooble remote proof");
  if (requireRemoteProof && !hasRemotePath(url.toString())) throw new JoobleAdapterError("Jooble URL is missing canonical Remote location path");
  url.searchParams.set("date", String(freshness.param));
  return url.toString();
};
const card = (url, title, company, date, snippet, promoted = false, evidence = {}) => ({
  url: canonical(url), title: compact(title) || "UNKNOWN", company: compact(company) || "UNKNOWN",
  date: compact(date, 120) || "UNKNOWN", snippet: compact(snippet), promoted: Boolean(promoted),
  carrier_url: evidence.sourceUrl || "", listing_text: compact(evidence.listingText || snippet, 4000),
  location_text: compact(evidence.locationText || "", 500),
  origin_url: evidence.originUrl || "",
});
const challengeText = /performing security verification|security verification|captcha|are you human|перевірка безпеки|проверка безопасности/i;

async function poll(tab, deadline, read, accepted, label, budgetLimited = false) {
  let latest = await read();
  while (!accepted(latest)) {
    if (performance.now() >= deadline) {
      if (budgetLimited) throw new JoobleBudgetError(`${label}: batch budget`, latest);
      throw new JoobleAdapterError(`${label}: condition deadline`);
    }
    await tab.playwright.waitForTimeout(250);
    latest = await read();
  }
  return latest;
}

function normalizedCard(root, posting, href, id, clean) {
  const text = clean(root.innerText || "");
  const titleNode = root.querySelector("h1,h2,h3,h4,[data-test-name*='title' i],[data-testid*='title' i]");
  const companyNode = root.querySelector('[data-test-name*="company" i], [data-testid*="company" i], [class*="company" i]');
  const date = clean(posting?.datePosted || root.querySelector("time[datetime]")?.getAttribute("datetime") || [...text.split(/\n+/)].reverse().find((line) => /(?:сьогодні|сегодня|today|\d+\s*(?:год|час|дн|день|hours?|days?))/i.test(line)) || "UNKNOWN");
  return { id, sourceUrl: href, title: clean(posting?.title || titleNode?.textContent || root.querySelector("a")?.textContent || "UNKNOWN"), company: clean(posting?.hiringOrganization?.name || companyNode?.textContent || "UNKNOWN"), date, snippet: text.slice(0, 240), promoted: /\b(?:запропоновані|предложенные|sponsored|promoted)\b/i.test(text) };
}

async function discover(tab) {
  return tab.playwright.evaluate(() => {
    const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const idOf = (value) => String(value || "").match(/\/(?:jdp|desc)\/(-?\d+)/)?.[1] || "";
    const postingSnapshot = (posting) => {
      if (!posting || typeof posting !== "object") return null;
      const box = document.createElement("div");
      box.innerHTML = String(posting.description || "");
      const detailText = clean(box.innerText || box.textContent || posting.description || "");
      const locationText = clean([posting.jobLocationType, posting.jobLocation?.address?.addressLocality, posting.jobLocation?.address?.addressRegion].filter(Boolean).join(" · "));
      return { title: clean(posting.title), company: clean(posting.hiringOrganization?.name), published_date: clean(posting.datePosted || "UNKNOWN"), location_text: locationText, detail_text: detailText.slice(0, 20000) };
    };
    const postings = new Map();
    const visit = (value) => {
      if (Array.isArray(value)) return value.forEach(visit);
      if (!value || typeof value !== "object") return;
      const types = Array.isArray(value["@type"]) ? value["@type"] : [value["@type"]];
      if (types.some((item) => /JobPosting/i.test(String(item || "")))) {
        const raw = typeof value.identifier === "object" ? value.identifier?.value : value.identifier;
        const id = idOf(value.url) || String(raw || "").match(/^-?\d+$/)?.[0] || "";
        if (id) postings.set(id, value);
      }
      if (Array.isArray(value["@graph"])) value["@graph"].forEach(visit);
    };
    const pageGlobal = typeof window === "object" ? window : {};
    for (const root of [pageGlobal.__INITIAL_STATE__, pageGlobal.__NEXT_DATA__, pageGlobal.__NUXT__]) visit(root);
    for (const script of document.scripts) {
      const raw = script.textContent || "";
      if (!/__INITIAL_STATE__|__NEXT_DATA__|__NUXT__|JobPosting/i.test(raw)) continue;
      try { const start = raw.indexOf("{"); const end = raw.lastIndexOf("}"); if (start >= 0 && end > start) visit(JSON.parse(raw.slice(start, end + 1))); } catch {}
    }
    for (const script of document.querySelectorAll('script[type="application/ld+json"]')) { try { visit(JSON.parse(script.textContent || "")); } catch {} }
    const dateFromRoot = (root, posting) => clean(posting?.datePosted || root.querySelector("time[datetime]")?.getAttribute("datetime") || "UNKNOWN");
    const direct = [];
    const directSeen = new Set();
    for (const node of document.querySelectorAll('[href*="/jdp/"]')) {
      const id = idOf(node.href); if (!id || directSeen.has(id)) continue;
      directSeen.add(id); const root = node.closest("article") || node.parentElement || node;
      const posting = postings.get(id); const text = clean(root.innerText);
      direct.push({ url: node.href, title: clean(posting?.title || node.textContent), company: clean(posting?.hiringOrganization?.name || "UNKNOWN"), date: dateFromRoot(root, posting), snippet: text.slice(0, 240), promoted: /\b(?:запропоновані|предложенные|sponsored|promoted)\b/i.test(text), structuredDetail: postingSnapshot(posting) });
    }
    const carriers = [];
    const carrierSeen = new Set();
    for (const node of document.querySelectorAll('a[href*="/desc/"]')) {
      const id = idOf(node.href); if (!id || carrierSeen.has(id)) continue;
      carrierSeen.add(id);
      let root = node.closest("article,li,[data-job-id],[data-testid*='job' i],[data-test*='job' i]") || node.parentElement || node;
      while (root.parentElement && root.parentElement.innerText.length < 3200 && root.parentElement.querySelectorAll('a[href*="/desc/"]').length === 1) root = root.parentElement;
      const text = clean(root.innerText);
      const posting = postings.get(id);
      const titleNode = root.querySelector("h1,h2,h3,h4,[data-test-name*='title' i],[data-testid*='title' i]");
      const companyNode = root.querySelector('[data-test-name*="company" i], [data-testid*="company" i], [class*="company" i]');
      carriers.push({ id, sourceUrl: node.href, title: clean(posting?.title || titleNode?.textContent || node.textContent || "UNKNOWN"), company: clean(posting?.hiringOrganization?.name || companyNode?.textContent || "UNKNOWN"), date: dateFromRoot(root, posting), snippet: text.slice(0, 240), listingText: text.slice(0, 4000), locationText: clean(root.querySelector('[class*="location" i],[data-testid*="location" i]')?.textContent || ""), promoted: /\b(?:запропоновані|предложенные|sponsored|promoted)\b/i.test(text), structuredDetail: postingSnapshot(posting) });
    }
    const next = [document.head.querySelector('link[rel="next"]')?.href, document.querySelector('a[rel="next"]')?.href, ...[...document.querySelectorAll("a[href]")].filter((item) => /^(?:наступн\w*|следующ\w*|next|›|»|→)$/i.test(clean(item.getAttribute("aria-label") || item.getAttribute("title") || item.textContent))).map((item) => item.href)].find(Boolean) || null;
    const controls = [...document.querySelectorAll('button, [role="button"], [role="option"], label, [aria-selected="true"], [aria-checked="true"]')].map((node) => ({ text: clean(node.getAttribute("aria-label") || node.getAttribute("title") || node.textContent), selected: node.getAttribute("aria-selected") === "true" || node.getAttribute("aria-checked") === "true" || /(?:active|selected|checked)/i.test(String(node.className || "")) })).filter((item) => item.text && /(?:remote|віддален|удален|дата\s+(?:публікації|публикации)|date\s+(?:posted|publication)|24\s*(?:год|час|hour)|3\s*(?:дн|дні|дня|day)|7\s*(?:дн|дні|дня|day)|сьогодні|сегодня|today)/i.test(item.text)).slice(0, 60);
    const body = clean(document.body.innerText);
    return { direct, carriers, discoveredIds: [...new Set([...direct.map((item) => idOf(item.url)), ...carriers.map((item) => item.id)].filter(Boolean))], next, resolvedUrl: location.href, dateParam: new URL(location.href).searchParams.get("date") || "", remotePath: location.pathname, remoteVisible: /(?:віддалена\s+робота|віддалено|remote)/i.test(body), controls, empty: /(?:вакансій не знайдено|вакансии не найдены|no jobs found|сторінку не знайдено|страница не найдена)/i.test(body), ready: direct.length > 0 || carriers.length > 0 || /(?:вакансій не знайдено|вакансии не найдены|no jobs found|сторінку не знайдено|страница не найдена)/i.test(body) };
  });
}

function filterEvidence(sample, freshness) {
  const generic = (sample.controls || []).find((item) => /(?:дата\s+(?:публікації|публикации)|date\s+(?:posted|publication))/i.test(item.text));
  const remote = (sample.controls || []).find((item) => /remote|віддален|удален/i.test(item.text));
  const remoteRoute = remotePathSegment(sample.resolvedUrl);
  let legacyRemoteQuery = false;
  try { legacyRemoteQuery = [...new URL(sample.resolvedUrl).searchParams.keys()].some((key) => key.toLowerCase() === "l"); } catch {}
  const freshnessProven = String(sample.dateParam) === String(freshness.param) && Boolean(generic);
  const remoteProven = Boolean(remoteRoute) && !legacyRemoteQuery;
  const proof = freshnessProven
    ? (remoteProven
      ? `remote-route:${remoteRoute}; date=${freshness.param}; date-control:${compact(generic.text, 120)}; remote-control:${compact(remote?.text || "location-path", 120)}`
      : `date=${freshness.param}; date-control:${compact(generic.text, 120)}; remote-unproven`)
    : null;
  return {
    proof,
    freshnessProven,
    remoteProven,
    dateParam: String(sample.dateParam || ""),
    dateControl: compact(generic?.text || "", 160),
    remoteRoute,
    remoteControl: compact(remote?.text || "", 160),
    legacyRemoteQuery,
  };
}

async function grow(tab, before, deadline) {
  const action = await tab.playwright.evaluate(() => { window.scrollTo(0, document.body.scrollHeight); return "scrolled"; });
  let latest = (await discover(tab)).discoveredIds.length; let stable = 0;
  while (performance.now() < deadline && stable < 3) {
    if (latest > before) return { grew: true, action, count: latest };
    await tab.playwright.waitForTimeout(350); const current = (await discover(tab)).discoveredIds.length;
    stable = current === latest ? stable + 1 : 0; latest = current;
    if (stable === 1) await tab.playwright.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  }
  return { grew: latest > before, action, count: latest };
}

export function createJoobleAdapter({ appendDiagnostic = () => {} } = {}) {
  const carrierCache = new Map();
  const detailCache = new Map();
  const metrics = { listingNavigations: 0, carrierNavigations: 0, detailNavigations: 0, challengeCount: 0, structuredStateDetails: 0, listingStateDetails: 0, uiFallbackDetails: 0, directJdpAttempts: 0 };
  const rememberDiscovery = (item, id) => {
    carrierCache.set(id, item.sourceUrl || item.url);
    const snapshot = item.structuredDetail;
    if (snapshot && String(snapshot.detail_text || "").length >= 800) detailCache.set(id, snapshot);
  };

  async function collectList({ tab, url, route, deadline, freshness, list, allowUnprovenRemote = false, allowUrlOnlyFreshness = false }) {
    let requestedUrl = "";
    if (!list.started) {
      requestedUrl = withFreshness(url, freshness, { requireRemoteProof: !allowUnprovenRemote });
      await tab.goto(requestedUrl); metrics.listingNavigations += 1; list.started = true; list.url = null;
    } else if (list.url) {
      requestedUrl = withFreshness(list.url, freshness, { requireRemoteProof: !allowUnprovenRemote });
      await tab.goto(requestedUrl); metrics.listingNavigations += 1; list.url = null;
    }
    let sample = await poll(tab, deadline, () => discover(tab), (value) => value.ready, `${SOURCE}/${route}: listing ready`);
    const evidence = filterEvidence(sample, freshness);
    const freshnessUrlProven = evidence.dateParam === String(freshness.param);
    const freshnessAccepted = evidence.freshnessProven || (allowUrlOnlyFreshness && freshnessUrlProven);
    appendDiagnostic("route-filter-evidence", {
      route,
      requested_url: requestedUrl || url,
      resolved_url: sample.resolvedUrl || (await tab.url()) || "",
      date_param: evidence.dateParam,
      freshness_param: String(freshness.param),
      date_control: evidence.dateControl,
      remote_route: evidence.remoteRoute,
      remote_control: evidence.remoteControl,
      legacy_remote_query: evidence.legacyRemoteQuery,
      freshness_proven: evidence.freshnessProven,
      freshness_url_proven: freshnessUrlProven,
      remote_proven: evidence.remoteProven,
      allow_unproven_remote: Boolean(allowUnprovenRemote),
      allow_url_only_freshness: Boolean(allowUrlOnlyFreshness),
    });
    if (!freshnessAccepted) throw new JoobleAdapterError(`${SOURCE}/${route}: freshness filter is not proven by URL and UI`);
    if (!allowUnprovenRemote && !evidence.remoteProven) throw new JoobleAdapterError(`${SOURCE}/${route}: Remote filter is not proven by canonical URL`);
    const acceptedProof = evidence.proof || (freshnessUrlProven
      ? `date=${freshness.param}; date-control:unproven; ${evidence.remoteProven ? `remote-route:${evidence.remoteRoute}` : "remote-unproven"}; calibration-url-only`
      : null);
    list.filterProof ??= acceptedProof;
    if (list.filterMode !== "UNFILTERED_LOCATION") list.filterMode = evidence.remoteProven ? "FILTERED_REMOTE" : "UNFILTERED_LOCATION";
    if (list.freshnessMode !== "URL_PARAM_ONLY") list.freshnessMode = evidence.freshnessProven ? "URL_AND_UI" : "URL_PARAM_ONLY";
    const resolvedUrl = canonical((await tab.url()) || sample.resolvedUrl);
    const active = new URL(resolvedUrl).searchParams;
    const hasLegacyRemoteQuery = [...active.keys()].some((key) => key.toLowerCase() === "l");
    if (active.get("date") !== String(freshness.param)) throw new JoobleAdapterError(`${SOURCE}/${route}: resolved URL lost freshness date=${freshness.param}`);
    if (!allowUnprovenRemote && (!hasRemotePath(resolvedUrl) || hasLegacyRemoteQuery)) throw new JoobleAdapterError(`${SOURCE}/${route}: resolved URL lost Remote location path or retained legacy l=Remote`);
    const discovered = [...(sample.carriers || []), ...(sample.direct || []).map((item) => ({ ...item, sourceUrl: item.url, id: directId(item.url), listingText: item.snippet, locationText: "" }))];
    const fresh = discovered.filter((item) => !list.seen.has(item.id)).map((item) => {
      const jdpUrl = `https://ua.jooble.org/jdp/${item.id}`;
      rememberDiscovery(item, item.id);
      return card(jdpUrl, item.title, item.company, item.date, item.listingText || item.snippet, item.promoted, { ...item, originUrl: resolvedUrl });
    });
    const beforeIds = [...list.seen];
    const afterIds = [...new Set([...beforeIds, ...fresh.map((item) => directId(item.url))])];
    fresh.forEach((item) => list.seen.add(directId(item.url)));
    let next = sample.next ? canonical(withFreshness(sample.next, freshness, { requireRemoteProof: !allowUnprovenRemote })) : null;
    if (next === resolvedUrl || list.visitedPages.has(next)) next = null;
    if (next) { list.pages.push({ step: list.pages.length + 1, resolved_url: resolvedUrl, next, before_ids: beforeIds, after_ids: afterIds, newly_discovered_ids: fresh.map((item) => directId(item.url)), continuation_evidence: "next-link", visible_cards: fresh.length, cards: fresh }); list.visitedPages.add(resolvedUrl); appendDiagnostic("route-page", { route, step: list.pages.length, cards: fresh.length, next, before_ids: beforeIds, after_ids: afterIds, newly_discovered_ids: fresh.map((item) => directId(item.url)), freshness, filter_proof: list.filterProof, filter_mode: list.filterMode, cards: fresh }); list.url = next; return { done: false, list }; }
    const growth = await grow(tab, sample.discoveredIds.length, Math.min(deadline, performance.now() + 2200));
    if (growth.grew) { const afterGrowth = await discover(tab); const grown = [...(afterGrowth.carriers || []), ...(afterGrowth.direct || [])].filter((item) => !list.seen.has(item.id || directId(item.url))).map((item) => { const id = item.id || directId(item.url); rememberDiscovery(item, id); return card(`https://ua.jooble.org/jdp/${id}`, item.title, item.company, item.date, item.listingText || item.snippet, item.promoted, { ...item, originUrl: resolvedUrl }); }); grown.forEach((item) => list.seen.add(directId(item.url))); const allAfter = [...new Set([...afterIds, ...grown.map((item) => directId(item.url))])]; list.pages.push({ step: list.pages.length + 1, resolved_url: resolvedUrl, next: "LOAD_MORE", before_ids: afterIds, after_ids: allAfter, newly_discovered_ids: grown.map((item) => directId(item.url)), continuation_evidence: "scroll-growth-and-rediscovery", visible_cards: grown.length, cards: grown }); appendDiagnostic("route-page", { route, step: list.pages.length, cards: grown.length, next: "LOAD_MORE", before_ids: afterIds, after_ids: allAfter, newly_discovered_ids: grown.map((item) => directId(item.url)), freshness, filter_proof: list.filterProof, filter_mode: list.filterMode, cards: grown }); return { done: false, list }; }
    list.pages.push({ step: list.pages.length + 1, resolved_url: resolvedUrl, next: null, before_ids: beforeIds, after_ids: afterIds, newly_discovered_ids: fresh.map((item) => directId(item.url)), continuation_evidence: "next-link-absent-and-zero-growth", visible_cards: fresh.length, cards: fresh }); appendDiagnostic("route-terminal", { route, step: list.pages.length, cards: fresh.length, next: null, before_ids: beforeIds, after_ids: afterIds, newly_discovered_ids: fresh.map((item) => directId(item.url)), reason: "no-continuation-and-zero-growth", freshness, filter_proof: list.filterProof, filter_mode: list.filterMode, cards: fresh }); return { done: true, list };
  }

  async function collectDetail(tab, url, deadline, fallback = {}) {
    const id = directId(url);
    const cached = detailCache.get(id);
    if (cached && (cached.title || fallback.title) && (cached.company || fallback.company) && String(cached.detail_text || "").length >= 800) {
      metrics.structuredStateDetails += 1; metrics.listingStateDetails += 1;
      appendDiagnostic("detail-listing-state-hit", { id, detail_chars: String(cached.detail_text || "").length });
      return { url: `https://ua.jooble.org/jdp/${id}`, final_url: `https://ua.jooble.org/jdp/${id}`, title: compact(cached.title || fallback.title), company: compact(cached.company || fallback.company), published_date: compact(cached.published_date || fallback.date || "UNKNOWN", 120), location_text: compact(cached.location_text || fallback.location_text || "", 500), detail_text: compact(cached.detail_text, DETAIL_TEXT_LIMIT) };
    }
    const carrier = fallback.carrier_url || carrierCache.get(id);
    if (!carrier) throw new JoobleAdapterError(`Jooble carrier cache missing for JDP id ${id}; controlled recovery required`);
    const currentUrl = (await tab.url()) || "";
    if (carrierId(currentUrl) !== id) { await tab.goto(carrier); metrics.carrierNavigations += 1; metrics.detailNavigations += 1; }
    else appendDiagnostic("detail-resume", { id, current_url: currentUrl });
    let detail;
    try { detail = await poll(tab, Math.min(deadline, performance.now() + 10_000), () => tab.playwright.evaluate(({ url, limit }) => {
      const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
      const idOf = (value) => String(value || "").match(/\/(?:jdp|desc)\/(-?\d+)/)?.[1] || "";
      const body = clean(document.body.innerText);
      const titleText = clean(document.title);
      if (/performing security verification|security verification|captcha|are you human|перевірка безпеки|проверка безопасности/i.test(`${titleText} ${body.slice(0, 1200)}`)) {
        return { challenge: true, url, final_url: "", title: titleText, company: "", published_date: "", location_text: "", detail_text: body.slice(0, limit), scope_ok: false, scope_chars: 0, foreign_job_links: 0 };
      }
      const targetId = idOf(url);
      let posting = null;
      const visit = (value) => {
        if (posting) return;
        if (Array.isArray(value)) return value.forEach(visit);
        if (!value || typeof value !== "object") return;
        const types = Array.isArray(value["@type"]) ? value["@type"] : [value["@type"]];
        const raw = typeof value.identifier === "object" ? value.identifier?.value : value.identifier;
        const candidate = idOf(value.url) || String(raw || "").match(/^-?\d+$/)?.[0] || "";
        if (types.some((item) => /JobPosting/i.test(String(item || ""))) && candidate === targetId) posting = value;
        if (Array.isArray(value["@graph"])) value["@graph"].forEach(visit);
      };
      for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
        try { visit(JSON.parse(script.textContent || "")); } catch {}
      }
      const jdp = [...document.querySelectorAll('a[href*="/jdp/"],link[href*="/jdp/"]')]
        .map((node) => node.href)
        .find((value) => idOf(value) === targetId) || url;
      const h1 = document.querySelector("h1");
      const title = clean(posting?.title || h1?.textContent);
      const company = clean(posting?.hiringOrganization?.name || h1?.parentElement?.parentElement?.querySelector('[class*="company" i]')?.textContent);
      let scope = null;
      if (!posting && h1) {
        let node = h1;
        while (node && node !== document.body) {
          const text = clean(node.innerText);
          const foreignJobLinks = [...node.querySelectorAll('a[href*="/jdp/"],a[href*="/desc/"]')]
            .map((link) => idOf(link.href))
            .filter((id) => id && id !== targetId).length;
          if (text.length >= 300 && foreignJobLinks <= 1) {
            scope = { text, foreignJobLinks };
            break;
          }
          node = node.parentElement;
        }
      }
      const description = clean(posting?.description || scope?.text || "");
      const location = clean([posting?.jobLocationType, posting?.jobLocation?.address?.addressLocality, posting?.jobLocation?.address?.addressRegion].filter(Boolean).join(" · "));
      return {
        challenge: false,
        url,
        final_url: jdp,
        title,
        company,
        published_date: clean(posting?.datePosted || document.querySelector("time[datetime]")?.getAttribute("datetime") || "UNKNOWN"),
        location_text: location,
        detail_text: description.slice(0, limit),
        structured: Boolean(posting),
        scope_ok: Boolean(posting || scope),
        scope_chars: description.length,
        foreign_job_links: scope?.foreignJobLinks || 0,
      };
    }, { url, limit: DETAIL_TEXT_LIMIT }), (value) => value.challenge || Boolean(
      value.scope_ok
      && (value.title || fallback.title)
      && (value.company || fallback.company)
      && value.detail_text.length >= 120
    ), "Jooble detail readiness", true); }
    catch (error) {
      if (error instanceof JoobleBudgetError) {
        const latest = error.latest || {};
        appendDiagnostic("detail-budget-yield", {
          id,
          title_seen: Boolean(latest.title),
          company_seen: Boolean(latest.company),
          detail_chars: String(latest.detail_text || "").length,
          scope_ok: Boolean(latest.scope_ok),
          scope_chars: Number(latest.scope_chars || 0),
          foreign_job_links: Number(latest.foreign_job_links || 0),
        });
      }
      throw error;
    }
    if (detail.challenge) { metrics.challengeCount += 1; throw new JoobleChallengeError(`Jooble security verification for JDP id ${id}`); }
    if (directId(detail.url) !== directId(detail.final_url)) throw new JoobleAdapterError("Jooble detail identity mismatch");
    if (detail.structured) metrics.structuredStateDetails += 1;
    else {
      metrics.uiFallbackDetails += 1;
      appendDiagnostic("detail-dom-scope", {
        id,
        detail_chars: Number(detail.scope_chars || String(detail.detail_text || "").length),
        foreign_job_links: Number(detail.foreign_job_links || 0),
      });
    }
    if (!detail.title || /^ua\.jooble\.org$/i.test(detail.title)) detail.title = fallback.title || detail.title;
    if (!detail.company || /^ua\.jooble\.org$/i.test(detail.company)) detail.company = fallback.company || detail.company;
    if (!detail.published_date || detail.published_date === "UNKNOWN") detail.published_date = fallback.date || detail.published_date;
    if (!detail.title || !detail.company) throw new JoobleAdapterError("Jooble detail identity fields are empty");
    return { url: `https://ua.jooble.org/jdp/${id}`, final_url: `https://ua.jooble.org/jdp/${id}`, title: compact(detail.title), company: compact(detail.company), published_date: compact(detail.published_date, 120), location_text: compact(detail.location_text, 500), detail_text: compact(detail.detail_text, DETAIL_TEXT_LIMIT) };
  }

  async function recoverDetail(tab, fallback) {
    const origin = fallback.origin_url || fallback.route_url;
    if (!origin) throw new JoobleAdapterError("challenge recovery has no originating SERP");
    await tab.goto(origin);
    const id = directId(fallback.url);
    await poll(tab, performance.now() + 8_000, () => tab.playwright.evaluate(({ id }) => {
      const node = [...document.querySelectorAll('a[href*="/desc/"]')].find((item) => String(item.href).includes(`/desc/${id}`));
      if (!node) return false;
      node.click();
      return true;
    }, { id }), Boolean, "Jooble challenge UI recovery");
  }

  return Object.freeze({ source: joobleSource, metrics, collectList, collectDetail, recoverDetail, carrierCache });
}

export const joobleAdapter = createJoobleAdapter();
