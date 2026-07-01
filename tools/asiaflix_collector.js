/**
 * AsiaFlix URL Collector  (v1 — collector-first support for asiaflix.net / .in)
 *
 * Same idea as tools/browser_collector.js (kisskh), adapted for AsiaFlix:
 * AsiaFlix is an Angular SPA whose content API (https://api.asiaflix.net/v1)
 * is behind Firebase auth. Your browser is already logged in, so instead of
 * replicating that auth we capture the *resolved* stream (.m3u8/.mp4) and
 * subtitle (.vtt/.srt) URLs straight from your session and write the same
 * manifest kissget already understands — then:
 *
 *   kissget dl --from-manifest <file>_manifest.json -o "C:\Users\you\Downloads"
 *
 * The manifest is tagged  "site": "asiaflix"  so the downloader sends an
 * AsiaFlix Referer to the CDN.
 *
 * Workflow:
 *   1. Log in and open your show on https://asiaflix.net (or .in)
 *   2. DevTools (F12) → Console → paste this whole script → Enter
 *   3. Open each episode and press Play until the video starts (AsiaFlix
 *      resolves the stream lazily, so Play is usually required here)
 *   4. Check the "Episode #" box in the overlay is correct for the episode you
 *      are on (it auto-detects from the URL when it can; edit it if wrong)
 *   5. Click Copy or Download when every episode shows a stream ✓
 *
 * NOTE (v1): AsiaFlix's exact URL/response shapes vary. This build logs every
 * stream/subtitle candidate it sees to the console — if an episode doesn't
 * capture, copy those log lines back so the hooks can be tuned.
 */
