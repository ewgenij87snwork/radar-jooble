# RADAR-JOOBLE browser fallback

This path is preserved for explicit fallback/calibration only. Normal discovery uses the official Jooble REST API.

Work only from the physical `radar-jooble` folder and read `AGENTS.md` first.

The bootstrap attaches an already-running Chrome extension surface from the OpenAI browser plugin. It does not start Chrome from shell and does not create a new profile/window.

```js
// @exec: {"max_output_tokens": 20000}
const result = await tools.mcp__node_repl__js({
  title: "RADAR-JOOBLE browser setup",
  timeout_ms: 30000,
  code: `if (globalThis.agent?.browsers == null) {
    const { readdirSync, existsSync } = await import("node:fs");
    const { join } = await import("node:path");
    const { homedir } = await import("node:os");
    const browserPluginRoot = join(homedir(), ".codex", "plugins", "cache", "openai-bundled", "browser");
    const browserClientPath = readdirSync(browserPluginRoot, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name)
      .filter((version) => existsSync(join(browserPluginRoot, version, "scripts/browser-client.mjs")))
      .sort((a, b) => b.localeCompare(a, undefined, { numeric: true }))[0];
    if (browserClientPath == null) throw new Error("No installed browser plugin contains scripts/browser-client.mjs");
    const { setupBrowserRuntime } = await import(join(browserPluginRoot, browserClientPath, "scripts/browser-client.mjs"));
    const runtimeAgent = await setupBrowserRuntime({ globals: globalThis });
    globalThis.agent ??= runtimeAgent;
  }
  if (globalThis.browser == null) {
    const surfaces = await globalThis.agent.browsers.list();
    const chromeSurfaces = surfaces.filter((surface) => surface.family === "chrome" && surface.type === "extension");
    if (chromeSurfaces.length === 0) throw new Error("No Chrome extension surface found");
    let chosen = chromeSurfaces[0];
    if (chromeSurfaces.length > 1) {
      const defaultBrowser = await globalThis.agent.browsers.getDefault();
      const defaultBrowserId = defaultBrowser.browserId ?? defaultBrowser.id;
      chosen = chromeSurfaces.find((surface) => String(surface.id) === String(defaultBrowserId));
      if (chosen == null) throw new Error("Multiple Chrome extension surfaces exist and the default surface is not one of them");
    }
    globalThis.browser = await globalThis.agent.browsers.get(chosen.id);
    await globalThis.browser.nameSession("RADAR-JOOBLE");
    nodeRepl.write((await browser.documentation()).replace(/(["']?credential["']?\\s*(?:=|:)\\s*)([^\\s,}\\]\\r\\n]+)/gi, "$1[REDACTED]"));
  }`,
});
for (const item of result.content ?? []) if (item.type === "text") text(item.text);
```

Choose `startArgs`:
- normal browser fallback: `[]`
- calibration TEST: `["--test-live", "--freshness", "3d"]`

Repeat the same runner wrapper until terminal status:

```js
// @exec: {"yield_time_ms":30000,"max_output_tokens":4000}
const result = await tools.mcp__node_repl__js({
  title: "RADAR-JOOBLE",
  timeout_ms: 30000,
  code: `const { join } = await import("node:path");
  const { pathToFileURL } = await import("node:url");
  const { realpathSync, existsSync } = await import("node:fs");
  const radarRoot = realpathSync(".");
  const runnerPath = join(radarRoot, "browser-runner.mjs");
  if (!existsSync(runnerPath)) throw new Error(`browser-runner.mjs not found under ${radarRoot}`);
  globalThis.radarJooble ??= (await import(pathToFileURL(runnerPath).href)).createRunner({
    browser,
    startArgs: ["--test-live", "--freshness", "3d"],
  });
  nodeRepl.write(await globalThis.radarJooble.run());`,
});
for (const item of result.content ?? []) if (item.type === "text") text(item.text);
```

`CONTINUE` / `PROGRESS` → repeat the same runner wrapper. `BLOCKED` → record the reason and repeat once so the runner can finalize PARTIAL diagnostics. `RUNNER_ERROR` → stop and preserve the active run. `DONE` → return the generated Markdown/JSONL (and calibration bundle in TEST) and stop browser work.