(function () {
  const STORAGE_KEY = "asiaflix_collector";
  const LOG = (msg, css, extra) =>
    console.log(`%c[asiaflix-collector] ${msg}`, css || "color:#40c4ff", extra ?? "");

  // ── Storage ───────────────────────────────────────────────────────────────
  function loadData() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY)) || { drama: "", manualEp: null, episodes: {} };
    } catch {
      return { drama: "", manualEp: null, episodes: {} };
    }
  }
  function saveData(data) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  }

  // ── Episode / title detection ──────────────────────────────────────────────
  // AsiaFlix routing isn't fully known; try several common patterns, and fall
  // back to the manual "Episode #" the user sets in the overlay.
  const EP_PATTERNS = [
    /[?&](?:ep|episode)=(\d+(?:\.\d+)?)/i,
    /\/(?:episode|ep|e|watch)[\/-](\d+(?:\.\d+)?)(?:[\/?#.]|$)/i,
    /[-_](?:episode|ep)[-_]?(\d+(?:\.\d+)?)(?:[\/?#.]|$)/i,
    /\bepisode\D{0,3}(\d+(?:\.\d+)?)/i,
  ];
  function episodeFromUrl(u) {
    const s = u || window.location.href;
    for (const re of EP_PATTERNS) {
      const m = s.match(re);
      if (m) return parseFloat(m[1]);
    }
    return null;
  }
  function currentEpisode() {
    const fromUrl = episodeFromUrl();
    if (fromUrl !== null) return fromUrl;
    const data = loadData();
    return data.manualEp != null ? parseFloat(data.manualEp) : null;
  }
  function detectTitle() {
    // Prefer a URL slug segment; else fall back to the page <title>.
    const parts = window.location.pathname.split("/").filter(Boolean);
    const skip = new Set(["home", "watch", "show", "shows", "drama", "e", "v", "d", "embed", "episode", "ep"]);
    for (const p of parts) {
      if (!skip.has(p.toLowerCase()) && /[a-z]/i.test(p) && !/^\d+$/.test(p)) {
        return decodeURIComponent(p).replace(/[-_]+/g, "-").replace(/^-+|-+$/g, "");
      }
    }
    return (document.title || "").split(/[|\-–—]/)[0].trim().replace(/\s+/g, "-");
  }

  // ── Candidate classification ────────────────────────────────────────────────
  const isStreamUrl = (u) => typeof u === "string" && /\.(m3u8|mp4)(\?|#|$)/i.test(u);
  const isSubtitleUrl = (u) => typeof u === "string" && /\.(vtt|srt|ass)(\?|#|$)/i.test(u);

  // ── Capture ─────────────────────────────────────────────────────────────────
  function ensureEp(data, epNum) {
    if (!data.episodes[epNum]) data.episodes[epNum] = { number: epNum, subtitles: [] };
    if (!data.episodes[epNum].subtitles) data.episodes[epNum].subtitles = [];
    return data.episodes[epNum];
  }

  function captureStream(url, epNumHint) {
    const epNum = epNumHint != null ? epNumHint : currentEpisode();
    if (epNum === null) {
      LOG("saw a stream but no episode # yet — set 'Episode #' in the overlay:", "color:orange", url.slice(0, 120));
      return;
    }
    const data = loadData();
    const title = detectTitle();
    if (title) data.drama = title;
    const ep = ensureEp(data, epNum);
    // Prefer HLS (.m3u8) over a progressive .mp4 if both show up.
    const preferNew = !ep.stream_url || (/\.mp4/i.test(ep.stream_url) && /\.m3u8/i.test(url));
    if (preferNew && ep.stream_url !== url) {
      ep.stream_url = url;
      saveData(data);
      LOG(`✅ E${epNum} stream captured`, "color:lime;font-weight:bold", url.slice(0, 100) + (url.length > 100 ? "…" : ""));
      renderOverlay();
    }
  }

  function captureSubtitle(url, lang, label, epNumHint) {
    const epNum = epNumHint != null ? epNumHint : currentEpisode();
    if (epNum === null || !url) return;
    const data = loadData();
    const ep = ensureEp(data, epNum);
    if (ep.subtitles.some((s) => s.src === url)) return; // dedupe
    ep.subtitles.push({ lang: lang || "", label: label || lang || "", src: url });
    saveData(data);
    LOG(`✅ E${epNum} subtitle captured (${lang || "?"})`, "color:lime;font-weight:bold", url.slice(0, 90));
    renderOverlay();
  }

  // Recursively walk any JSON response and pull out stream + subtitle URLs,
  // pairing subtitle URLs with the nearest language/label fields on their object.
  function scanJson(node) {
    if (!node || typeof node !== "object") return;
    if (Array.isArray(node)) {
      node.forEach(scanJson);
      return;
    }
    // Collect string values on this object, and any language/label hints.
    const lang =
      node.languageCode || node.lang || node.language || node.srclang || node.code || "";
    const label = node.label || node.name || node.title || "";
    for (const v of Object.values(node)) {
      if (typeof v === "string") {
        if (isStreamUrl(v)) captureStream(v);
        else if (isSubtitleUrl(v)) captureSubtitle(v, lang, label);
      }
    }
    Object.values(node).forEach(scanJson);
  }

  // ── PerformanceObserver: catch stream/subtitle resource loads directly ──────
  if (!window.__asiaflix_po_installed) {
    window.__asiaflix_po_installed = true;
    try {
      const po = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          const url = entry.name;
          if (url.includes(window.location.hostname)) continue;
          if (isStreamUrl(url)) {
            LOG("candidate stream (resource):", "color:#888", url.slice(0, 120));
            captureStream(url);
          } else if (isSubtitleUrl(url)) {
            LOG("candidate subtitle (resource):", "color:#888", url.slice(0, 120));
            captureSubtitle(url, "", "");
          }
        }
      });
      po.observe({ type: "resource", buffered: true });
      LOG("PerformanceObserver installed (buffered — already-loaded URLs captured too).", "color:lime;font-weight:bold");
    } catch (e) {
      console.warn("[asiaflix-collector] PerformanceObserver unavailable:", e);
    }
  }

  // ── fetch hook: scan AsiaFlix API responses for streams + subtitles ─────────
  if (!window.__asiaflix_fetch_hooked) {
    window.__asiaflix_fetch_hooked = true;
    const _fetch = window.fetch;
    window.fetch = async function (...args) {
      const res = await _fetch.apply(this, args);
      const url = (typeof args[0] === "string" ? args[0] : args[0]?.url) || "";
      if (/asiaflix\.(net|in)/i.test(url) || /\/v1\//.test(url)) {
        res.clone().json().then((body) => {
          LOG("scanned API response:", "color:#888", url.slice(0, 120));
          scanJson(body);
        }).catch(() => {});
      }
      return res;
    };
    LOG("fetch hook installed.", "color:lime;font-weight:bold");
  }

  // ── XHR hook: Angular HttpClient uses XHR ───────────────────────────────────
  if (!window.__asiaflix_xhr_hooked) {
    window.__asiaflix_xhr_hooked = true;
    const _open = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (method, url, ...rest) {
      this.__af_url = String(url);
      return _open.apply(this, [method, url, ...rest]);
    };
    const _send = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function (...args) {
      const url = this.__af_url || "";
      if (/asiaflix\.(net|in)/i.test(url) || /\/v1\//.test(url)) {
        this.addEventListener("load", () => {
          try {
            scanJson(JSON.parse(this.responseText));
          } catch {}
        });
      }
      return _send.apply(this, args);
    };
    LOG("XHR hook installed.", "color:lime;font-weight:bold");
  }

  // ── Manifest ────────────────────────────────────────────────────────────────
  function buildManifest() {
    const data = loadData();
    const episodes = Object.values(data.episodes)
      .sort((a, b) => a.number - b.number)
      .map((ep) => ({ number: ep.number, stream_url: ep.stream_url || null, subtitles: ep.subtitles || [] }));
    return { drama: data.drama, site: "asiaflix", episodes };
  }

  // ── Overlay UI ──────────────────────────────────────────────────────────────
  function renderOverlay() {
    const data = loadData();
    const eps = Object.values(data.episodes);
    const withStream = eps.filter((e) => e.stream_url).length;
    const withSubs = eps.filter((e) => e.subtitles && e.subtitles.length > 0).length;
    const curEp = currentEpisode();

    let overlay = document.getElementById("__asiaflix_overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "__asiaflix_overlay";
      overlay.style.cssText = [
        "position:fixed", "top:16px", "right:16px", "z-index:2147483647",
        "background:#0d0d0d", "color:#e0e0e0", "font-family:monospace", "font-size:13px",
        "border:1px solid #333", "border-radius:10px", "padding:14px 18px", "min-width:290px",
        "box-shadow:0 6px 30px rgba(0,0,0,0.7)", "line-height:1.6",
      ].join(";");
      document.body.appendChild(overlay);
    }

    overlay.innerHTML = `
      <div style="font-weight:bold;color:#ff5252;font-size:14px;margin-bottom:8px">🎬 AsiaFlix Collector</div>
      <div>Show: <span style="color:#ffd740">${data.drama || "(not detected yet)"}</span></div>
      <div style="margin:6px 0">Episode #:
        <input id="__af_ep" value="${curEp != null ? curEp : ""}" placeholder="auto"
          style="width:60px;background:#1a1a1a;color:#fff;border:1px solid #444;border-radius:4px;padding:2px 6px" />
        <span style="color:#888;font-size:11px">(auto from URL; edit if wrong)</span>
      </div>
      <div>Episodes: <span style="color:#40c4ff">${eps.length}</span>
           &nbsp;·&nbsp; Streams: <span style="color:#40c4ff">${withStream}</span>
           &nbsp;·&nbsp; Subs: <span style="color:#40c4ff">${withSubs}</span></div>
      <div style="color:#888;font-size:11px;margin:8px 0 10px">
        Open an episode and press <b>Play</b> until video starts.<br>Watch the console for candidates.
      </div>
      <div style="display:flex;gap:8px">
        <button id="__af_copy" style="flex:1;background:#00897b;color:#fff;border:none;padding:7px 10px;border-radius:6px;cursor:pointer;font-weight:bold">📋 Copy</button>
        <button id="__af_download" style="flex:1;background:#1565c0;color:#fff;border:none;padding:7px 10px;border-radius:6px;cursor:pointer;font-weight:bold">💾 Download</button>
        <button id="__af_clear" style="background:#b71c1c;color:#fff;border:none;padding:7px 10px;border-radius:6px;cursor:pointer">🗑</button>
        <button id="__af_close" style="background:#333;color:#aaa;border:none;padding:7px 10px;border-radius:6px;cursor:pointer">✕</button>
      </div>
    `;

    document.getElementById("__af_ep").onchange = function () {
      const d = loadData();
      d.manualEp = this.value.trim() === "" ? null : this.value.trim();
      saveData(d);
      LOG(`Episode # set to ${d.manualEp ?? "(auto)"}`, "color:yellow");
    };

    document.getElementById("__af_copy").onclick = function () {
      const json = JSON.stringify(buildManifest(), null, 2);
      navigator.clipboard.writeText(json).then(() => {
        this.textContent = "✅ Copied!";
        setTimeout(() => (this.textContent = "📋 Copy"), 2500);
        console.log(json);
      }).catch(() => {
        console.log(json);
        alert("Clipboard blocked — manifest printed to console.");
      });
    };

    document.getElementById("__af_download").onclick = function () {
      const manifest = buildManifest();
      const json = JSON.stringify(manifest, null, 2);
      const safe =
        (manifest.drama || "asiaflix").replace(/[\\/:*?"<>|]+/g, "_").replace(/-+/g, "-").replace(/^[-_.]+|[-_.]+$/g, "") ||
        "asiaflix";
      const blob = new Blob([json], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${safe}_manifest.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      this.textContent = "✅ Saved!";
      setTimeout(() => (this.textContent = "💾 Download"), 2500);
    };

    document.getElementById("__af_clear").onclick = function () {
      if (confirm("Clear all collected AsiaFlix data?")) {
        saveData({ drama: "", manualEp: null, episodes: {} });
        renderOverlay();
        LOG("Data cleared.", "color:orange");
      }
    };

    document.getElementById("__af_close").onclick = function () {
      overlay.remove();
      LOG("Overlay hidden — collector still active. Re-run the script to show it again.", "color:yellow");
    };
  }

  renderOverlay();
  LOG("AsiaFlix collector active. Open an episode and press Play.", "color:lime;font-weight:bold");
})();
