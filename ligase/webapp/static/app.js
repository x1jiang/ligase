/* Ligase Biomedical & NIAGADS Co-Scientist Web Portal Client
 * Zero external CDN dependencies · Multi-tab accessible workspace · Interactive SVG Mindmap · Live NIAGADS Open Access API v2.0 console.
 */

(() => {
  "use strict";

  // ── Client Workspace ID (isolates threads/uploads per browser) ────────────
  function getClientId() {
    const key = "ligase_client_id";
    try {
      let id = localStorage.getItem(key);
      if (!id || id.length < 12) {
        id =
          "cli_" +
          (crypto.randomUUID
            ? crypto.randomUUID().replace(/-/g, "").slice(0, 20)
            : Math.random().toString(36).slice(2) + Date.now().toString(36));
        localStorage.setItem(key, id);
      }
      return id;
    } catch {
      return "local_default";
    }
  }

  const CLIENT_ID = getClientId();

  const TAB_TITLES = {
    studio: "Research Studio | Ligase · Biomedical & NIAGADS Co-Scientist",
    mindmap: "Capabilities Mindmap | Ligase · Biomedical & NIAGADS Co-Scientist",
    "niagads-api": "NIAGADS Open Access API | Ligase · Biomedical & NIAGADS Co-Scientist",
    usage: "Usage & Volume Ledger | Ligase · Biomedical & NIAGADS Co-Scientist",
    feedback: "Comments & Feedback | Ligase · Biomedical & NIAGADS Co-Scientist",
  };

  const OA_PRESETS = [
    { label: "🏛️ ADSP R5 (58.5k) Power & NIH DAR: ABCA7", action: "adsp_r5_power_dar", target: "ABCA7", loc: "staar_o_burden|case_control_ad", flank: 0 },
    { label: "🏛️ ADSP R5 SORL1 Rare Burden + CSF ATN DAR", action: "adsp_r5_power_dar", target: "SORL1", loc: "staar_o_burden|fluid_biomarkers_atn", flank: 0 },
    { label: "🔬 BIN1 TAD ColocBoost + MESuSiE", action: "colocboost_mesusie", target: "BIN1", loc: "ALL", flank: 0 },
    { label: "🧬 EGFR Distal +243 kb TAD Loop", action: "colocboost_mesusie", target: "EGFR", loc: "ALL", flank: 0 },
    { label: "🛡️ APOEε4 FN1 Resilience + XWAS + SEA-AD", action: "resilience_xwas_seaad", target: "APOE", loc: "e4/e4", flank: 0 },
    { label: "🎯 BIN1 Fine-Map + FunGen Coloc", action: "finemap_coloc", target: "BIN1", loc: "", flank: 50000 },
    { label: "📐 Microglia 2SMR + PRS-CSx Admixture", action: "mr_prs", target: "microglia_endolysosomal", loc: "", flank: 0 },
    { label: "🧬 TSPAN14 AlphaGenome + Cryptic Splice", action: "rare_regulatory", target: "TSPAN14", loc: "", flank: 0 },
    { label: "💊 APOE ARIA Safety + ClinicalTrials", action: "translational_trials", target: "APOE", loc: "", flank: 0 },
    { label: "📚 16-Paper Literature Credits", action: "literature_credits", target: "all", loc: "", flank: 0 },
    { label: "🔬 rs6733839 Full V2F Dossier", action: "locus_dossier", target: "rs6733839", loc: "", flank: 0 },
  ];

  const state = {
    activeTab: "studio",
    meta: null,
    mindmap: null,
    oaCatalog: null,
    lastOaResult: null,
    threads: [],
    activeThreadId: null,
    profile: "ad1",
    speedMode: "fast", // "fast" | "deep"
    mode: "direct", // "direct" | "plan"
    maxIterations: 10,
    pendingUploads: [], // [{name, token, size_bytes}]
    activeRunId: null,
    abortController: null,
    fullMetaLoaded: false,
    // Mindmap & Explorer render flags
    mmRendered: false,
    oaRendered: false,
    mmFilterPillar: "all",
    mmSearch: "",
    mmViewMode: "graph", // "graph" | "table"
    mmZoom: 1.0,
    mmCollapsed: new Set(),
    mmSelectedId: "mm_oa_variants",
    // Usage & Volume Dashboard state
    usageDays: "all",
    usageData: null,
    usageLedgerType: "all",
    usageLedgerDomain: "",
    usageLedgerSearch: "",
    usageSortCol: "ts",
    usageSortDir: "desc",
  };

  // ── DOM Elements ──────────────────────────────────────────────────────────
  const el = {
    sidebar: document.getElementById("sidebar"),
    openSidebarBtn: document.getElementById("open-sidebar-btn"),
    closeSidebarBtn: document.getElementById("close-sidebar-btn"),
    appVersion: document.getElementById("app-version"),
    newStudyBtn: document.getElementById("new-study-btn"),
    threadList: document.getElementById("thread-list"),
    portalTablist: document.getElementById("portal-tablist"),
    studioProfileGroup: document.getElementById("studio-profile-group"),
    studioSpeedGroup: document.getElementById("studio-speed-group"),
    studioModeGroup: document.getElementById("studio-mode-group"),
    profileAd1Btn: document.getElementById("profile-ad1-btn"),
    profileA1Btn: document.getElementById("profile-a1-btn"),
    speedFastBtn: document.getElementById("speed-fast-btn"),
    speedDeepBtn: document.getElementById("speed-deep-btn"),
    speedCriticBtn: document.getElementById("speed-critic-btn"),
    modeDirectBtn: document.getElementById("mode-direct-btn"),
    modePlanBtn: document.getElementById("mode-plan-btn"),
    statusDot: document.getElementById("status-dot"),
    modelBadgeText: document.getElementById("model-badge-text"),
    panelStudio: document.getElementById("panel-studio"),
    panelMindmap: document.getElementById("panel-mindmap"),
    panelNiagadsApi: document.getElementById("panel-niagads-api"),
    panelUsage: document.getElementById("panel-usage"),
    panelFeedback: document.getElementById("panel-feedback"),
    canvas: document.getElementById("canvas"),
    welcomeView: document.getElementById("welcome-view"),
    heroEyebrow: document.getElementById("hero-eyebrow"),
    heroTitle: document.getElementById("hero-title"),
    heroLead: document.getElementById("hero-lead"),
    starterGrid: document.getElementById("starter-grid"),
    transcript: document.getElementById("transcript"),
    attachmentStrip: document.getElementById("attachment-strip"),
    composerForm: document.getElementById("composer-form"),
    chatInput: document.getElementById("chat-input"),
    fileUploadInput: document.getElementById("file-upload-input"),
    attachFileBtn: document.getElementById("attach-file-btn"),
    workflowHint: document.getElementById("workflow-hint"),
    stopRunBtn: document.getElementById("stop-run-btn"),
    sendBtn: document.getElementById("send-btn"),
    catalogDialog: document.getElementById("catalog-dialog"),
    openCatalogBtn: document.getElementById("open-catalog-btn"),
    inspectCatalogInline: document.getElementById("inspect-catalog-inline"),
    toolsCatalogList: document.getElementById("tools-catalog-list"),
    niagadsCatalogList: document.getElementById("niagads-catalog-list"),
    settingsDialog: document.getElementById("settings-dialog"),
    openSettingsBtn: document.getElementById("open-settings-btn"),
    maxIterSelect: document.getElementById("max-iter-select"),
    diagnosticsSummary: document.getElementById("diagnostics-summary"),
    // Mindmap elements
    mmKpiRow: document.getElementById("mindmap-kpi-row"),
    mmPillarFilters: document.getElementById("mindmap-pillar-filters"),
    mmFilterForm: document.getElementById("mindmap-filter-form"),
    mmSearchInput: document.getElementById("mindmap-search-input"),
    mmViewGraphBtn: document.getElementById("mm-view-graph-btn"),
    mmViewTableBtn: document.getElementById("mm-view-table-btn"),
    mmExpandAllBtn: document.getElementById("mm-expand-all-btn"),
    mmCollapseAllBtn: document.getElementById("mm-collapse-all-btn"),
    mmZoomOutBtn: document.getElementById("mm-zoom-out-btn"),
    mmZoomInBtn: document.getElementById("mm-zoom-in-btn"),
    mmZoomReadout: document.getElementById("mm-zoom-readout"),
    mmGraphWorkbench: document.getElementById("mindmap-graph-workbench"),
    mmStageScroll: document.getElementById("mindmap-stage-scroll"),
    mmStage: document.getElementById("mindmap-stage"),
    mmLinksSvg: document.getElementById("mm-links-svg"),
    mmColumns: document.getElementById("mm-columns"),
    mmInspector: document.getElementById("mm-inspector"),
    mmMatrixContainer: document.getElementById("mindmap-matrix-container"),
    mmMatrixTbody: document.getElementById("mindmap-matrix-tbody"),
    // NIAGADS Open Access API Explorer elements
    oaRolloutGrid: document.getElementById("oa-rollout-grid"),
    oaPresetStrip: document.getElementById("oa-preset-strip"),
    oaForm: document.getElementById("niagads-live-form"),
    oaActionSelect: document.getElementById("oa-action-select"),
    oaTargetInput: document.getElementById("oa-target-input"),
    oaLocInput: document.getElementById("oa-loc-input"),
    oaFlankInput: document.getElementById("oa-flank-input"),
    oaSubmitBtn: document.getElementById("oa-submit-btn"),
    oaResultCard: document.getElementById("oa-result-card"),
    oaResultMeta: document.getElementById("oa-result-meta"),
    oaEcosystemLinks: document.getElementById("oa-ecosystem-links"),
    oaPaperCredits: document.getElementById("oa-paper-credits"),
    oaVisualContainer: document.getElementById("oa-visual-container"),
    oaResultMarkdown: document.getElementById("oa-result-markdown"),
    oaResultJson: document.getElementById("oa-result-json"),
    oaSendStudioBtn: document.getElementById("oa-send-studio-btn"),
    oaCiteBtn: document.getElementById("oa-cite-btn"),
    oaCopyJsonBtn: document.getElementById("oa-copy-json-btn"),
    oaEndpointsTbody: document.getElementById("oa-endpoints-tbody"),
    // Command Palette & NIAGADS Bond elements
    openCmdkBtn: document.getElementById("open-cmdk-btn"),
    heroOpenCmdkBtn: document.getElementById("hero-open-cmdk-btn"),
    copyNiagadsAckBtn: document.getElementById("copy-niagads-ack-btn"),
    cmdkDialog: document.getElementById("command-palette-dialog"),
    cmdkInput: document.getElementById("cmdk-input"),
    cmdkResults: document.getElementById("cmdk-results"),
    // Usage & Volume Dashboard elements
    usageWindowSub: document.getElementById("usage-window-sub"),
    usageRangeGroup: document.getElementById("usage-range-group"),
    usageRefreshBtn: document.getElementById("usage-refresh-btn"),
    usageExportDropdown: document.getElementById("usage-export-dropdown"),
    usagePrintPdfBtn: document.getElementById("usage-print-pdf-btn"),
    usageExportCsvLink: document.getElementById("usage-export-csv-link"),
    usageExportJsonLink: document.getElementById("usage-export-json-link"),
    usageExportMdLink: document.getElementById("usage-export-md-link"),
    usagePulseGrid: document.getElementById("usage-pulse-grid"),
    usageBriefList: document.getElementById("usage-brief-list"),
    usageTileWall: document.getElementById("usage-tile-wall"),
    usageTileCaption: document.getElementById("usage-tile-caption"),
    usageSpendTotal: document.getElementById("usage-spend-total"),
    usageSplitModel: document.getElementById("usage-split-model"),
    usageSplitCloud: document.getElementById("usage-split-cloud"),
    usageModelPct: document.getElementById("usage-model-pct"),
    usageCloudPct: document.getElementById("usage-cloud-pct"),
    usageCostKpis: document.getElementById("usage-cost-kpis"),
    usagePricingNote: document.getElementById("usage-pricing-note"),
    usageVolumeStrip: document.getElementById("usage-volume-strip"),
    svgDailyVolume: document.getElementById("svg-daily-volume"),
    svgCumulativeSpend: document.getElementById("svg-cumulative-spend"),
    svgLatencyScatter: document.getElementById("svg-latency-scatter"),
    svgArrivalHeatmap: document.getElementById("svg-arrival-heatmap"),
    usageHeatmapSub: document.getElementById("usage-heatmap-sub"),
    usageToolSub: document.getElementById("usage-tool-sub"),
    usageToolBand: document.getElementById("usage-tool-band"),
    usageToolList: document.getElementById("usage-tool-list"),
    usageFunnelList: document.getElementById("usage-funnel-list"),
    usageDomainBars: document.getElementById("usage-domain-bars"),
    usageClearDomainBtn: document.getElementById("usage-clear-domain-btn"),
    usageQualityDl: document.getElementById("usage-quality-dl"),
    usageSavingsGrid: document.getElementById("usage-savings-grid"),
    usageSavingsNote: document.getElementById("usage-savings-note"),
    usageLedgerCount: document.getElementById("usage-ledger-count"),
    usageTypeFilterGroup: document.getElementById("usage-type-filter-group"),
    usageLedgerSearch: document.getElementById("usage-ledger-search"),
    usageLedgerTable: document.getElementById("usage-ledger-table"),
    usageLedgerTbody: document.getElementById("usage-ledger-tbody"),
    usageWorkspacesTbody: document.getElementById("usage-workspaces-tbody"),
    usageTooltip: document.getElementById("usage-tooltip"),
  };

  // ── API Helper ────────────────────────────────────────────────────────────
  async function apiFetch(path, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("X-Ligase-Client-Id", CLIENT_ID);
    const resp = await fetch(path, { ...options, headers });
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try {
        const err = await resp.json();
        detail = err.detail || err.message || err.summary_markdown || detail;
      } catch {}
      throw new Error(detail);
    }
    return resp.json();
  }

  // ── Safe Markdown + GFM Table Renderer ────────────────────────────────────
  function escapeHtml(text) {
    return String(text ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  const GREEK_MAP = {
    alpha: "α",
    beta: "β",
    gamma: "γ",
    delta: "δ",
    Delta: "Δ",
    epsilon: "ε",
    varepsilon: "ε",
    lambda: "λ",
    mu: "μ",
    pi: "π",
    psi: "ψ",
    Psi: "Ψ",
    sigma: "σ",
    Sigma: "Σ",
    tau: "τ",
    chi: "χ",
    omega: "ω",
    Omega: "Ω",
    times: "×",
    cdot: "·",
    pm: "±",
    approx: "≈",
    le: "≤",
    leq: "≤",
    ge: "≥",
    geq: "≥",
    neq: "≠",
    to: "→",
    rightarrow: "→",
  };

  function formatInlineMath(expr) {
    let m = escapeHtml(expr.trim());
    m = m.replace(/\\(?:text|mathrm|mathbf)\{([^{}]*)\}/g, '<span class="math-rm">$1</span>');
    m = m.replace(/(<\/span>)\{(<span class="math-rm">[^{}<]*<\/span>|[^{}]+)\}/g, "$1<sub>$2</sub>");
    m = m.replace(/\\([A-Za-z]+)/g, (full, cmd) => GREEK_MAP[cmd] || cmd);
    m = m.replace(/\\([%&_# ])/g, (_, ch) => (ch === " " ? "\u00a0" : ch));
    m = m.replace(/_\{(<span class="math-rm">[^{}<]*<\/span>|[^{}]+)\}/g, "<sub>$1</sub>");
    m = m.replace(/\^\{(<span class="math-rm">[^{}<]*<\/span>|[^{}]+)\}/g, "<sup>$1</sup>");
    m = m.replace(/_([A-Za-z0-9]+)/g, "<sub>$1</sub>");
    m = m.replace(/\^([A-Za-z0-9+-]+)/g, "<sup>$1</sup>");
    return `<span class="math-inline">${m}</span>`;
  }

  function renderInline(line) {
    const codeSpans = [];
    const mathSpans = [];
    let s = String(line ?? "").replace(/`([^`]+)`/g, (_, code) => {
      const idx = codeSpans.length;
      codeSpans.push(`<code>${escapeHtml(code)}</code>`);
      return `\u0000CODE${idx}\u0000`;
    });
    s = s.replace(/\\\[(.+?)\\\]|\$\$([^$\n]+?)\$\$|\\\((.+?)\\\)|\$(?!\s)([^$\n]+?)(?<!\s)\$/g, (full, d1, d2, p1, p2) => {
      const expr = d1 ?? d2 ?? p1 ?? p2 ?? "";
      if (!expr || /^\d+(?:[.,]\d+)?$/.test(expr.trim())) return full;
      const idx = mathSpans.length;
      mathSpans.push(formatInlineMath(expr));
      return `\u0000MATH${idx}\u0000`;
    });
    s = escapeHtml(s);
    s = s.replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
    );
    s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|[\s(])\*([^*\n]+)\*(?=[\s).,;:!?]|$)/g, "$1<em>$2</em>");
    s = s.replace(/\u0000MATH(\d+)\u0000/g, (_, idx) => mathSpans[Number(idx)] || "");
    s = s.replace(/\u0000CODE(\d+)\u0000/g, (_, idx) => codeSpans[Number(idx)] || "");
    return s;
  }

  function parseTableCells(rowLine) {
    let trimmed = rowLine.trim();
    if (trimmed.startsWith("|")) trimmed = trimmed.slice(1);
    if (trimmed.endsWith("|")) trimmed = trimmed.slice(0, -1);
    return trimmed.split("|").map((c) => c.trim());
  }

  function isTableSeparator(line) {
    const t = line.trim();
    if (!t.includes("|") || !t.includes("-")) return false;
    const cells = parseTableCells(t);
    return cells.length > 0 && cells.every((c) => /^:?-{2,}:?$/.test(c));
  }

  function renderMarkdown(md) {
    const src = String(md ?? "").replace(/\r\n/g, "\n");
    const lines = src.split("\n");
    const out = [];
    let i = 0;

    while (i < lines.length) {
      const line = lines[i];

      if (line.trim().startsWith("```")) {
        const lang = line.trim().slice(3).trim();
        const buf = [];
        i++;
        while (i < lines.length && !lines[i].trim().startsWith("```")) {
          buf.push(lines[i]);
          i++;
        }
        i++;
        out.push(`<pre><code data-lang="${escapeHtml(lang)}">${escapeHtml(buf.join("\n"))}</code></pre>`);
        continue;
      }

      if (line.includes("|") && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
        const headers = parseTableCells(line);
        i += 2;
        const rows = [];
        while (i < lines.length && lines[i].trim() && lines[i].includes("|")) {
          rows.push(parseTableCells(lines[i]));
          i++;
        }
        const ths = headers.map((h) => `<th scope="col">${renderInline(h)}</th>`).join("");
        const trs = rows
          .map((cells) => {
            const tds = headers
              .map((h, colIdx) => {
                const val = cells[colIdx] ?? "";
                if (colIdx === 0) {
                  return `<th scope="row">${renderInline(val)}</th>`;
                }
                const cleanLabel = h.replace(/[`*_]/g, "").trim();
                return `<td data-col-label="${escapeHtml(cleanLabel)}">${renderInline(val)}</td>`;
              })
              .join("");
            return `<tr>${tds}</tr>`;
          })
          .join("");
        out.push(
          `<div tabindex="0" role="region" aria-label="Scientific results table" class="table-wrapper">` +
            `<table><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>` +
            `</div>`
        );
        continue;
      }

      const hMatch = line.match(/^(#{1,4})\s+(.*)$/);
      if (hMatch) {
        const lvl = Math.min(4, Math.max(2, hMatch[1].length));
        out.push(`<h${lvl}>${renderInline(hMatch[2])}</h${lvl}>`);
        i++;
        continue;
      }

      if (line.trim().startsWith(">")) {
        const qBuf = [];
        while (i < lines.length && lines[i].trim().startsWith(">")) {
          qBuf.push(lines[i].trim().replace(/^>\s?/, ""));
          i++;
        }
        out.push(`<blockquote>${qBuf.map(renderInline).join("<br>")}</blockquote>`);
        continue;
      }

      if (/^\s*[-*+]\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
          items.push(`<li>${renderInline(lines[i].replace(/^\s*[-*+]\s+/, ""))}</li>`);
          i++;
        }
        out.push(`<ul>${items.join("")}</ul>`);
        continue;
      }

      if (/^\s*\d+[.)]\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
          items.push(`<li>${renderInline(lines[i].replace(/^\s*\d+[.)]\s+/, ""))}</li>`);
          i++;
        }
        out.push(`<ol>${items.join("")}</ol>`);
        continue;
      }

      if (/^\s*---+\s*$/.test(line)) {
        out.push("<hr>");
        i++;
        continue;
      }

      if (!line.trim()) {
        i++;
        continue;
      }

      const pBuf = [];
      while (
        i < lines.length &&
        lines[i].trim() &&
        !lines[i].trim().startsWith("```") &&
        !/^(#{1,4})\s+/.test(lines[i]) &&
        !lines[i].trim().startsWith(">") &&
        !/^\s*[-*+]\s+/.test(lines[i]) &&
        !/^\s*\d+[.)]\s+/.test(lines[i]) &&
        !(lines[i].includes("|") && i + 1 < lines.length && isTableSeparator(lines[i + 1]))
      ) {
        pBuf.push(renderInline(lines[i]));
        i++;
      }
      out.push(`<p>${pBuf.join("<br>")}</p>`);
    }

    return out.join("\n");
  }

  // ── Accessible Multi-Tab Navigation (with Same-Document View Transitions) ──
  function runMaybeViewTransition(mutateDom, afterFocusEl = null) {
    const shiftFocus = () => {
      if (afterFocusEl && typeof afterFocusEl.focus === "function") {
        if (!afterFocusEl.hasAttribute("tabindex")) {
          afterFocusEl.setAttribute("tabindex", "-1");
        }
        afterFocusEl.focus({ preventScroll: true });
      }
    };
    const reduceMotion =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!reduceMotion && typeof document.startViewTransition === "function") {
      try {
        const vt = document.startViewTransition(mutateDom);
        if (vt && vt.finished && typeof vt.finished.then === "function") {
          vt.finished.then(shiftFocus).catch(() => {});
        } else {
          shiftFocus();
        }
        return;
      } catch {}
    }
    mutateDom();
    shiftFocus();
  }

  function resolvePanelHeading(validTab) {
    const map = {
      studio: el.heroTitle,
      mindmap: el.panelMindmap?.querySelector(".page-heading"),
      "niagads-api": el.panelNiagadsApi?.querySelector(".page-heading"),
      usage: el.panelUsage?.querySelector(".page-heading"),
      feedback: el.panelFeedback?.querySelector(".page-heading"),
    };
    return map[validTab] || null;
  }

  async function switchPortalTab(tabId, { focusTab = false, focusHeading = false, updateHash = true } = {}) {
    const valid =
      tabId === "mindmap" || tabId === "niagads-api" || tabId === "usage" || tabId === "feedback"
        ? tabId
        : "studio";
    const changed = state.activeTab !== valid;
    const prevTab = state.activeTab;
    state.activeTab = valid;

    const applyTabVisibility = () => {
      const tabButtons = Array.from(el.portalTablist.querySelectorAll('[role="tab"]'));
      for (const btn of tabButtons) {
        const isMatch = btn.dataset.tab === valid;
        btn.setAttribute("aria-selected", isMatch ? "true" : "false");
        if (isMatch) {
          btn.removeAttribute("tabindex");
        } else {
          btn.setAttribute("tabindex", "-1");
        }
        const li = btn.closest(".portal-tab-item");
        if (li) li.classList.toggle("active", isMatch);
        if (isMatch && focusTab) btn.focus();
      }

      el.panelStudio.hidden = valid !== "studio";
      el.panelMindmap.hidden = valid !== "mindmap";
      el.panelNiagadsApi.hidden = valid !== "niagads-api";
      el.panelUsage.hidden = valid !== "usage";
      if (el.panelFeedback) el.panelFeedback.hidden = valid !== "feedback";

      // Studio-specific topbar segmented switches
      const isStudio = valid === "studio";
      el.studioProfileGroup.hidden = !isStudio;
      el.studioSpeedGroup.hidden = !isStudio;
      el.studioModeGroup.hidden = !isStudio;

      // Sidebar view shortcut active highlight
      for (const sc of document.querySelectorAll("[data-goto-tab]")) {
        if (sc.classList.contains("ghost-footer-btn")) {
          sc.classList.toggle("active", sc.dataset.gotoTab === valid);
        }
      }
    };

    const headingTarget = focusHeading && !focusTab ? resolvePanelHeading(valid) : null;
    if (changed) {
      runMaybeViewTransition(applyTabVisibility, headingTarget);
    } else {
      applyTabVisibility();
      if (headingTarget) {
        if (!headingTarget.hasAttribute("tabindex")) headingTarget.setAttribute("tabindex", "-1");
        headingTarget.focus({ preventScroll: true });
      }
    }

    document.title = TAB_TITLES[valid] || TAB_TITLES.studio;
    if (updateHash) {
      try {
        const pLower = (window.location.pathname || "").toLowerCase();
        const basePath =
          pLower === "/usage" || pLower === "/admin" || pLower === "/feedback" || pLower === "/comments"
            ? "/"
            : window.location.pathname;
        history.replaceState(null, "", valid === "studio" ? basePath : `${basePath}#${valid}`);
      } catch {}
    }
    el.sidebar.classList.remove("open");

    if (valid === "mindmap") {
      await ensureMindmapLoaded();
      requestAnimationFrame(() => drawMindmapConnectors());
    } else if (valid === "niagads-api") {
      await ensureOaCatalogLoaded();
    } else if (valid === "usage") {
      await ensureUsageLoaded();
    } else if (valid === "feedback") {
      // Pre-select the portal component the user just came from!
      const areaSelect = document.getElementById("fb-target-area");
      if (areaSelect && prevTab && prevTab !== "feedback") {
        areaSelect.value = prevTab;
      }
      await ensureFeedbackTabLoaded();
    }
  }

  el.portalTablist.addEventListener("click", (ev) => {
    const btn = ev.target.closest('[role="tab"]');
    if (!btn) return;
    switchPortalTab(btn.dataset.tab);
  });

  el.portalTablist.addEventListener("keydown", (ev) => {
    const tabs = Array.from(el.portalTablist.querySelectorAll('[role="tab"]'));
    const idx = tabs.indexOf(document.activeElement);
    if (idx === -1) return;
    let nextIdx = -1;
    if (ev.key === "ArrowRight") nextIdx = (idx + 1) % tabs.length;
    else if (ev.key === "ArrowLeft") nextIdx = (idx - 1 + tabs.length) % tabs.length;
    else if (ev.key === "Home") nextIdx = 0;
    else if (ev.key === "End") nextIdx = tabs.length - 1;
    if (nextIdx !== -1) {
      ev.preventDefault();
      switchPortalTab(tabs[nextIdx].dataset.tab, { focusTab: true });
    }
  });

  for (const gotoBtn of document.querySelectorAll("[data-goto-tab]")) {
    gotoBtn.addEventListener("click", () => {
      switchPortalTab(gotoBtn.dataset.gotoTab, { focusHeading: true });
    });
  }

  // ── Capabilities Mindmap Logic ────────────────────────────────────────────
  async function ensureMindmapLoaded() {
    if (!state.mindmap) {
      try {
        state.mindmap = await apiFetch("/api/mindmap");
      } catch (err) {
        el.mmColumns.innerHTML = `<p style="color:var(--danger)">Could not load mindmap: ${escapeHtml(err.message)}</p>`;
        return;
      }
    }
    if (!state.mmRendered) {
      state.mmRendered = true;
      renderMindmapAll();
    }
  }

  function findMindmapEntity(entityId) {
    const mm = state.mindmap;
    if (!mm) return null;
    if (entityId === mm.root.id) {
      return { kind: "root", node: mm.root, branch: null };
    }
    for (const branch of mm.branches || []) {
      if (branch.id === entityId) {
        return { kind: "branch", node: branch, branch };
      }
      for (const comp of branch.components || []) {
        if (comp.id === entityId) {
          return { kind: "component", node: comp, branch };
        }
      }
    }
    return null;
  }

  function componentMatchesFilter(comp, branch) {
    if (state.mmFilterPillar !== "all" && branch.id !== state.mmFilterPillar) {
      return false;
    }
    const q = state.mmSearch.trim().toLowerCase();
    if (!q) return true;
    const hay = [
      comp.title,
      comp.badge,
      comp.summary,
      branch.title,
      ...(comp.backing || []),
    ]
      .join(" ")
      .toLowerCase();
    return hay.includes(q);
  }

  function renderMindmapKpis() {
    const st = state.mindmap?.stats || {};
    const items = [
      { val: st.pillars || 6, lbl: "Core Pillars" },
      { val: st.components || 32, lbl: "Components" },
      { val: st.niagads_openapi_paths || 19, lbl: "NIAGADS v2.0 Paths" },
      { val: st.niagads_dss_cohorts || 24, lbl: "NG* Cohorts" },
      { val: st.biomni_tools || "180+", lbl: "Biomni Tools" },
    ];
    el.mmKpiRow.innerHTML = items
      .map(
        (it) => `
        <div class="mm-kpi-pill">
          <span class="mm-kpi-val">${escapeHtml(it.val)}</span>
          <span class="mm-kpi-lbl">${escapeHtml(it.lbl)}</span>
        </div>
      `
      )
      .join("");
  }

  function renderMindmapPillarFilters() {
    const branches = state.mindmap?.branches || [];
    el.mmPillarFilters.innerHTML = "";

    const allBtn = document.createElement("button");
    allBtn.type = "button";
    allBtn.className = "pillar-filter-btn";
    allBtn.setAttribute("aria-pressed", state.mmFilterPillar === "all" ? "true" : "false");
    allBtn.textContent = "All 6 Pillars";
    allBtn.addEventListener("click", () => {
      state.mmFilterPillar = "all";
      renderMindmapPillarFilters();
      renderMindmapGraphAndMatrix();
    });
    el.mmPillarFilters.appendChild(allBtn);

    for (const b of branches) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "pillar-filter-btn";
      btn.style.setProperty("--branch-accent", b.accent);
      btn.setAttribute("aria-pressed", state.mmFilterPillar === b.id ? "true" : "false");
      btn.innerHTML = `<span aria-hidden="true">${escapeHtml(b.icon)}</span> ${escapeHtml(b.short_title || b.title)}`;
      btn.addEventListener("click", () => {
        state.mmFilterPillar = b.id;
        state.mmCollapsed.delete(b.id);
        renderMindmapPillarFilters();
        renderMindmapGraphAndMatrix();
      });
      el.mmPillarFilters.appendChild(btn);
    }
  }

  function renderMindmapGraphAndMatrix() {
    const mm = state.mindmap;
    if (!mm) return;

    // 1. Render Interactive Graph Nodes
    el.mmColumns.innerHTML = "";

    const rootCol = document.createElement("div");
    rootCol.className = "mm-root-col";
    const rootBtn = document.createElement("button");
    rootBtn.type = "button";
    rootBtn.id = `mm-dom-${mm.root.id}`;
    rootBtn.className = "mm-root-node" + (state.mmSelectedId === mm.root.id ? " selected" : "");
    rootBtn.innerHTML = `
      <div class="mm-root-title">🧬 ${escapeHtml(mm.root.title)}</div>
      <div class="mm-root-sub">${escapeHtml(mm.root.subtitle)}</div>
    `;
    rootBtn.addEventListener("click", () => {
      state.mmSelectedId = mm.root.id;
      renderMindmapGraphAndMatrix();
    });
    rootCol.appendChild(rootBtn);

    const branchesCol = document.createElement("div");
    branchesCol.className = "mm-branches-col";

    const matrixRowsHtml = [];

    for (const branch of mm.branches || []) {
      const matchingLeaves = (branch.components || []).filter((c) => componentMatchesFilter(c, branch));
      if (state.mmFilterPillar !== "all" && branch.id !== state.mmFilterPillar) continue;
      if (state.mmSearch.trim() && matchingLeaves.length === 0) continue;

      const isCollapsed = state.mmCollapsed.has(branch.id);

      const row = document.createElement("div");
      row.className = "mm-branch-row";
      row.style.setProperty("--branch-accent", branch.accent);

      const pillarCard = document.createElement("div");
      pillarCard.id = `mm-dom-${branch.id}`;
      pillarCard.className = "mm-pillar-card" + (state.mmSelectedId === branch.id ? " selected" : "");
      pillarCard.dataset.branchId = branch.id;

      const selectBtn = document.createElement("button");
      selectBtn.type = "button";
      selectBtn.className = "mm-pillar-select-btn";
      selectBtn.innerHTML = `
        <div class="mm-pillar-top">
          <span class="mm-pillar-title"><span aria-hidden="true">${escapeHtml(branch.icon)}</span> ${escapeHtml(branch.title)}</span>
        </div>
        <span class="mm-pillar-badge">${escapeHtml(branch.badge)} · ${matchingLeaves.length} items</span>
      `;
      selectBtn.addEventListener("click", () => {
        state.mmSelectedId = branch.id;
        renderMindmapGraphAndMatrix();
      });

      const toggleBtn = document.createElement("button");
      toggleBtn.type = "button";
      toggleBtn.className = "mm-pillar-toggle-btn";
      toggleBtn.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
      toggleBtn.setAttribute("aria-label", `${isCollapsed ? "Expand" : "Collapse"} ${branch.title}`);
      toggleBtn.textContent = isCollapsed ? "+" : "−";
      toggleBtn.addEventListener("click", () => {
        if (state.mmCollapsed.has(branch.id)) state.mmCollapsed.delete(branch.id);
        else state.mmCollapsed.add(branch.id);
        renderMindmapGraphAndMatrix();
      });

      pillarCard.append(selectBtn, toggleBtn);
      row.appendChild(pillarCard);

      const leavesStack = document.createElement("div");
      leavesStack.className = "mm-leaves-stack";
      if (isCollapsed) {
        leavesStack.hidden = true;
      } else {
        for (const comp of matchingLeaves) {
          const leafBtn = document.createElement("button");
          leafBtn.type = "button";
          leafBtn.id = `mm-dom-${comp.id}`;
          leafBtn.dataset.parentBranch = branch.id;
          leafBtn.className = "mm-leaf-node" + (state.mmSelectedId === comp.id ? " selected" : "");
          leafBtn.innerHTML = `
            <span>${escapeHtml(comp.title)}</span>
            <span class="mm-leaf-badge">${escapeHtml(comp.badge)}</span>
          `;
          leafBtn.addEventListener("click", () => {
            state.mmSelectedId = comp.id;
            renderMindmapGraphAndMatrix();
          });
          leavesStack.appendChild(leafBtn);
        }
      }
      row.appendChild(leavesStack);
      branchesCol.appendChild(row);

      // Build semantic table rows in parallel
      for (const comp of matchingLeaves) {
        const backingCode = (comp.backing || []).map((b) => `<code>${escapeHtml(b)}</code>`).join(" ");
        matrixRowsHtml.push(`
          <tr>
            <th scope="row">${escapeHtml(comp.title)}</th>
            <td data-col-label="Pillar">${escapeHtml(branch.title)}</td>
            <td data-col-label="Status">${escapeHtml(comp.badge)}</td>
            <td data-col-label="Backing">${backingCode}</td>
            <td data-col-label="Summary">${escapeHtml(comp.summary)}</td>
            <td data-col-label="Action">
              <button type="button" class="tool-chip-btn" data-matrix-run="${escapeHtml(comp.id)}">Run in Studio →</button>
            </td>
          </tr>
        `);
      }
    }

    el.mmColumns.append(rootCol, branchesCol);
    el.mmMatrixTbody.innerHTML =
      matrixRowsHtml.join("") ||
      `<tr><th scope="row">No matches</th><td colspan="5">Clear search filter to see all 32 supported Ligase components.</td></tr>`;

    for (const runBtn of el.mmMatrixTbody.querySelectorAll("[data-matrix-run]")) {
      runBtn.addEventListener("click", () => {
        const found = findMindmapEntity(runBtn.dataset.matrixRun);
        if (found?.node?.sample_prompt) {
          launchPromptInStudio(found.node.sample_prompt, found.branch?.id);
        }
      });
    }

    renderMindmapInspector();
    requestAnimationFrame(() => drawMindmapConnectors());
  }

  function drawMindmapConnectors() {
    if (!state.mindmap || state.activeTab !== "mindmap" || state.mmViewMode !== "graph") return;
    const svg = el.mmLinksSvg;
    const stageRect = el.mmStage.getBoundingClientRect();
    const scale = state.mmZoom || 1;
    if (stageRect.width === 0) return;

    const relBox = (domEl) => {
      const r = domEl.getBoundingClientRect();
      return {
        left: (r.left - stageRect.left) / scale,
        right: (r.right - stageRect.left) / scale,
        midY: (r.top - stageRect.top + r.height / 2) / scale,
      };
    };

    const rootEl = document.getElementById(`mm-dom-${state.mindmap.root.id}`);
    if (!rootEl) {
      svg.innerHTML = "";
      return;
    }
    const rootBox = relBox(rootEl);
    const paths = [];

    for (const branch of state.mindmap.branches || []) {
      const pEl = document.getElementById(`mm-dom-${branch.id}`);
      if (!pEl) continue;
      const pBox = relBox(pEl);
      const dx1 = Math.max(36, (pBox.left - rootBox.right) * 0.52);
      paths.push(
        `<path d="M ${rootBox.right.toFixed(1)} ${rootBox.midY.toFixed(1)} ` +
          `C ${(rootBox.right + dx1).toFixed(1)} ${rootBox.midY.toFixed(1)}, ` +
          `${(pBox.left - dx1).toFixed(1)} ${pBox.midY.toFixed(1)}, ` +
          `${pBox.left.toFixed(1)} ${pBox.midY.toFixed(1)}" ` +
          `fill="none" stroke="${escapeHtml(branch.accent)}" stroke-width="2.2" stroke-opacity="0.65" />`
      );

      if (!state.mmCollapsed.has(branch.id)) {
        const leafEls = el.mmColumns.querySelectorAll(`[data-parent-branch="${branch.id}"]`);
        for (const lEl of leafEls) {
          const lBox = relBox(lEl);
          const dx2 = Math.max(30, (lBox.left - pBox.right) * 0.5);
          paths.push(
            `<path d="M ${pBox.right.toFixed(1)} ${pBox.midY.toFixed(1)} ` +
              `C ${(pBox.right + dx2).toFixed(1)} ${pBox.midY.toFixed(1)}, ` +
              `${(lBox.left - dx2).toFixed(1)} ${lBox.midY.toFixed(1)}, ` +
              `${lBox.left.toFixed(1)} ${lBox.midY.toFixed(1)}" ` +
              `fill="none" stroke="${escapeHtml(branch.accent)}" stroke-width="1.6" stroke-opacity="0.45" />`
          );
        }
      }
    }

    svg.innerHTML = paths.join("");
  }

  function renderMindmapInspector() {
    const found = findMindmapEntity(state.mmSelectedId) || findMindmapEntity("mm_oa_variants");
    if (!found) return;
    const { kind, node, branch } = found;
    const accent = branch?.accent || "var(--brand-primary)";
    el.mmInspector.style.setProperty("--branch-accent", accent);

    if (kind === "root") {
      el.mmInspector.innerHTML = `
        <div class="mm-inspector-pillar">Unified Co-Scientist Architecture</div>
        <h3 class="mm-inspector-title">${escapeHtml(node.title)}</h3>
        <p class="mm-inspector-summary">${escapeHtml(node.summary)}</p>
        <div class="mm-inspector-label">Architectural Pillars</div>
        <div class="mm-backing-chips">
          ${(state.mindmap.branches || [])
            .map((b) => `<span class="mm-backing-chip">${escapeHtml(b.icon)} ${escapeHtml(b.short_title)}</span>`)
            .join("")}
        </div>
        <div class="mm-inspector-actions">
          <button type="button" class="plan-approve-btn" id="mm-insp-open-oa">🌐 Open Live NIAGADS API v2.0 Console</button>
        </div>
      `;
      document.getElementById("mm-insp-open-oa")?.addEventListener("click", () => switchPortalTab("niagads-api"));
      return;
    }

    if (kind === "branch") {
      el.mmInspector.innerHTML = `
        <div class="mm-inspector-pillar">${escapeHtml(node.badge)}</div>
        <h3 class="mm-inspector-title">${escapeHtml(node.icon)} ${escapeHtml(node.title)}</h3>
        <p class="mm-inspector-summary">${escapeHtml(node.summary)}</p>
        <div class="mm-inspector-label">Supported Components (${(node.components || []).length})</div>
        <div class="mm-backing-chips">
          ${(node.components || [])
            .map((c) => `<span class="mm-backing-chip">${escapeHtml(c.title)}</span>`)
            .join("")}
        </div>
      `;
      return;
    }

    const backingHtml = (node.backing || [])
      .map((b) => `<span class="mm-backing-chip">${escapeHtml(b)}</span>`)
      .join("");
    const hasLivePreset = Boolean(node.live_api_preset);

    el.mmInspector.innerHTML = `
      <div class="mm-inspector-pillar">${escapeHtml(branch.icon)} ${escapeHtml(branch.title)} · ${escapeHtml(node.badge)}</div>
      <h3 class="mm-inspector-title">${escapeHtml(node.title)}</h3>
      <p class="mm-inspector-summary">${escapeHtml(node.summary)}</p>
      <div class="mm-inspector-label">Backing Endpoints &amp; Modules</div>
      <div class="mm-backing-chips">${backingHtml}</div>
      ${
        node.sample_prompt
          ? `<div class="mm-inspector-label">Ready-to-Run Scientific Prompt</div>
             <div class="mm-prompt-preview">${escapeHtml(node.sample_prompt)}</div>`
          : ""
      }
      <div class="mm-inspector-actions">
        ${
          node.sample_prompt
            ? `<button type="button" class="plan-approve-btn" id="mm-insp-run-studio">🚀 Launch Study in Research Studio</button>`
            : ""
        }
        ${
          hasLivePreset
            ? `<button type="button" class="plan-secondary-btn" id="mm-insp-run-oa">⚡ Test Live NIAGADS API Endpoint</button>`
            : ""
        }
      </div>
    `;

    document.getElementById("mm-insp-run-studio")?.addEventListener("click", () => {
      launchPromptInStudio(node.sample_prompt, branch.id);
    });
    document.getElementById("mm-insp-run-oa")?.addEventListener("click", async () => {
      const p = node.live_api_preset;
      await switchPortalTab("niagads-api");
      applyAndRunOaPreset(p.action, p.target, p.loc || "", 0);
    });
  }

  function renderMindmapAll() {
    renderMindmapKpis();
    renderMindmapPillarFilters();
    renderMindmapGraphAndMatrix();
  }

  function setMindmapZoom(nextZoom) {
    state.mmZoom = Math.min(1.25, Math.max(0.75, Math.round(nextZoom * 100) / 100));
    el.mmStage.style.setProperty("--mm-zoom", String(state.mmZoom));
    el.mmZoomReadout.textContent = `${Math.round(state.mmZoom * 100)}%`;
    requestAnimationFrame(() => drawMindmapConnectors());
  }

  el.mmFilterForm.addEventListener("submit", (ev) => {
    ev.preventDefault();
    state.mmSearch = el.mmSearchInput.value;
    renderMindmapGraphAndMatrix();
  });
  el.mmSearchInput.addEventListener("input", () => {
    state.mmSearch = el.mmSearchInput.value;
    renderMindmapGraphAndMatrix();
  });

  el.mmViewGraphBtn.addEventListener("click", () => {
    state.mmViewMode = "graph";
    el.mmViewGraphBtn.classList.add("active");
    el.mmViewGraphBtn.setAttribute("aria-pressed", "true");
    el.mmViewTableBtn.classList.remove("active");
    el.mmViewTableBtn.setAttribute("aria-pressed", "false");
    el.mmGraphWorkbench.hidden = false;
    el.mmMatrixContainer.hidden = true;
    requestAnimationFrame(() => drawMindmapConnectors());
  });

  el.mmViewTableBtn.addEventListener("click", () => {
    state.mmViewMode = "table";
    el.mmViewTableBtn.classList.add("active");
    el.mmViewTableBtn.setAttribute("aria-pressed", "true");
    el.mmViewGraphBtn.classList.remove("active");
    el.mmViewGraphBtn.setAttribute("aria-pressed", "false");
    el.mmGraphWorkbench.hidden = true;
    el.mmMatrixContainer.hidden = false;
  });

  el.mmExpandAllBtn.addEventListener("click", () => {
    state.mmCollapsed.clear();
    renderMindmapGraphAndMatrix();
  });
  el.mmCollapseAllBtn.addEventListener("click", () => {
    for (const b of state.mindmap?.branches || []) state.mmCollapsed.add(b.id);
    renderMindmapGraphAndMatrix();
  });
  el.mmZoomOutBtn.addEventListener("click", () => setMindmapZoom(state.mmZoom - 0.1));
  el.mmZoomInBtn.addEventListener("click", () => setMindmapZoom(state.mmZoom + 0.1));

  if (typeof ResizeObserver !== "undefined") {
    const ro = new ResizeObserver(() => {
      if (state.activeTab === "mindmap") drawMindmapConnectors();
    });
    ro.observe(el.mmColumns);
  }

  function launchPromptInStudio(promptText, branchId = "") {
    const useAd1 = !branchId || branchId.startsWith("niagads") || branchId === "engine" || branchId === "portal_outputs";
    setProfile(useAd1 ? "ad1" : "a1");
    switchPortalTab("studio");
    el.chatInput.value = promptText;
    el.chatInput.focus();
    handleSubmitPrompt(promptText);
  }

  // ── NIAGADS Open Access API v2.0 Live Explorer Logic ──────────────────────
  async function ensureOaCatalogLoaded() {
    if (!state.oaCatalog) {
      state.oaCatalog = state.meta?.niagads?.open_access || (await apiFetch("/api/niagads/endpoints"));
    }
    if (!state.oaRendered) {
      state.oaRendered = true;
      renderOaExplorerStatic();
    }
    if (!state.lastOaResult) {
      // Fire default showcase query asynchronously without blocking tab render
      runLiveNiagadsQuery();
    }
  }

  function renderOaExplorerStatic() {
    const cat = state.oaCatalog;
    if (!cat) return;

    el.oaRolloutGrid.innerHTML = (cat.resources || [])
      .map((r) => {
        const isLive = r.status === "available" || r.status === "partner_live";
        return `
          <div class="oa-rollout-card">
            <div class="oa-rollout-head">
              <span class="oa-rollout-title">${escapeHtml(r.name)}</span>
              <span class="oa-status-pill ${isLive ? "" : "staged"}">${escapeHtml(r.badge)}</span>
            </div>
            <div class="oa-rollout-desc">${escapeHtml(r.description)}</div>
          </div>
        `;
      })
      .join("");

    el.oaPresetStrip.innerHTML = "";
    for (const p of OA_PRESETS) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "oa-preset-btn";
      btn.textContent = p.label;
      btn.addEventListener("click", () => {
        applyAndRunOaPreset(p.action, p.target, p.loc, p.flank);
      });
      el.oaPresetStrip.appendChild(btn);
    }

    el.oaEndpointsTbody.innerHTML = (cat.endpoints || [])
      .map(
        (ep) => `
        <tr>
          <th scope="row"><code>${escapeHtml(ep.action)}</code></th>
          <td data-col-label="REST Path"><code>${escapeHtml(ep.path)}</code></td>
          <td data-col-label="Capability"><strong>${escapeHtml(ep.summary)}</strong></td>
          <td data-col-label="Description">${escapeHtml(ep.description)}</td>
          <td data-col-label="Live Test">
            <button
              type="button"
              class="tool-chip-btn"
              data-try-action="${escapeHtml(ep.action)}"
              data-try-target="${escapeHtml(ep.example_target || "")}"
              data-try-loc="${escapeHtml(ep.example_loc || "")}"
            >Try <code>${escapeHtml(ep.example_target)}</code> →</button>
          </td>
        </tr>
      `
      )
      .join("");

    for (const tryBtn of el.oaEndpointsTbody.querySelectorAll("[data-try-action]")) {
      tryBtn.addEventListener("click", () => {
        applyAndRunOaPreset(
          tryBtn.dataset.tryAction,
          tryBtn.dataset.tryTarget,
          tryBtn.dataset.tryLoc || "",
          0
        );
      });
    }
  }

  // ── Toast & NIH/NIA U24AG041689 Citation Helpers ──────────────────────────
  let activeToastTimer = null;
  function showToast(message) {
    let banner = document.getElementById("ligase-toast-banner");
    if (!banner) {
      banner = document.createElement("div");
      banner.id = "ligase-toast-banner";
      banner.className = "toast-banner";
      banner.setAttribute("role", "status");
      banner.setAttribute("aria-live", "polite");
      document.body.appendChild(banner);
    }
    banner.textContent = message;
    banner.hidden = false;
    if (activeToastTimer) clearTimeout(activeToastTimer);
    activeToastTimer = setTimeout(() => {
      banner.hidden = true;
    }, 2800);
  }

  function buildNiagadsCitationText(contextLabel = "Ligase NIAGADS Study", identifiers = []) {
    const stamp = new Date().toISOString().slice(0, 10);
    const idLine = identifiers.length ? `\nQueried Accessions / Loci: ${identifiers.join(", ")}` : "";
    const credits = Array.isArray(state.lastOaResult?.paper_credits) ? state.lastOaResult.paper_credits : [];
    const paperLines = credits.length
      ? [
          "",
          "Grounded Peer-Reviewed & Preprint Literature Credits:",
          ...credits.map((p) => `- ${p.short_citation} — ${p.title} (${p.venue}, DOI/ID: ${p.doi}) [${p.url}]`),
        ]
      : [];
    return [
      `NIH / NIA NIAGADS Data Acknowledgment (${contextLabel}, accessed ${stamp}):${idLine}`,
      "Data used in preparation of this analysis were obtained from the National Institute on Aging Genetics of Alzheimer's Disease Data Storage Site (NIAGADS, https://www.niagads.org) and the NIAGADS Open Access API v2.0 (https://api.niagads.org/open-access, Apache 2.0). NIAGADS is supported by the National Institute on Aging under Cooperative Agreement U24AG041689.",
      ...paperLines,
      "",
      "@misc{niagads_open_access_v2,",
      "  title        = {NIAGADS Alzheimer's GenomicsDB \\& Open Access API v2.0},",
      "  organization = {National Institute on Aging Genetics of Alzheimer's Disease Data Storage Site (NIAGADS)},",
      "  url          = {https://api.niagads.org/open-access},",
      "  note         = {Supported by NIH/NIA Cooperative Agreements U24AG041689 and U24AG074855 (ADSP-PHC); synthesized via Ligase v0.8.0}",
      "}",
    ].join("\n");
  }

  async function copyNiagadsCitation(contextLabel, identifiers = []) {
    const text = buildNiagadsCitationText(contextLabel, identifiers);
    try {
      await navigator.clipboard.writeText(text);
      showToast("✓ Copied NIH/NIA NIAGADS U24AG041689 acknowledgment & BibTeX");
    } catch {
      showToast("Citation ready — clipboard permission unavailable in this context");
    }
  }

  // ── Programmatic SVG Genomics Visualizer & Ecosystem Cross-Links ──────────
  function svgNode(tag, attrs = {}, text = "") {
    const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v !== null && v !== undefined) n.setAttribute(k, String(v));
    }
    if (text) n.textContent = text;
    return n;
  }

  function renderOaEcosystemAndVisuals(res) {
    if (el.oaEcosystemLinks) {
      el.oaEcosystemLinks.replaceChildren();
      const links = Array.isArray(res?.ecosystem_links) ? res.ecosystem_links : [];
      if (links.length) {
        const lbl = document.createElement("span");
        lbl.className = "oa-eco-label";
        lbl.textContent = "Bonded Ecosystem:";
        el.oaEcosystemLinks.appendChild(lbl);
        for (const item of links) {
          const a = document.createElement("a");
          a.className = "oa-eco-pill";
          a.href = String(item.url || "https://www.niagads.org");
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          const txt = document.createElement("span");
          txt.textContent = `↗ ${item.label || "NIAGADS"}`;
          a.appendChild(txt);
          if (item.badge) {
            const b = document.createElement("span");
            b.className = "oa-eco-badge";
            b.textContent = String(item.badge);
            a.appendChild(b);
          }
          el.oaEcosystemLinks.appendChild(a);
        }
        el.oaEcosystemLinks.hidden = false;
      } else {
        el.oaEcosystemLinks.hidden = true;
      }
    }

    if (el.oaPaperCredits) {
      el.oaPaperCredits.replaceChildren();
      const papers = Array.isArray(res?.paper_credits) ? res.paper_credits : [];
      if (papers.length) {
        const lbl = document.createElement("span");
        lbl.className = "oa-paper-label";
        lbl.textContent = "📚 Paper Credits:";
        el.oaPaperCredits.appendChild(lbl);
        for (const p of papers) {
          const a = document.createElement("a");
          a.className = "paper-credit-pill";
          a.href = String(p.url || "https://www.niagads.org");
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.title = `${p.title || ""}\n${p.key_contribution || ""}\nAnchor: ${p.niagads_anchor || ""}`;
          const citeSpan = document.createElement("span");
          citeSpan.textContent = `↗ ${p.short_citation || p.id}`;
          a.appendChild(citeSpan);
          if (p.doi) {
            const vSpan = document.createElement("span");
            vSpan.className = "paper-credit-venue";
            vSpan.textContent = String(p.doi);
            a.appendChild(vSpan);
          }
          el.oaPaperCredits.appendChild(a);
        }
        el.oaPaperCredits.hidden = false;
      } else {
        el.oaPaperCredits.hidden = true;
      }
    }

    if (!el.oaVisualContainer) return;
    el.oaVisualContainer.replaceChildren();
    const vis = res?.visual || {};
    const cards = [];

    // 1. GWAS / WGS Associations -log10(p) or Track Count SVG Chart
    if (vis.associations && Array.isArray(vis.associations.items) && vis.associations.items.length) {
      const card = document.createElement("div");
      card.className = "oa-vis-card";
      const head = document.createElement("div");
      head.className = "oa-vis-head";
      const title = document.createElement("h4");
      title.className = "oa-vis-title";
      const sub = document.createElement("span");
      sub.className = "oa-vis-sub";

      const items = vis.associations.items.slice(0, 8);
      const isPval = vis.associations.mode === "pvalues";
      title.textContent = isPval
        ? "NIAGADS Multi-Cohort GWAS / WGS Signals (−log10 p)"
        : "NIAGADS Association Track Coverage";
      sub.textContent = isPval ? "Dashed line: p = 5×10⁻⁸ (−log10 p = 7.30)" : `Top ${items.length} tracks`;
      head.append(title, sub);

      const rowH = 24;
      const topPad = 14;
      const botPad = 16;
      const leftPad = 158;
      const rightPad = 56;
      const width = 500;
      const height = topPad + items.length * rowH + botPad;
      const plotW = width - leftPad - rightPad;
      const maxVal = Math.max(
        isPval ? 8.5 : 1,
        ...items.map((it) => Number(isPval ? it.neg_log10_p : it.count) || 0)
      );

      const svg = svgNode("svg", {
        viewBox: `0 0 ${width} ${height}`,
        class: "oa-vis-svg",
        role: "img",
        "aria-label": title.textContent,
      });

      if (isPval) {
        const threshX = leftPad + Math.min(1, 7.3 / maxVal) * plotW;
        svg.appendChild(
          svgNode("line", {
            x1: threshX.toFixed(1),
            y1: topPad - 6,
            x2: threshX.toFixed(1),
            y2: height - botPad + 4,
            stroke: "#e11d48",
            "stroke-width": "1.3",
            "stroke-dasharray": "4 3",
          })
        );
      }

      items.forEach((it, idx) => {
        const y = topPad + idx * rowH;
        const val = Number(isPval ? it.neg_log10_p : it.count) || 0;
        const barW = Math.max(3, (val / maxVal) * plotW);
        const labelStr = isPval
          ? `${it.variant || "?"} · ${(it.study || it.track || "").slice(0, 12)}`
          : String(it.track || "?").slice(0, 22);
        const isSig = isPval && val >= 7.3;

        svg.appendChild(
          svgNode(
            "text",
            {
              x: leftPad - 8,
              y: y + 13,
              "text-anchor": "end",
              "font-size": "10.5",
              fill: "currentColor",
              opacity: "0.88",
            },
            labelStr
          )
        );
        const rect = svgNode("rect", {
          x: leftPad,
          y: y + 3,
          width: barW.toFixed(1),
          height: 14,
          rx: 4,
          fill: isSig ? "#0f766e" : "#4f46e5",
          opacity: isSig ? "0.92" : "0.75",
        });
        rect.appendChild(
          svgNode(
            "title",
            {},
            isPval
              ? `${it.variant} | Track: ${it.track} | p=${it.pvalue} (-log10p=${val}) | ${it.traits}`
              : `${it.track}: ${val} associations (${it.traits})`
          )
        );
        svg.appendChild(rect);
        svg.appendChild(
          svgNode(
            "text",
            {
              x: (leftPad + barW + 6).toFixed(1),
              y: y + 13,
              "font-size": "10.5",
              "font-weight": "700",
              fill: "currentColor",
            },
            isPval ? val.toFixed(1) : String(val)
          )
        );
      });

      card.append(head, svg);
      cards.push(card);
    }

    // 2. GRCh38 Canonical Transcript & Exon Architecture Track
    if (vis.gene_structure && Array.isArray(vis.gene_structure.exons) && vis.gene_structure.exons.length) {
      const gs = vis.gene_structure;
      const card = document.createElement("div");
      card.className = "oa-vis-card";
      const head = document.createElement("div");
      head.className = "oa-vis-head";
      const title = document.createElement("h4");
      title.className = "oa-vis-title";
      title.textContent = `${gs.gene} GRCh38 Exon Architecture (${gs.transcript_name || gs.transcript_id})`;
      const sub = document.createElement("span");
      sub.className = "oa-vis-sub";
      const spanKb = Math.max(0.1, (Number(gs.end) - Number(gs.start)) / 1000).toFixed(1);
      sub.textContent = `${gs.chrom}:${Number(gs.start).toLocaleString()}–${Number(gs.end).toLocaleString()} (${spanKb} kb · ${gs.exon_count} exons)`;
      head.append(title, sub);

      const width = 500;
      const height = 74;
      const padX = 18;
      const plotW = width - padX * 2;
      const gStart = Number(gs.start) || 0;
      const gSpan = Math.max(1, (Number(gs.end) || gStart + 1) - gStart);

      const svg = svgNode("svg", {
        viewBox: `0 0 ${width} ${height}`,
        class: "oa-vis-svg",
        role: "img",
        "aria-label": `${gs.gene} canonical transcript exon diagram`,
      });

      // Intron backbone
      svg.appendChild(
        svgNode("line", {
          x1: padX,
          y1: 34,
          x2: width - padX,
          y2: 34,
          stroke: "currentColor",
          "stroke-opacity": "0.35",
          "stroke-width": "2",
        })
      );

      // Exon blocks
      for (const ex of gs.exons) {
        const x1 = padX + ((Number(ex.start) - gStart) / gSpan) * plotW;
        const x2 = padX + ((Number(ex.end) - gStart) / gSpan) * plotW;
        const w = Math.max(3.2, x2 - x1);
        const r = svgNode("rect", {
          x: x1.toFixed(1),
          y: 20,
          width: w.toFixed(1),
          height: 28,
          rx: 2,
          fill: "#0f766e",
        });
        r.appendChild(
          svgNode(
            "title",
            {},
            `Exon ${ex.rank} (${ex.id}): ${gs.chrom}:${Number(ex.start).toLocaleString()}-${Number(ex.end).toLocaleString()} (${Number(ex.end) - Number(ex.start) + 1} bp)`
          )
        );
        svg.appendChild(r);
      }

      svg.appendChild(
        svgNode("text", { x: padX, y: 64, "font-size": "10", fill: "currentColor", opacity: "0.7" }, `5' ${gs.chrom}:${gStart.toLocaleString()}`)
      );
      svg.appendChild(
        svgNode(
          "text",
          { x: width - padX, y: 64, "text-anchor": "end", "font-size": "10", fill: "currentColor", opacity: "0.7" },
          `${gs.chrom}:${Number(gs.end).toLocaleString()} (${gs.total_transcripts || 1} isoforms)`
        )
      );

      card.append(head, svg);
      cards.push(card);
    }

    // 3. Population Allele Frequencies SVG Bars
    if (Array.isArray(vis.allele_frequencies) && vis.allele_frequencies.length) {
      const freqs = vis.allele_frequencies;
      const card = document.createElement("div");
      card.className = "oa-vis-card";
      const head = document.createElement("div");
      head.className = "oa-vis-head";
      const title = document.createElement("h4");
      title.className = "oa-vis-title";
      title.textContent = `Reference Population Allele Frequencies (${freqs[0].variant})`;
      const sub = document.createElement("span");
      sub.className = "oa-vis-sub";
      sub.textContent = "NIAGADS / ALFA / gnomAD / TOPMed";
      head.append(title, sub);

      const rowH = 22;
      const leftPad = 128;
      const rightPad = 64;
      const width = 460;
      const height = 10 + freqs.length * rowH + 8;
      const plotW = width - leftPad - rightPad;
      const maxAf = Math.max(0.05, ...freqs.map((f) => Number(f.af) || 0));

      const svg = svgNode("svg", {
        viewBox: `0 0 ${width} ${height}`,
        class: "oa-vis-svg",
        role: "img",
        "aria-label": title.textContent,
      });

      freqs.forEach((f, idx) => {
        const y = 8 + idx * rowH;
        const val = Number(f.af) || 0;
        const w = Math.max(2.5, (val / maxAf) * plotW);
        svg.appendChild(
          svgNode("text", { x: leftPad - 8, y: y + 13, "text-anchor": "end", "font-size": "10.5", fill: "currentColor", opacity: "0.85" }, f.population)
        );
        svg.appendChild(
          svgNode("rect", { x: leftPad, y: y + 3, width: w.toFixed(1), height: 13, rx: 3.5, fill: "#7c3aed", opacity: "0.85" })
        );
        svg.appendChild(
          svgNode("text", { x: (leftPad + w + 6).toFixed(1), y: y + 13, "font-size": "10.5", "font-weight": "700", fill: "currentColor" }, `${(val * 100).toFixed(2)}%`)
        );
      });

      card.append(head, svg);
      cards.push(card);
    }

    // 4. NIAGADS v0.6 Multi-Track 2D-Pannable LocusZoom + FILER PIP + FunGen-xQTL Colocalization
    if (vis.locuszoom && Array.isArray(vis.locuszoom.variants) && vis.locuszoom.variants.length) {
      const lz = vis.locuszoom;
      const locusTitle = lz.gene || lz.locus || "Locus";
      const csCount = Array.isArray(lz.credible_set_95) ? lz.credible_set_95.length : Number(lz.credible_set_size || 0);
      const card = document.createElement("div");
      card.className = "oa-vis-card oa-vis-wide";

      const head = document.createElement("div");
      head.className = "oa-vis-head";
      const title = document.createElement("h4");
      title.className = "oa-vis-title";
      title.textContent = `${locusTitle} (${lz.chrom}) Multi-Track NIAGADS LocusZoom · FILER PIP · FunGen-xQTL Colocalization`;
      const sub = document.createElement("span");
      sub.className = "oa-vis-sub";
      sub.textContent = `Coloc PP.H4 = ${(Number(lz.coloc?.["PP.H4"] || 0) * 100).toFixed(1)}% · 95% CS = ${csCount} SNP(s) · FILER Tracks = ${Number(lz.filer_tracks || 0).toLocaleString()}`;
      head.append(title, sub);

      const toolbar = document.createElement("div");
      toolbar.className = "locuszoom-toolbar";
      toolbar.innerHTML = `
        <div class="lz-legend-pills">
          <span><i class="lz-dot" style="background:#dc2626"></i>r² ≥ 0.8 / Lead</span>
          <span><i class="lz-dot" style="background:#ea580c"></i>r² 0.6–0.8</span>
          <span><i class="lz-dot" style="background:#0f766e"></i>FILER Enhancer Peak</span>
          <span><i class="lz-dot" style="background:#7c3aed"></i>FunGen-xQTL (−log10 p)</span>
        </div>
        <div class="lz-zoom-controls" role="group" aria-label="Genomic LocusZoom magnification">
          <button type="button" class="lz-zoom-btn active" data-lz-zoom="1">1× Fit</button>
          <button type="button" class="lz-zoom-btn" data-lz-zoom="1.8">1.8× Pan</button>
          <button type="button" class="lz-zoom-btn" data-lz-zoom="2.6">2.6× Fine</button>
        </div>
      `;

      const viewport = document.createElement("div");
      viewport.className = "locuszoom-pan-viewport";
      viewport.tabIndex = 0;
      viewport.setAttribute("role", "region");
      viewport.setAttribute(
        "aria-label",
        `Interactive 2D-pannable NIAGADS LocusZoom and colocalization tracks for ${locusTitle}`
      );

      const baseW = 780;
      const baseH = 340;
      const padL = 88;
      const padR = 26;
      const plotW = baseW - padL - padR;

      const svg = svgNode("svg", {
        viewBox: `0 0 ${baseW} ${baseH}`,
        class: "locuszoom-pan-surface",
        role: "img",
        "aria-label": `${locusTitle} GWAS, FILER PIP, and FunGen-xQTL colocalization plot`,
      });
      svg.style.inlineSize = "100%";
      svg.style.blockSize = "auto";

      const vList = lz.variants;
      const minPos = Math.min(...vList.map((v) => Number(v.pos) || 0)) - 2500;
      const maxPos = Math.max(...vList.map((v) => Number(v.pos) || 0)) + 2500;
      const span = Math.max(1000, maxPos - minPos);
      const xOf = (pos) => padL + ((Number(pos) - minPos) / span) * plotW;
      const gwasOf = (v) => Number(v.gwas_nlp ?? v.gwas_neg_log10_p) || 0;
      const xqtlOf = (v) => Number(v.xqtl_nlp ?? v.xqtl_neg_log10_p) || 0;
      const filerHitOf = (v) => Boolean(v.filer_hit ?? v.filer_enhancer_overlap);

      // Track bands: [Track 1: GWAS -log10(p) y=16..114], [Track 2: FILER PIP y=134..216], [Track 3: FunGen-xQTL y=236..312]
      const tracks = [
        { label: "GWAS −log10(p)", top: 18, bot: 112, maxY: Math.max(10, ...vList.map(gwasOf)) * 1.08 },
        { label: "FILER PIP", top: 136, bot: 214, maxY: 1.05 },
        { label: "FunGen xQTL", top: 238, bot: 312, maxY: Math.max(8, ...vList.map(xqtlOf)) * 1.1 },
      ];

      for (const tr of tracks) {
        svg.appendChild(
          svgNode("rect", {
            x: padL,
            y: tr.top,
            width: plotW,
            height: tr.bot - tr.top,
            rx: 4,
            fill: "currentColor",
            "fill-opacity": "0.035",
          })
        );
        svg.appendChild(
          svgNode(
            "text",
            { x: padL - 8, y: (tr.top + tr.bot) / 2 + 3, "text-anchor": "end", "font-size": "9.5", "font-weight": "600", fill: "currentColor", opacity: "0.78" },
            tr.label
          )
        );
      }

      // Genome-wide significance threshold in Track 1
      const gwsY = tracks[0].bot - (7.3 / tracks[0].maxY) * (tracks[0].bot - tracks[0].top);
      if (gwsY > tracks[0].top) {
        svg.appendChild(
          svgNode("line", {
            x1: padL,
            y1: gwsY.toFixed(1),
            x2: baseW - padR,
            y2: gwsY.toFixed(1),
            stroke: "#e11d48",
            "stroke-width": "1.1",
            "stroke-dasharray": "4 3",
          })
        );
      }

      const ldColor = (r2) => {
        if (r2 >= 0.8) return "#dc2626";
        if (r2 >= 0.6) return "#ea580c";
        if (r2 >= 0.4) return "#16a34a";
        return "#2563eb";
      };

      vList.forEach((v) => {
        const cx = xOf(v.pos);
        const r2 = Number(v.ld_r2 || 0);
        const gwasVal = gwasOf(v);
        const xqtlVal = xqtlOf(v);
        const isFilerHit = filerHitOf(v);
        const isLead = lz.lead_rsid ? v.rsid === lz.lead_rsid : r2 >= 0.99;
        const gY = tracks[0].bot - (Math.min(tracks[0].maxY, gwasVal) / tracks[0].maxY) * (tracks[0].bot - tracks[0].top);
        const pipVal = Number(v.pip_filer) || 0;
        const pipH = Math.max(2, (pipVal / tracks[1].maxY) * (tracks[1].bot - tracks[1].top));
        const xY = tracks[2].bot - (Math.min(tracks[2].maxY, xqtlVal) / tracks[2].maxY) * (tracks[2].bot - tracks[2].top);

        // Vertical guide for credible-set variants
        if (v.in_credible_set_95) {
          svg.appendChild(
            svgNode("line", {
              x1: cx.toFixed(1),
              y1: tracks[0].top,
              x2: cx.toFixed(1),
              y2: tracks[2].bot,
              stroke: "#0f766e",
              "stroke-opacity": "0.22",
              "stroke-dasharray": "2 2",
            })
          );
        }

        // Track 1: GWAS point (purple lead SNP)
        const tipText = `${v.rsid} (${lz.chrom}:${Number(v.pos).toLocaleString()}) | GWAS -log10p=${gwasVal} | FILER PIP=${(pipVal * 100).toFixed(1)}% | xQTL -log10p=${xqtlVal} | r²=${r2} | ${v.annot || v.annotation || ""}`;
        const dot = svgNode("circle", {
          cx: cx.toFixed(1),
          cy: gY.toFixed(1),
          r: isLead ? "6.2" : v.in_credible_set_95 ? "5" : "4",
          fill: isLead ? "#7c3aed" : ldColor(r2),
          stroke: "#ffffff",
          "stroke-width": "1.2",
        });
        dot.appendChild(svgNode("title", {}, tipText));
        svg.appendChild(dot);

        if (isLead || pipVal >= 0.15) {
          const labelAnchor = cx > baseW - 180 ? "end" : "start";
          const labelX = labelAnchor === "end" ? cx - 8 : cx + 8;
          svg.appendChild(
            svgNode(
              "text",
              { x: labelX.toFixed(1), y: (gY + 3).toFixed(1), "text-anchor": labelAnchor, "font-size": "9.5", "font-weight": "700", fill: "currentColor" },
              `${v.rsid} (PIP ${(pipVal * 100).toFixed(1)}%)`
            )
          );
        }

        // Track 2: FILER-weighted PIP bar
        const pipBar = svgNode("rect", {
          x: (cx - 4.5).toFixed(1),
          y: (tracks[1].bot - pipH).toFixed(1),
          width: "9",
          height: pipH.toFixed(1),
          rx: "2",
          fill: isFilerHit ? "#0f766e" : "#64748b",
        });
        pipBar.appendChild(svgNode("title", {}, tipText));
        svg.appendChild(pipBar);

        // Track 3: FunGen-xQTL colocalization lollipop
        svg.appendChild(
          svgNode("line", {
            x1: cx.toFixed(1),
            y1: tracks[2].bot,
            x2: cx.toFixed(1),
            y2: xY.toFixed(1),
            stroke: "#7c3aed",
            "stroke-opacity": "0.55",
            "stroke-width": "1.6",
          })
        );
        const xDot = svgNode("circle", {
          cx: cx.toFixed(1),
          cy: xY.toFixed(1),
          r: isFilerHit ? "4.6" : "3.6",
          fill: "#7c3aed",
        });
        xDot.appendChild(svgNode("title", {}, tipText));
        svg.appendChild(xDot);
      });

      svg.appendChild(
        svgNode("text", { x: padL, y: baseH - 8, "font-size": "9.5", fill: "currentColor", opacity: "0.72" }, `${lz.chrom}:${minPos.toLocaleString()} (GRCh38)`)
      );
      svg.appendChild(
        svgNode("text", { x: baseW - padR, y: baseH - 8, "text-anchor": "end", "font-size": "9.5", fill: "currentColor", opacity: "0.72" }, `${lz.chrom}:${maxPos.toLocaleString()} · Drag / Trackpad 2D Pan when zoomed`)
      );

      viewport.appendChild(svg);

      for (const zBtn of toolbar.querySelectorAll("[data-lz-zoom]")) {
        zBtn.addEventListener("click", () => {
          const factor = Number(zBtn.dataset.lzZoom) || 1;
          for (const b of toolbar.querySelectorAll("[data-lz-zoom]")) b.classList.toggle("active", b === zBtn);
          if (factor <= 1.01) {
            svg.style.inlineSize = "100%";
            svg.style.blockSize = "auto";
            viewport.scrollTo({ left: 0, top: 0, behavior: "smooth" });
          } else {
            const targetW = Math.round(baseW * factor);
            const targetH = Math.round(baseH * Math.min(1.45, 1 + (factor - 1) * 0.28));
            svg.style.inlineSize = `${targetW}px`;
            svg.style.blockSize = `${targetH}px`;
            const centerPos = Number(lz.lead_pos) || Number(vList[0]?.pos) || minPos;
            const leadX = (xOf(centerPos) / baseW) * targetW;
            viewport.scrollLeft = Math.max(0, leadX - viewport.clientWidth / 2);
          }
        });
      }

      card.append(head, toolbar, viewport);
      cards.push(card);
    }

    // 5. Two-Sample MR + 4-Ancestry NIAGADS PRS Calibration Chart
    if (vis.mr_prs && Array.isArray(vis.mr_prs.prs) && vis.mr_prs.prs.length) {
      const mp = vis.mr_prs;
      const card = document.createElement("div");
      card.className = "oa-vis-card oa-vis-wide";
      const head = document.createElement("div");
      head.className = "oa-vis-head";
      const title = document.createElement("h4");
      title.className = "oa-vis-title";
      title.textContent = "Cross-Ancestry NIAGADS PRS Relative Risk & Transferability (EUR · AFR · AMR · EAS)";
      const sub = document.createElement("span");
      sub.className = "oa-vis-sub";
      const rawP = mp.mr?.ivw?.pvalue ?? mp.mr?.ivw?.p_value;
      const fmtP = typeof rawP === "number" ? rawP.toExponential(2) : (rawP ?? "—");
      sub.textContent = `IVW Causal OR = ${mp.mr?.ivw?.or ?? "—"}× (p = ${fmtP})`;
      head.append(title, sub);

      const prsRows = mp.prs;
      const width = 560;
      const rowH = 28;
      const leftPad = 175;
      const rightPad = 95;
      const height = 16 + prsRows.length * rowH + 10;
      const plotW = width - leftPad - rightPad;
      const maxOr = Math.max(2.5, ...prsRows.map((r) => Number(r.relative_or) || 1));

      const svg = svgNode("svg", {
        viewBox: `0 0 ${width} ${height}`,
        class: "oa-vis-svg",
        role: "img",
        "aria-label": title.textContent,
      });

      prsRows.forEach((r, idx) => {
        const y = 12 + idx * rowH;
        const val = Number(r.relative_or) || 1;
        const barW = Math.max(6, (val / maxOr) * plotW);
        const cohortName = String(r.cohort || r.label || "").split("(")[0].trim();
        svg.appendChild(
          svgNode("text", { x: leftPad - 8, y: y + 15, "text-anchor": "end", "font-size": "10.5", fill: "currentColor" }, `${r.ancestry} · ${cohortName}`)
        );
        svg.appendChild(
          svgNode("rect", { x: leftPad, y: y + 4, width: barW.toFixed(1), height: 15, rx: 4, fill: idx === 1 ? "#0284c7" : "#0f766e", opacity: "0.88" })
        );
        svg.appendChild(
          svgNode("text", { x: (leftPad + barW + 7).toFixed(1), y: y + 15, "font-size": "10", "font-weight": "700", fill: "currentColor" }, `${val.toFixed(2)}× (${r.percentile}th pct)`)
        );
      });

      card.append(head, svg);
      cards.push(card);
    }

    // 6. ADSP Release 5 + FILER 5-Modality Rare/Non-Coding Regulatory Impact Profile
    if (vis.regulatory_profile && Array.isArray(vis.regulatory_profile.modalities)) {
      const rp = vis.regulatory_profile;
      const card = document.createElement("div");
      card.className = "oa-vis-card oa-vis-wide";
      const head = document.createElement("div");
      head.className = "oa-vis-head";
      const title = document.createElement("h4");
      title.className = "oa-vis-title";
      const rpLabel = rp.gene ? `${rp.target || rp.variant} (${rp.gene})` : (rp.target || rp.variant || "Variant");
      title.textContent = `ADSP R5 + FILER Deep-Regulatory Perturbation Profile — ${rpLabel}`;
      const sub = document.createElement("span");
      sub.className = "oa-vis-sub";
      sub.textContent = `Composite Impact: ${rp.composite}/100`;
      head.append(title, sub);

      const mods = rp.modalities;
      const width = 560;
      const rowH = 26;
      const leftPad = 195;
      const rightPad = 56;
      const height = 14 + mods.length * rowH + 8;
      const plotW = width - leftPad - rightPad;

      const svg = svgNode("svg", {
        viewBox: `0 0 ${width} ${height}`,
        class: "oa-vis-svg",
        role: "img",
        "aria-label": title.textContent,
      });

      mods.forEach((m, idx) => {
        const y = 10 + idx * rowH;
        const sc = Math.max(0, Math.min(100, Number(m.score) || 0));
        const barW = Math.max(4, (sc / 100) * plotW);
        svg.appendChild(
          svgNode("text", { x: leftPad - 8, y: y + 14, "text-anchor": "end", "font-size": "10", fill: "currentColor" }, String(m.modality).slice(0, 30))
        );
        svg.appendChild(
          svgNode("rect", { x: leftPad, y: y + 3, width: barW.toFixed(1), height: 14, rx: 4, fill: sc >= 75 ? "#0f766e" : "#4f46e5", opacity: "0.88" })
        );
        svg.appendChild(
          svgNode("text", { x: (leftPad + barW + 6).toFixed(1), y: y + 14, "font-size": "10", "font-weight": "700", fill: "currentColor" }, `${sc}/100`)
        );
      });

      card.append(head, svg);
      cards.push(card);
    }

    // 7. v0.7 TAD-Window 6-Modality ColocBoost + 4-Ancestry ADSP emeraLD MESuSiE Chart
    if (vis.colocboost_mesusie && Array.isArray(vis.colocboost_mesusie.modalities)) {
      const cb = vis.colocboost_mesusie;
      const anc0 = Array.isArray(cb.ancestries) && cb.ancestries.length ? cb.ancestries[0] : {};
      const singlePipNum = Number(cb.mesusie_single_ancestry_pip ?? anc0.pip_single ?? 0.528);
      const sharedPipNum = Number(cb.mesusie_shared_pip ?? anc0.pip_mesusie_shared ?? cb.cos_joint ?? 0.96);
      const card = document.createElement("div");
      card.className = "oa-vis-card oa-vis-wide";
      const head = document.createElement("div");
      head.className = "oa-vis-head";
      const title = document.createElement("h4");
      title.className = "oa-vis-title";
      title.textContent = `${cb.gene} (${cb.lead_variant}) · 6-Modality FunGen ColocBoost CoS + 4-Ancestry MESuSiE`;
      const sub = document.createElement("span");
      sub.className = "oa-vis-sub";
      sub.textContent = `MESuSiE PIP: ${(singlePipNum * 100).toFixed(1)}% → ${(sharedPipNum * 100).toFixed(1)}% · Joint 95% CS = ${cb.joint_cs_size ?? 1}`;
      head.append(title, sub);

      const mods = cb.modalities;
      const width = 580;
      const rowH = 25;
      const leftPad = 198;
      const rightPad = 78;
      const height = 16 + (mods.length + 2) * rowH + 10;
      const plotW = width - leftPad - rightPad;

      const svg = svgNode("svg", {
        viewBox: `0 0 ${width} ${height}`,
        class: "oa-vis-svg",
        role: "img",
        "aria-label": title.textContent,
      });

      const threshX = leftPad + 0.75 * plotW;
      svg.appendChild(
        svgNode("line", {
          x1: threshX.toFixed(1),
          y1: 8,
          x2: threshX.toFixed(1),
          y2: height - 10,
          stroke: "#0d9488",
          "stroke-width": "1.2",
          "stroke-dasharray": "4 3",
        })
      );

      mods.forEach((m, idx) => {
        const y = 12 + idx * rowH;
        const cos = Math.max(0, Math.min(1, Number(m.cos_score ?? m.cos_prob) || 0));
        const barW = Math.max(4, cos * plotW);
        svg.appendChild(
          svgNode("text", { x: leftPad - 8, y: y + 14, "text-anchor": "end", "font-size": "10", fill: "currentColor" }, String(m.modality).slice(0, 28))
        );
        svg.appendChild(
          svgNode("rect", { x: leftPad, y: y + 3, width: barW.toFixed(1), height: 14, rx: 4, fill: cos >= 0.75 ? "#0f766e" : "#64748b", opacity: "0.88" })
        );
        svg.appendChild(
          svgNode("text", { x: (leftPad + barW + 6).toFixed(1), y: y + 14, "font-size": "9.8", "font-weight": "700", fill: "currentColor" }, `${(cos * 100).toFixed(1)}%`)
        );
      });

      const pipRows = [
        { label: "EUR Single-Ancestry PIP", val: singlePipNum, color: "#6366f1" },
        { label: "ADSP 4-Ancestry MESuSiE PIP", val: sharedPipNum, color: "#0284c7" },
      ];
      pipRows.forEach((pr, j) => {
        const y = 16 + (mods.length + j) * rowH;
        const barW = Math.max(4, Math.min(1, pr.val) * plotW);
        svg.appendChild(
          svgNode("text", { x: leftPad - 8, y: y + 14, "text-anchor": "end", "font-size": "10", "font-weight": "700", fill: "currentColor" }, pr.label)
        );
        svg.appendChild(
          svgNode("rect", { x: leftPad, y: y + 3, width: barW.toFixed(1), height: 14, rx: 4, fill: pr.color, opacity: "0.92" })
        );
        svg.appendChild(
          svgNode("text", { x: (leftPad + barW + 6).toFixed(1), y: y + 14, "font-size": "9.8", "font-weight": "700", fill: "currentColor" }, `${(pr.val * 100).toFixed(1)}%`)
        );
      });

      card.append(head, svg);
      cards.push(card);
    }

    // 8. v0.7 APOEε4 BBB Resilience Modifiers + Two-Epoch SEA-AD CPS Trajectory Chart
    if (vis.resilience_xwas_seaad && Array.isArray(vis.resilience_xwas_seaad.resilience_modifiers)) {
      const rx = vis.resilience_xwas_seaad;
      const card = document.createElement("div");
      card.className = "oa-vis-card oa-vis-wide";
      const head = document.createElement("div");
      head.className = "oa-vis-head";
      const title = document.createElement("h4");
      title.className = "oa-vis-title";
      title.textContent = "APOEε4 Resilience Protective Odds Ratios (FN1 · COL6A2 · PLCG2) & chrX XWAS";
      const sub = document.createElement("span");
      sub.className = "oa-vis-sub";
      sub.textContent = "Dashed line: Neutral OR = 1.00 (lower = stronger protection)";
      head.append(title, sub);

      const mods = rx.resilience_modifiers.slice(0, 5);
      const width = 580;
      const rowH = 26;
      const leftPad = 198;
      const rightPad = 24;
      const height = 16 + mods.length * rowH + 10;
      const plotW = width - leftPad - rightPad;
      const maxOr = 1.02;

      const svg = svgNode("svg", {
        viewBox: `0 0 ${width} ${height}`,
        class: "oa-vis-svg",
        role: "img",
        "aria-label": title.textContent,
      });

      const neutralX = leftPad + (1.0 / maxOr) * plotW;
      svg.appendChild(
        svgNode("line", {
          x1: neutralX.toFixed(1),
          y1: 8,
          x2: neutralX.toFixed(1),
          y2: height - 8,
          stroke: "#e11d48",
          "stroke-width": "1.3",
          "stroke-dasharray": "4 3",
        })
      );

      mods.forEach((m, idx) => {
        const y = 12 + idx * rowH;
        const orVal = Math.max(0.05, Math.min(maxOr, Number(m.protective_or) || 0.5));
        const barW = Math.max(6, (orVal / maxOr) * plotW);
        const delayYr = m.onset_delay_yr ?? m.onset_delay_years ?? 0;
        const shortVar = String(m.variant || "").split(" ")[0];
        svg.appendChild(
          svgNode("text", { x: leftPad - 8, y: y + 14, "text-anchor": "end", "font-size": "10", fill: "currentColor" }, `${m.gene} (${shortVar})`)
        );
        svg.appendChild(
          svgNode("rect", { x: leftPad, y: y + 3, width: barW.toFixed(1), height: 14, rx: 4, fill: m.gene === "FN1" ? "#0f766e" : "#0284c7", opacity: "0.9" })
        );
        svg.appendChild(
          svgNode(
            "text",
            { x: (leftPad + barW + 6).toFixed(1), y: y + 14, "font-size": "9.8", "font-weight": "700", fill: "currentColor" },
            `OR ${orVal.toFixed(2)} (+${delayYr}y)`
          )
        );
      });

      card.append(head, svg);
      cards.push(card);
    }

    // 9. v0.8 NIAGADS ADSP Release 5 (58,507 WGS) Statistical Power & Multi-Ancestry Power Curves
    if (vis.adsp_r5_power_dar && Array.isArray(vis.adsp_r5_power_dar.strata)) {
      const pd = vis.adsp_r5_power_dar;
      const strata = pd.strata;

      // 9a. Ancestry-Stratified Statistical Power Bar Chart (with 80% Power Threshold & MDE_80)
      const cardBar = document.createElement("div");
      cardBar.className = "oa-vis-card oa-vis-wide";
      const headBar = document.createElement("div");
      headBar.className = "oa-vis-head";
      const titleBar = document.createElement("h4");
      titleBar.className = "oa-vis-title";
      titleBar.textContent = `${pd.gene} (${pd.lead_variant}) · ADSP Release 5 (58,507 WGS) Statistical Power by Ancestry`;
      const subBar = document.createElement("span");
      subBar.className = "oa-vis-sub";
      subBar.textContent = `α = ${Number(pd.alpha || 2.5e-6).toExponential(1)} · Dashed line = 80% Power`;
      headBar.append(titleBar, subBar);

      const width = 780;
      const rowH = 26;
      const leftPad = 148;
      const rightPad = 152;
      const height = 24 + strata.length * rowH + 10;
      const plotW = width - leftPad - rightPad;

      const svgBar = svgNode("svg", {
        viewBox: `0 0 ${width} ${height}`,
        class: "oa-vis-svg",
        role: "img",
        "aria-label": titleBar.textContent,
      });

      const x80 = leftPad + 0.80 * plotW;
      svgBar.appendChild(
        svgNode("text", { x: x80.toFixed(1), y: 12, "text-anchor": "middle", "font-size": "9.2", "font-weight": "700", fill: "#0d9488" }, "80% Power")
      );
      svgBar.appendChild(
        svgNode("line", {
          x1: x80.toFixed(1),
          y1: 16,
          x2: x80.toFixed(1),
          y2: height - 6,
          stroke: "#0d9488",
          "stroke-width": "1.3",
          "stroke-dasharray": "4 3",
        })
      );

      const ANC_COLORS = {
        NHW: "#4f46e5",
        HIS: "#0284c7",
        AA: "#0f766e",
        ASN: "#7c3aed",
        ALL: "#d97706",
      };

      strata.forEach((st, idx) => {
        const y = 19 + idx * rowH;
        const pwr = Math.max(0, Math.min(100, Number(st.power_pct) || 0));
        const barW = Math.max(4, (pwr / 100) * plotW);
        const col = ANC_COLORS[st.ancestry] || "#0f766e";
        const lbl = `${st.ancestry} (N=${Number(st.n_subjects || 0).toLocaleString()})`;

        svgBar.appendChild(
          svgNode(
            "text",
            {
              x: leftPad - 10,
              y: y + 14,
              "text-anchor": "end",
              "font-size": "10.2",
              "font-weight": st.ancestry === "ALL" ? "700" : "500",
              fill: "currentColor",
            },
            lbl
          )
        );
        svgBar.appendChild(
          svgNode("rect", {
            x: leftPad,
            y: y + 3,
            width: plotW.toFixed(1),
            height: 14,
            rx: 4,
            fill: "currentColor",
            opacity: "0.07",
          })
        );
        const rect = svgNode("rect", {
          x: leftPad,
          y: y + 3,
          width: barW.toFixed(1),
          height: 14,
          rx: 4,
          fill: col,
          opacity: pwr >= 80 ? "0.94" : "0.72",
        });
        rect.appendChild(
          svgNode(
            "title",
            {},
            `${st.stratum_label} | N=${st.n_subjects} | MAF/cMAF=${st.frequency} | Power=${pwr.toFixed(1)}% | 80% MDE=${st.mde_80}`
          )
        );
        svgBar.appendChild(rect);
        svgBar.appendChild(
          svgNode(
            "text",
            {
              x: (leftPad + plotW + 10).toFixed(1),
              y: y + 14,
              "font-size": "10",
              "font-weight": "700",
              fill: "currentColor",
            },
            `${pwr.toFixed(1)}% (${st.mde_80})`
          )
        );
      });

      cardBar.append(headBar, svgBar);
      cards.push(cardBar);

      // 9b. Multi-Ancestry Effect-Size Power Sweep Curve
      if (Array.isArray(pd.power_curves) && pd.power_curves.length) {
        const cardCurve = document.createElement("div");
        cardCurve.className = "oa-vis-card oa-vis-wide";
        const headCurve = document.createElement("div");
        headCurve.className = "oa-vis-head";
        const titleCurve = document.createElement("h4");
        titleCurve.className = "oa-vis-title";
        titleCurve.textContent = `${pd.gene} · Multi-Ancestry Power Curve Across Effect Sizes (${pd.is_quantitative ? "β SD" : "Odds Ratio"})`;
        const subCurve = document.createElement("span");
        subCurve.className = "oa-vis-sub";
        subCurve.textContent = `${pd.phenotype_label}`;
        headCurve.append(titleCurve, subCurve);

        const cw = 780;
        const ch = 186;
        const cLeft = 48;
        const cRight = 108;
        const cTop = 16;
        const cBot = 28;
        const cPlotW = cw - cLeft - cRight;
        const cPlotH = ch - cTop - cBot;

        const svgCurve = svgNode("svg", {
          viewBox: `0 0 ${cw} ${ch}`,
          class: "oa-vis-svg",
          role: "img",
          "aria-label": titleCurve.textContent,
        });

        const xs = pd.power_curves[0].points.map((p) => Number(p.x));
        const minX = Math.min(...xs);
        const maxX = Math.max(...xs);
        const spanX = Math.max(0.01, maxX - minX);

        // Horizontal 80% power line
        const y80 = cTop + (1 - 0.80) * cPlotH;
        svgCurve.appendChild(
          svgNode("line", {
            x1: cLeft,
            y1: y80.toFixed(1),
            x2: cw - cRight,
            y2: y80.toFixed(1),
            stroke: "#e11d48",
            "stroke-width": "1.1",
            "stroke-dasharray": "4 3",
          })
        );
        svgCurve.appendChild(
          svgNode("text", { x: cLeft - 6, y: y80 + 3, "text-anchor": "end", "font-size": "9", fill: "#e11d48" }, "80%")
        );
        svgCurve.appendChild(
          svgNode("text", { x: cLeft - 6, y: cTop + 4, "text-anchor": "end", "font-size": "9", fill: "currentColor", opacity: "0.7" }, "100%")
        );
        svgCurve.appendChild(
          svgNode("text", { x: cLeft - 6, y: cTop + cPlotH, "text-anchor": "end", "font-size": "9", fill: "currentColor", opacity: "0.7" }, "0%")
        );

        xs.forEach((xv) => {
          const px = cLeft + ((xv - minX) / spanX) * cPlotW;
          svgCurve.appendChild(
            svgNode(
              "text",
              { x: px.toFixed(1), y: ch - 8, "text-anchor": "middle", "font-size": "9.2", fill: "currentColor", opacity: "0.8" },
              pd.is_quantitative ? `${xv.toFixed(2)}` : `${xv.toFixed(2)}×`
            )
          );
        });

        pd.power_curves.forEach((series, sIdx) => {
          const col = ANC_COLORS[series.ancestry] || "#0f766e";
          const ptsStr = series.points
            .map((pt) => {
              const px = cLeft + ((Number(pt.x) - minX) / spanX) * cPlotW;
              const py = cTop + (1 - Math.max(0, Math.min(100, Number(pt.power_pct))) / 100) * cPlotH;
              return `${px.toFixed(1)},${py.toFixed(1)}`;
            })
            .join(" ");
          svgCurve.appendChild(
            svgNode("polyline", {
              points: ptsStr,
              fill: "none",
              stroke: col,
              "stroke-width": series.ancestry === "ALL" ? "2.6" : "1.9",
              "stroke-linecap": "round",
              "stroke-linejoin": "round",
            })
          );
          series.points.forEach((pt) => {
            const px = cLeft + ((Number(pt.x) - minX) / spanX) * cPlotW;
            const py = cTop + (1 - Math.max(0, Math.min(100, Number(pt.power_pct))) / 100) * cPlotH;
            svgCurve.appendChild(svgNode("circle", { cx: px.toFixed(1), cy: py.toFixed(1), r: "2.7", fill: col }));
          });
          // Legend row on right
          const ly = cTop + 12 + sIdx * 20;
          svgCurve.appendChild(svgNode("rect", { x: cw - cRight + 12, y: ly - 7, width: 10, height: 10, rx: 2, fill: col }));
          svgCurve.appendChild(
            svgNode("text", { x: cw - cRight + 27, y: ly + 1, "font-size": "9.5", "font-weight": "600", fill: "currentColor" }, series.ancestry)
          );
        });

        cardCurve.append(headCurve, svgCurve);
        cards.push(cardCurve);
      }
    }

    if (cards.length) {
      // Attach 1-click Vector .svg & 300-DPI .png export controls to every NIAGADS chart card
      cards.forEach((cardEl, idx) => {
        const svgEl = cardEl.querySelector("svg");
        const headEl = cardEl.querySelector(".oa-vis-head");
        if (!svgEl || !headEl) return;
        const subEl = headEl.querySelector(".oa-vis-sub");
        const rightWrap = document.createElement("div");
        rightWrap.className = "oa-vis-head-right";
        if (subEl) rightWrap.appendChild(subEl);

        const baseSlug = `ligase_niagads_${(state.lastOaResult?.target || "locus").replace(/[^a-zA-Z0-9_-]/g, "_")}_${idx + 1}`;
        const svgBtn = document.createElement("button");
        svgBtn.type = "button";
        svgBtn.className = "oa-vis-export-btn";
        svgBtn.textContent = "⬇ SVG";
        svgBtn.title = "Download publication vector SVG figure";
        svgBtn.addEventListener("click", () => downloadInlineSvgFigure(svgEl, `${baseSlug}.svg`, "svg"));

        const pngBtn = document.createElement("button");
        pngBtn.type = "button";
        pngBtn.className = "oa-vis-export-btn";
        pngBtn.textContent = "⬇ PNG";
        pngBtn.title = "Download high-DPI PNG figure";
        pngBtn.addEventListener("click", () => downloadInlineSvgFigure(svgEl, `${baseSlug}.png`, "png"));

        rightWrap.append(svgBtn, pngBtn);
        headEl.appendChild(rightWrap);
      });

      const grid = document.createElement("div");
      grid.className = "oa-vis-grid";
      for (const c of cards) grid.appendChild(c);
      el.oaVisualContainer.appendChild(grid);
      el.oaVisualContainer.hidden = false;
    } else {
      el.oaVisualContainer.hidden = true;
    }
  }

  function downloadInlineSvgFigure(svgEl, filename, fmt = "svg") {
    if (!svgEl) return;
    const clone = svgEl.cloneNode(true);
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    const computedColor = getComputedStyle(svgEl).color || "#0f172a";
    clone.style.color = computedColor;
    const serialized = new XMLSerializer().serializeToString(clone).replace(/currentColor/g, computedColor);
    if (fmt === "svg") {
      const blob = new Blob([serialized], { type: "image/svg+xml;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      return;
    }
    const vb = (svgEl.getAttribute("viewBox") || "0 0 580 220").split(/\s+/).map(Number);
    const w = vb[2] || 580;
    const h = vb[3] || 220;
    const scale = 3;
    const img = new Image();
    const svgBlob = new Blob([serialized], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(svgBlob);
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = w * scale;
      canvas.height = h * scale;
      const ctx = canvas.getContext("2d");
      const bg = getComputedStyle(document.documentElement).getPropertyValue("--bg-surface").trim() || "#ffffff";
      ctx.fillStyle = bg.startsWith("light-dark") ? "#ffffff" : bg;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.scale(scale, scale);
      ctx.drawImage(img, 0, 0, w, h);
      URL.revokeObjectURL(url);
      canvas.toBlob((pngBlob) => {
        if (!pngBlob) return;
        const pUrl = URL.createObjectURL(pngBlob);
        const a = document.createElement("a");
        a.href = pUrl;
        a.download = filename;
        a.click();
        setTimeout(() => URL.revokeObjectURL(pUrl), 1000);
      }, "image/png");
    };
    img.src = url;
  }

  function applyAndRunOaPreset(action, target, loc = "", flank = 0) {
    el.oaActionSelect.value = action;
    el.oaTargetInput.value = target;
    el.oaLocInput.value = loc;
    el.oaFlankInput.value = String(flank || 0);
    runLiveNiagadsQuery();
  }

  async function runLiveNiagadsQuery() {
    const action = el.oaActionSelect.value;
    let target = el.oaTargetInput.value.trim();
    const loc = el.oaLocInput.value.trim();
    const flank = Number(el.oaFlankInput.value || 0);
    if (!target && action === "literature_credits") {
      target = "all";
      el.oaTargetInput.value = "all";
    }
    if (!target && action === "adsp_r5_power_dar") {
      target = "ABCA7";
      el.oaTargetInput.value = "ABCA7";
    }
    if (!target && !loc) return;

    el.oaSubmitBtn.disabled = true;
    el.oaSubmitBtn.textContent = "Querying api.niagads.org…";
    el.oaResultCard.hidden = false;
    if (el.oaEcosystemLinks) el.oaEcosystemLinks.hidden = true;
    if (el.oaPaperCredits) el.oaPaperCredits.hidden = true;
    if (el.oaVisualContainer) el.oaVisualContainer.hidden = true;
    el.oaResultMeta.innerHTML = `<span class="spinner" aria-hidden="true"></span><span>Fetching live NIAGADS Open Access v2.0 record…</span>`;
    el.oaResultMarkdown.innerHTML = `<p style="color:var(--text-muted)">Contacting <code>https://api.niagads.org/api</code>…</p>`;

    const qs = new URLSearchParams({
      action,
      target,
      loc,
      flank: String(flank),
    });

    try {
      const res = await apiFetch(`/api/niagads/live?${qs.toString()}`);
      state.lastOaResult = { action, target, loc, flank, ...res };
      const reqBadge = res.request_id ? ` · request_id: <code>${escapeHtml(res.request_id)}</code>` : "";
      el.oaResultMeta.innerHTML = `
        <span class="oa-status-pill">✓ HTTP 200 OK · ${escapeHtml(res.elapsed_ms)} ms</span>
        <span>Endpoint: <code>${escapeHtml(res.endpoint)}</code>${reqBadge}</span>
      `;
      renderOaEcosystemAndVisuals(res);
      el.oaResultMarkdown.innerHTML = renderMarkdown(res.summary_markdown || "");
      el.oaResultJson.textContent = JSON.stringify(res.raw, null, 2);
      state.usageData = null;
    } catch (err) {
      if (el.oaEcosystemLinks) el.oaEcosystemLinks.hidden = true;
      if (el.oaPaperCredits) el.oaPaperCredits.hidden = true;
      if (el.oaVisualContainer) el.oaVisualContainer.hidden = true;
      el.oaResultMeta.innerHTML = `<span class="oa-status-pill staged" style="color:var(--danger)">✗ Query Error</span>`;
      el.oaResultMarkdown.innerHTML = `<p style="color:var(--danger)">${escapeHtml(err.message)}</p>`;
      el.oaResultJson.textContent = "";
    } finally {
      el.oaSubmitBtn.disabled = false;
      el.oaSubmitBtn.textContent = "⚡ Execute Live API Query ↵";
    }
  }

  el.oaForm.addEventListener("submit", (ev) => {
    ev.preventDefault();
    runLiveNiagadsQuery();
  });

  el.oaCiteBtn?.addEventListener("click", () => {
    const r = state.lastOaResult;
    const ids = r?.target ? [r.target] : [];
    copyNiagadsCitation(`NIAGADS Open Access v2.0 (${r?.action || "live"})`, ids);
  });

  el.oaCopyJsonBtn.addEventListener("click", async () => {
    if (!state.lastOaResult?.raw) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(state.lastOaResult.raw, null, 2));
      el.oaCopyJsonBtn.textContent = "✓ Copied JSON";
      setTimeout(() => {
        el.oaCopyJsonBtn.textContent = "📋 Copy Raw JSON";
      }, 1500);
    } catch {}
  });

  function triggerNiagadsTrackDownload(trackFormat) {
    const r = state.lastOaResult;
    if (!r) return;
    const qs = new URLSearchParams({
      action: r.action || "finemap_coloc",
      target: r.target || "BIN1",
      loc: r.loc || "",
      track_format: trackFormat,
    });
    const a = document.createElement("a");
    a.href = `/api/niagads/export-track?${qs.toString()}`;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    a.remove();
    showToast(
      trackFormat === "bedgraph"
        ? "✓ Downloading GRCh38 IGV.js .bedGraph track for NIAGADS Genome Browser"
        : "✓ Downloading GRCh38 LocusZoom .tsv regional track"
    );
  }

  document.getElementById("oa-export-bedgraph-btn")?.addEventListener("click", () => {
    triggerNiagadsTrackDownload("bedgraph");
  });

  document.getElementById("oa-export-lz-btn")?.addEventListener("click", () => {
    triggerNiagadsTrackDownload("locuszoom");
  });

  el.oaSendStudioBtn.addEventListener("click", () => {
    const r = state.lastOaResult;
    if (!r) return;
    const locNote = r.loc ? ` (locus \`${r.loc}\`)` : "";
    const synthPrompt =
      `Analyze the live NIAGADS Open Access API v2.0 result for \`${r.target}\`${locNote} ` +
      `(action=\`${r.action}\`), cross-reference it with Ligase's curated NIAGADS functional genomics / multi-ancestry ` +
      `panels (\`query_niagads\`) and UniProt/Ensembl annotations where relevant, and provide a quantitative biomedical interpretation.`;
    launchPromptInStudio(synthPrompt, "niagads_api");
  });

  // ── Research Studio Rendering Helpers ─────────────────────────────────────
  function setProfile(profile) {
    state.profile = profile === "a1" ? "a1" : "ad1";
    el.profileAd1Btn.classList.toggle("active", state.profile === "ad1");
    el.profileA1Btn.classList.toggle("active", state.profile === "a1");

    if (state.profile === "ad1") {
      el.heroEyebrow.textContent = "ALZHEIMER'S GENOMICS · NIAGADS OPEN ACCESS v2.0 · MULTI-OMICS CO-SCIENTIST";
      el.heroTitle.textContent = "Grounded Quantitative Discovery with Ligase";
    } else {
      el.heroEyebrow.textContent = "GENOMICS · PHARMACOLOGY · STRUCTURAL & MOLECULAR BIOLOGY";
      el.heroTitle.textContent = "General-Purpose Biomedical Research with Ligase";
    }
  }

  function syncWorkflowHint() {
    if (state.mode === "plan") {
      el.workflowHint.textContent =
        "Plan-then-Approve · review & edit numbered methodology before tools execute";
    } else if (state.speedMode === "critic") {
      el.workflowHint.textContent =
        "🏛️ NIAGADS Critic · quantitative synthesis + LD hitchhiking, sample-overlap & multi-ancestry audit";
    } else if (state.speedMode === "deep") {
      el.workflowHint.textContent =
        "🔬 Deep exploration · multi-round reasoning + full Biomni & NIAGADS tool suite";
    } else {
      el.workflowHint.textContent =
        "⚡ Fast execution · parallel <350 ms pre-grounding + single-pass synthesis & report";
    }
  }

  function setSpeedMode(speed) {
    state.speedMode = speed === "deep" || speed === "critic" ? speed : "fast";
    el.speedFastBtn.classList.toggle("active", state.speedMode === "fast");
    el.speedDeepBtn.classList.toggle("active", state.speedMode === "deep");
    el.speedCriticBtn?.classList.toggle("active", state.speedMode === "critic");
    syncWorkflowHint();
  }

  function setMode(mode) {
    state.mode = mode === "plan" ? "plan" : "direct";
    el.modeDirectBtn.classList.toggle("active", state.mode === "direct");
    el.modePlanBtn.classList.toggle("active", state.mode === "plan");
    syncWorkflowHint();
    el.sendBtn.textContent = state.mode === "plan" ? "Propose Plan ↵" : "Run Study ↵";
  }

  function showWelcomeOrTranscript(showTranscript) {
    el.welcomeView.hidden = showTranscript;
    el.transcript.hidden = !showTranscript;
  }

  function scrollCanvasToBottom() {
    el.canvas.scrollTop = el.canvas.scrollHeight;
  }

  el.starterGrid.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".starter-card[data-starter-id]");
    if (!btn) return;
    const starterId = btn.dataset.starterId;
    const s = (state.meta?.starters || []).find((item) => item.id === starterId);
    if (!s) return;
    setProfile(s.profile || "ad1");
    el.chatInput.value = s.question;
    el.chatInput.focus();
    handleSubmitPrompt(s.question);
  });

  function renderStarters() {
    const starters = state.meta?.starters || [];
    // Reuse server-side rendered starter cards when already hydrated in HTML
    if (el.starterGrid.querySelectorAll(".starter-card[data-starter-id]").length === starters.length && starters.length > 0) {
      return;
    }
    el.starterGrid.innerHTML = "";
    for (const s of starters) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "starter-card";
      btn.dataset.starterId = s.id;
      btn.innerHTML = `
        <span class="starter-badge">${escapeHtml(s.badge)}</span>
        <div class="starter-title">${escapeHtml(s.title)}</div>
        <div class="starter-sub">${escapeHtml(s.subtitle)}</div>
      `;
      el.starterGrid.appendChild(btn);
    }
  }

  function renderCatalogDialog() {
    const tools = state.meta?.tools || [];
    el.toolsCatalogList.innerHTML = tools
      .map(
        (t) => `
        <div class="catalog-item">
          <div class="catalog-item-head">
            <span class="catalog-item-id">${escapeHtml(t.name)}</span>
            <span class="catalog-item-tag">${escapeHtml(t.category)}</span>
          </div>
          <div class="catalog-item-desc">${escapeHtml(t.description)}</div>
        </div>
      `
      )
      .join("");

    const datasets = state.meta?.niagads?.datasets || [];
    el.niagadsCatalogList.innerHTML = datasets
      .map(
        (d) => `
        <div class="catalog-item">
          <div class="catalog-item-head">
            <span class="catalog-item-id">${escapeHtml(d.id)}</span>
            <span class="catalog-item-tag">${escapeHtml(d.file_count ? `${d.file_count} files` : d.access)}</span>
          </div>
          <div class="catalog-item-desc"><strong>${escapeHtml(d.title)}</strong> — ${escapeHtml(d.description)}</div>
        </div>
      `
      )
      .join("");
  }

  function renderThreads() {
    el.threadList.innerHTML = "";
    if (!state.threads.length) {
      const empty = document.createElement("div");
      empty.className = "setting-desc";
      empty.style.padding = "0.55rem 0.6rem";
      empty.textContent = "No saved studies yet.";
      el.threadList.appendChild(empty);
      return;
    }

    for (const t of state.threads) {
      const row = document.createElement("div");
      row.className = "thread-item" + (t.id === state.activeThreadId ? " active" : "");

      const openBtn = document.createElement("button");
      openBtn.type = "button";
      openBtn.className = "thread-item-title";
      openBtn.style.border = "none";
      openBtn.style.background = "transparent";
      openBtn.style.color = "inherit";
      openBtn.style.font = "inherit";
      openBtn.style.textAlign = "start";
      openBtn.style.cursor = "pointer";
      openBtn.style.padding = "0";
      openBtn.textContent = t.title;
      openBtn.addEventListener("click", () => {
        switchPortalTab("studio");
        openThread(t.id);
      });

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "thread-del-btn";
      delBtn.setAttribute("aria-label", `Delete study ${t.title}`);
      delBtn.textContent = "✕";
      delBtn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        await apiFetch(`/api/threads/${encodeURIComponent(t.id)}`, { method: "DELETE" });
        if (state.activeThreadId === t.id) {
          startFreshStudy();
        }
        await refreshThreads();
      });

      row.append(openBtn, delBtn);
      el.threadList.appendChild(row);
    }
  }

  async function refreshThreads() {
    try {
      const data = await apiFetch("/api/threads", { priority: "low" });
      state.threads = data.threads || [];
      renderThreads();
    } catch {}
  }

  function startFreshStudy() {
    switchPortalTab("studio");
    state.activeThreadId = null;
    el.transcript.innerHTML = "";
    showWelcomeOrTranscript(false);
    renderThreads();
    el.sidebar.classList.remove("open");
  }

  async function openThread(threadId) {
    try {
      const data = await apiFetch(`/api/threads/${encodeURIComponent(threadId)}`);
      const thread = data.thread;
      state.activeThreadId = thread.id;
      setProfile(thread.profile || "ad1");
      el.transcript.innerHTML = "";
      showWelcomeOrTranscript(true);

      for (const m of thread.messages || []) {
        if (m.role === "user") {
          appendUserBubble(m.content, m.metadata?.attachments || []);
        } else if (m.role === "assistant") {
          appendCompletedAssistantCard(m.content, m.metadata || {});
        }
      }
      renderThreads();
      scrollCanvasToBottom();
      el.sidebar.classList.remove("open");
    } catch (err) {
      alert(`Could not load study: ${err.message}`);
    }
  }

  function appendUserBubble(content, attachmentNames = []) {
    const div = document.createElement("div");
    div.className = "msg-user";
    div.textContent = content;
    if (attachmentNames.length) {
      const attWrap = document.createElement("div");
      attWrap.className = "msg-attachments";
      for (const name of attachmentNames) {
        const pill = document.createElement("span");
        pill.className = "att-pill";
        pill.textContent = `📎 ${name}`;
        attWrap.appendChild(pill);
      }
      div.appendChild(attWrap);
    }
    el.transcript.appendChild(div);
  }

  function buildToolTraceElement(toolTrace) {
    const wrap = document.createElement("div");
    wrap.className = "tool-trace-list";
    for (const t of toolTrace || []) {
      const details = document.createElement("details");
      details.className = "tool-step";
      const okMark = t.success === false ? "✗" : "✓";
      details.innerHTML = `
        <summary>
          <span class="tool-step-left">
            <span>${okMark}</span>
            <span class="tool-name-chip">${escapeHtml(t.tool_name || "tool")}</span>
            <span class="tool-args-inline">${escapeHtml(t.args_preview || "")}</span>
          </span>
          <span class="tool-meta-right">${escapeHtml(t.elapsed_ms ? `${t.elapsed_ms} ms` : "done")}</span>
        </summary>
        <div class="tool-step-body">${escapeHtml(t.output_preview || t.args_preview || "Completed.")}</div>
      `;
      wrap.appendChild(details);
    }
    return wrap;
  }

  const CANONICAL_AD_GENES = [
    "APOE",
    "BIN1",
    "TREM2",
    "ABCA7",
    "SORL1",
    "PLCG2",
    "ABI3",
    "MAPT",
    "CLU",
    "CR1",
    "PICALM",
    "SPI1",
    "CD33",
    "MS4A6A",
    "RELN",
    "ADAM10",
  ];

  function extractGroundedProvenance(markdownText, meta = {}) {
    const traceStr = (meta.tool_trace || [])
      .map((t) => `${t.tool_name || ""} ${t.args_preview || ""} ${t.output_preview || ""}`)
      .join(" ");
    const hay = `${markdownText || ""} ${traceStr}`;
    const ngs = Array.from(new Set((hay.match(/\bNG00\d{3}\b/gi) || []).map((x) => x.toUpperCase()))).slice(0, 6);
    const rsids = Array.from(new Set((hay.match(/\brs\d{3,12}\b/gi) || []).map((x) => x.toLowerCase()))).slice(0, 6);
    const genes = CANONICAL_AD_GENES.filter((g) => new RegExp(`\\b${g}\\b`).test(hay)).slice(0, 6);
    return { ngs, rsids, genes, all: [...ngs, ...genes, ...rsids] };
  }

  function buildProvenanceStrip(markdownText, meta = {}) {
    const prov = extractGroundedProvenance(markdownText, meta);
    if (!prov.all.length) return null;

    const strip = document.createElement("div");
    strip.className = "provenance-strip";

    const lbl = document.createElement("span");
    lbl.className = "prov-label";
    lbl.textContent = "Grounded NIAGADS Entities:";
    strip.appendChild(lbl);

    for (const ng of prov.ngs) {
      const a = document.createElement("a");
      a.className = "prov-pill";
      a.href = `https://dss.niagads.org/datasets/${ng.toLowerCase()}/`;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.title = `Open NIAGADS DSS Study ${ng}`;
      a.textContent = `🏛️ ${ng}`;
      strip.appendChild(a);
    }

    for (const g of prov.genes) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "prov-pill";
      btn.title = `Inspect ${g} V2F Locus Dossier in NIAGADS Explorer`;
      btn.textContent = `🧬 ${g}`;
      btn.addEventListener("click", async () => {
        await switchPortalTab("niagads-api", { focusHeading: true });
        applyAndRunOaPreset("locus_dossier", g, "", 10000);
      });
      strip.appendChild(btn);
    }

    for (const rs of prov.rsids) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "prov-pill";
      btn.title = `Inspect ${rs} V2F Variant Dossier in NIAGADS Explorer`;
      btn.textContent = `🧪 ${rs}`;
      btn.addEventListener("click", async () => {
        await switchPortalTab("niagads-api", { focusHeading: true });
        applyAndRunOaPreset("locus_dossier", rs, "", 0);
      });
      strip.appendChild(btn);
    }

    return strip;
  }

  function buildArtifactBar(markdownText, meta = {}) {
    const bar = document.createElement("div");
    bar.className = "artifact-bar";

    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "artifact-btn";
    copyBtn.textContent = "📋 Copy Markdown";
    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(markdownText);
        copyBtn.textContent = "✓ Copied";
        setTimeout(() => {
          copyBtn.textContent = "📋 Copy Markdown";
        }, 1600);
      } catch {}
    });
    bar.appendChild(copyBtn);

    const prov = extractGroundedProvenance(markdownText, meta);
    const citeBtn = document.createElement("button");
    citeBtn.type = "button";
    citeBtn.className = "artifact-btn";
    citeBtn.textContent = "📜 Cite NIAGADS";
    citeBtn.title = "Copy NIH/NIA U24AG041689 acknowledgment & BibTeX";
    citeBtn.addEventListener("click", () => {
      copyNiagadsCitation(meta.run_id || "Ligase Biomedical Study", prov.all);
    });
    bar.appendChild(citeBtn);

    if (meta.report_url) {
      const repLink = document.createElement("a");
      repLink.className = "artifact-btn";
      repLink.href = meta.report_url;
      repLink.download = "";
      repLink.textContent = "⬇ Download report.md";
      bar.appendChild(repLink);
    }

    const nbHref = meta.notebook_url || (meta.run_id ? `/api/runs/${encodeURIComponent(meta.run_id)}/notebook.ipynb?client_id=${encodeURIComponent(CLIENT_ID)}` : "");
    if (nbHref) {
      const nbLink = document.createElement("a");
      nbLink.className = "artifact-btn";
      nbLink.href = nbHref;
      nbLink.download = "";
      nbLink.title = "Download reproducible Python 3 Jupyter Notebook (.ipynb) querying live NIAGADS Open Access v2.0";
      nbLink.textContent = "📓 Export .ipynb";
      bar.appendChild(nbLink);
    }

    if (meta.run_id || meta.share_url) {
      const shareBtn = document.createElement("button");
      shareBtn.type = "button";
      shareBtn.className = "artifact-btn";
      shareBtn.textContent = "🔗 Share Study Link";
      shareBtn.title = "Copy read-only NIAGADS study permalink";
      shareBtn.addEventListener("click", async () => {
        const rel = meta.share_url || `/?study=${encodeURIComponent(meta.run_id)}`;
        const fullUrl = new URL(rel, window.location.origin).toString();
        try {
          await navigator.clipboard.writeText(fullUrl);
          showToast("✓ Copied shareable NIAGADS study permalink");
        } catch {
          showToast(fullUrl);
        }
      });
      bar.appendChild(shareBtn);
    }

    if (meta.bundle_url) {
      const zipLink = document.createElement("a");
      zipLink.className = "artifact-btn";
      zipLink.href = meta.bundle_url;
      zipLink.download = "";
      zipLink.textContent = "📦 Download Run .zip";
      bar.appendChild(zipLink);
    }

    return bar;
  }

  function appendCompletedAssistantCard(markdownText, meta = {}) {
    const card = document.createElement("article");
    card.className = "msg-assistant";

    const modelName = meta.model || state.meta?.model || "gpt-6-luna";
    const statsParts = [];
    if (meta.elapsed_s) statsParts.push(`${meta.elapsed_s}s`);
    if (meta.iterations) statsParts.push(`${meta.iterations} round${meta.iterations === 1 ? "" : "s"}`);
    if (meta.tool_trace?.length)
      statsParts.push(`${meta.tool_trace.length} tool call${meta.tool_trace.length === 1 ? "" : "s"}`);

    const head = document.createElement("div");
    head.className = "assistant-head";
    head.innerHTML = `
      <span class="assistant-badge">🧬 Ligase · ${escapeHtml(modelName)}</span>
      <span>${escapeHtml(statsParts.join(" · "))}</span>
    `;
    card.appendChild(head);

    if (meta.tool_trace?.length) {
      card.appendChild(buildToolTraceElement(meta.tool_trace));
    }

    const body = document.createElement("div");
    body.className = "md-body";
    body.innerHTML = renderMarkdown(markdownText);
    card.appendChild(body);

    if (meta.figures?.length) {
      const gal = document.createElement("div");
      gal.className = "figure-gallery";
      for (const f of meta.figures) {
        const img = document.createElement("img");
        img.src = f.url;
        img.alt = f.name || "Generated study figure";
        img.loading = "lazy";
        gal.appendChild(img);
      }
      card.appendChild(gal);
    }

    const provStrip = buildProvenanceStrip(markdownText, meta);
    if (provStrip) card.appendChild(provStrip);
    card.appendChild(buildArtifactBar(markdownText, meta));
    el.transcript.appendChild(card);
  }

  // ── Uploads ───────────────────────────────────────────────────────────────
  function renderPendingUploads() {
    if (!state.pendingUploads.length) {
      el.attachmentStrip.hidden = true;
      el.attachmentStrip.innerHTML = "";
      return;
    }
    el.attachmentStrip.hidden = false;
    el.attachmentStrip.innerHTML = "";
    state.pendingUploads.forEach((u, idx) => {
      const chip = document.createElement("span");
      chip.className = "pending-file-chip";
      chip.innerHTML = `📎 ${escapeHtml(u.name)} <small>(${Math.max(1, Math.round(u.size_bytes / 1024))} KB)</small>`;
      const rm = document.createElement("button");
      rm.type = "button";
      rm.setAttribute("aria-label", `Remove ${u.name}`);
      rm.textContent = "✕";
      rm.addEventListener("click", () => {
        state.pendingUploads.splice(idx, 1);
        renderPendingUploads();
      });
      chip.appendChild(rm);
      el.attachmentStrip.appendChild(chip);
    });
  }

  el.attachFileBtn.addEventListener("click", () => el.fileUploadInput.click());
  el.fileUploadInput.addEventListener("change", async () => {
    const files = Array.from(el.fileUploadInput.files || []);
    el.fileUploadInput.value = "";
    for (const file of files) {
      try {
        const buf = await file.arrayBuffer();
        const res = await apiFetch("/api/uploads", {
          method: "POST",
          headers: {
            "Content-Type": "application/octet-stream",
            "X-Upload-Filename": file.name,
          },
          body: buf,
        });
        state.pendingUploads.push(res);
        renderPendingUploads();
      } catch (err) {
        alert(`Upload failed for ${file.name}: ${err.message}`);
      }
    }
  });

  // ── Busy State Control ────────────────────────────────────────────────────
  function setRunningState(running) {
    el.sendBtn.disabled = running;
    el.stopRunBtn.hidden = !running;
  }

  el.stopRunBtn.addEventListener("click", async () => {
    if (state.activeRunId) {
      try {
        await apiFetch(`/api/runs/${encodeURIComponent(state.activeRunId)}/cancel`, { method: "POST" });
      } catch {}
    }
    if (state.abortController) {
      state.abortController.abort();
    }
  });

  // ── Plan-then-Approve Flow ────────────────────────────────────────────────
  async function runPlanFlow(prompt, attachments) {
    showWelcomeOrTranscript(true);
    appendUserBubble(prompt, attachments.map((a) => a.name));
    scrollCanvasToBottom();

    const planCard = document.createElement("div");
    planCard.className = "plan-card";
    planCard.innerHTML = `<div class="plan-card-header">📋 Generating Scientific Plan (${escapeHtml(state.meta?.model || "gpt-6-luna")})…</div><div class="md-body"><p>Triaging question and matching NIAGADS Open Access v2.0 / biomedical tools…</p></div>`;
    el.transcript.appendChild(planCard);
    scrollCanvasToBottom();

    setRunningState(true);
    try {
      const res = await apiFetch("/api/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          thread_id: state.activeThreadId,
          prompt,
          profile: state.profile,
        }),
      });
      setRunningState(false);

      if (!res.needs_plan && res.direct_answer) {
        planCard.remove();
        if (res.thread_id) state.activeThreadId = res.thread_id;
        appendCompletedAssistantCard(res.direct_answer, { model: state.meta?.model || "gpt-6-luna" });
        await refreshThreads();
        scrollCanvasToBottom();
        return;
      }

      renderInteractivePlanCard(planCard, prompt, attachments, res.plan_markdown);
    } catch (err) {
      setRunningState(false);
      planCard.innerHTML = `<div class="plan-card-header" style="color:var(--danger)">Plan Failed</div><p>${escapeHtml(err.message)}</p>`;
    }
  }

  function renderInteractivePlanCard(planCard, prompt, attachments, planMarkdown) {
    planCard.innerHTML = `
      <div class="plan-card-header">📋 Proposed Scientific Plan · Awaiting Researcher Approval</div>
      <div class="md-body">${renderMarkdown(planMarkdown)}</div>
      <div class="plan-actions">
        <button type="button" class="plan-approve-btn" data-action="approve">✅ Approve &amp; Execute</button>
        <button type="button" class="plan-secondary-btn" data-action="revise">✏️ Revise Plan</button>
        <button type="button" class="plan-secondary-btn" data-action="cancel">🚫 Cancel</button>
      </div>
      <div class="plan-revise-box" hidden>
        <input type="text" placeholder="Describe how to revise the plan (e.g., also query live NIAGADS exon structure)…" aria-label="Plan revision instructions">
        <button type="button" class="plan-approve-btn" data-action="submit-revise">Update</button>
      </div>
    `;
    scrollCanvasToBottom();

    const approveBtn = planCard.querySelector('[data-action="approve"]');
    const reviseBtn = planCard.querySelector('[data-action="revise"]');
    const cancelBtn = planCard.querySelector('[data-action="cancel"]');
    const reviseBox = planCard.querySelector(".plan-revise-box");
    const reviseInput = reviseBox.querySelector("input");
    const submitReviseBtn = planCard.querySelector('[data-action="submit-revise"]');

    approveBtn.addEventListener("click", () => {
      planCard.querySelector(".plan-actions").remove();
      reviseBox.remove();
      planCard.querySelector(".plan-card-header").textContent = "✅ Approved Scientific Plan";
      streamExecution(prompt, attachments, planMarkdown, true);
    });

    reviseBtn.addEventListener("click", () => {
      reviseBox.hidden = !reviseBox.hidden;
      if (!reviseBox.hidden) reviseInput.focus();
    });

    submitReviseBtn.addEventListener("click", async () => {
      const note = reviseInput.value.trim();
      if (!note) return;
      submitReviseBtn.disabled = true;
      submitReviseBtn.textContent = "Updating…";
      try {
        const updated = await apiFetch("/api/plan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            thread_id: state.activeThreadId,
            prompt,
            profile: state.profile,
            revision_note: note,
          }),
        });
        renderInteractivePlanCard(planCard, prompt, attachments, updated.plan_markdown);
      } catch (err) {
        alert(`Revision failed: ${err.message}`);
        submitReviseBtn.disabled = false;
        submitReviseBtn.textContent = "Update";
      }
    });

    cancelBtn.addEventListener("click", () => {
      planCard.innerHTML = `<div class="plan-card-header">🚫 Execution Cancelled</div><p class="setting-desc">Nothing was executed.</p>`;
    });
  }

  // ── Live SSE Agent Execution ──────────────────────────────────────────────
  async function streamExecution(prompt, attachments, approvedPlan = null, skipUserBubble = false) {
    showWelcomeOrTranscript(true);
    if (!skipUserBubble) {
      appendUserBubble(prompt, attachments.map((a) => a.name));
    }

    const card = document.createElement("article");
    card.className = "msg-assistant";

    const head = document.createElement("div");
    head.className = "assistant-head";
    const statusRight = document.createElement("span");
    statusRight.textContent = "Starting engine…";
    head.innerHTML = `<span class="assistant-badge">🧬 Ligase · ${escapeHtml(state.meta?.model || "gpt-6-luna")}</span>`;
    head.appendChild(statusRight);

    const traceList = document.createElement("div");
    traceList.className = "tool-trace-list";

    const mdContainer = document.createElement("div");
    mdContainer.className = "md-body";
    mdContainer.innerHTML = `<p style="color:var(--text-muted)">Reasoning &amp; grounding with live NIAGADS Open Access v2.0 + biomedical tools…</p>`;

    const figureGallery = document.createElement("div");
    figureGallery.className = "figure-gallery";
    figureGallery.hidden = true;

    card.append(head, traceList, mdContainer, figureGallery);
    el.transcript.appendChild(card);
    scrollCanvasToBottom();

    const stepElements = new Map();
    let streamedMarkdown = "";
    let renderScheduled = false;

    function scheduleMarkdownRender() {
      if (renderScheduled) return;
      renderScheduled = true;
      requestAnimationFrame(() => {
        renderScheduled = false;
        if (streamedMarkdown) {
          mdContainer.innerHTML = renderMarkdown(streamedMarkdown);
          scrollCanvasToBottom();
        }
      });
    }

    const abortController = new AbortController();
    state.abortController = abortController;
    setRunningState(true);

    const startedClock = performance.now();
    const timerId = setInterval(() => {
      const secs = ((performance.now() - startedClock) / 1000).toFixed(1);
      statusRight.textContent = `Running · ${secs}s`;
    }, 250);

    try {
      const resp = await fetch("/api/chat/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Ligase-Client-Id": CLIENT_ID,
        },
        body: JSON.stringify({
          thread_id: state.activeThreadId,
          prompt,
          profile: state.profile,
          speed_mode: state.speedMode,
          max_iterations: state.maxIterations,
          attachments: attachments.map((a) => a.token),
          approved_plan: approvedPlan,
        }),
        signal: abortController.signal,
      });

      if (!resp.ok || !resp.body) {
        let msg = `HTTP ${resp.status}`;
        try {
          const err = await resp.json();
          msg = err.detail || msg;
        } catch {}
        throw new Error(msg);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let boundary;
        while ((boundary = buffer.indexOf("\n\n")) !== -1) {
          const rawEvent = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          if (!rawEvent.trim() || rawEvent.startsWith(":")) continue;

          let eventName = "message";
          const dataLines = [];
          for (const line of rawEvent.split("\n")) {
            if (line.startsWith("event:")) {
              eventName = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
              dataLines.push(line.slice(5).trim());
            }
          }
          if (!dataLines.length) continue;

          let payload;
          try {
            payload = JSON.parse(dataLines.join("\n"));
          } catch {
            continue;
          }

          if (eventName === "run_started") {
            state.activeRunId = payload.run_id;
            state.activeThreadId = payload.thread_id;
            refreshThreads();
          } else if (eventName === "tool_started") {
            const details = document.createElement("details");
            details.className = "tool-step";
            details.innerHTML = `
              <summary>
                <span class="tool-step-left">
                  <span class="spinner" aria-hidden="true"></span>
                  <span class="tool-name-chip">${escapeHtml(payload.tool_name)}</span>
                  <span class="tool-args-inline">${escapeHtml(payload.args_preview || "")}</span>
                </span>
                <span class="tool-meta-right">running…</span>
              </summary>
              <div class="tool-step-body">Arguments: ${escapeHtml(payload.args_preview || "{}")}</div>
            `;
            traceList.appendChild(details);
            stepElements.set(payload.call_id || payload.tool_name, details);
            scrollCanvasToBottom();
          } else if (eventName === "tool_result") {
            const details =
              stepElements.get(payload.call_id) ||
              stepElements.get(payload.tool_name) ||
              traceList.lastElementChild;
            if (details) {
              const spinnerEl = details.querySelector(".spinner");
              if (spinnerEl) {
                const mark = document.createElement("span");
                mark.textContent = payload.success === false ? "✗" : "✓";
                spinnerEl.replaceWith(mark);
              }
              const metaRight = details.querySelector(".tool-meta-right");
              if (metaRight) metaRight.textContent = `${payload.elapsed_ms || 1} ms`;
              const bodyEl = details.querySelector(".tool-step-body");
              if (bodyEl) bodyEl.textContent = payload.output_preview || "Completed.";
            }
          } else if (eventName === "assistant_delta") {
            streamedMarkdown += payload.delta || "";
            scheduleMarkdownRender();
          } else if (eventName === "figure") {
            figureGallery.hidden = false;
            const img = document.createElement("img");
            img.src = payload.url;
            img.alt = payload.name || "Study plot";
            figureGallery.appendChild(img);
          } else if (eventName === "run_complete") {
            clearInterval(timerId);
            const finalMd = payload.content || streamedMarkdown;
            mdContainer.innerHTML = renderMarkdown(finalMd);
            const toolCount = (payload.tool_trace || []).length;
            const ttftBadge = payload.ttft_ms ? ` · TTFT ${payload.ttft_ms} ms` : "";
            statusRight.textContent = `${payload.elapsed_s}s${ttftBadge} · ${payload.iterations} round${payload.iterations === 1 ? "" : "s"} · ${toolCount} tool call${toolCount === 1 ? "" : "s"}`;
            const provStrip = buildProvenanceStrip(finalMd, payload);
            if (provStrip) card.appendChild(provStrip);
            card.appendChild(buildArtifactBar(finalMd, payload));
            state.usageData = null;
            await refreshThreads();
            scrollCanvasToBottom();
          } else if (eventName === "run_cancelled") {
            clearInterval(timerId);
            statusRight.textContent = `Stopped (${payload.elapsed_s}s)`;
            if (!streamedMarkdown) {
              mdContainer.innerHTML = `<p style="color:var(--text-muted)">Run stopped by researcher.</p>`;
            }
          } else if (eventName === "run_error") {
            clearInterval(timerId);
            statusRight.textContent = "Failed";
            mdContainer.innerHTML = `<p style="color:var(--danger)"><strong>Run error:</strong> ${escapeHtml(payload.message)}</p>`;
          }
        }
      }
    } catch (err) {
      clearInterval(timerId);
      if (err.name === "AbortError") {
        statusRight.textContent = "Stopped";
        if (!streamedMarkdown) {
          mdContainer.innerHTML = `<p style="color:var(--text-muted)">Run stopped by researcher.</p>`;
        }
      } else {
        statusRight.textContent = "Error";
        mdContainer.innerHTML = `<p style="color:var(--danger)"><strong>Connection error:</strong> ${escapeHtml(err.message)}</p>`;
      }
    } finally {
      clearInterval(timerId);
      state.activeRunId = null;
      state.abortController = null;
      setRunningState(false);
    }
  }

  async function handleSubmitPrompt(rawPrompt) {
    const prompt = String(rawPrompt ?? el.chatInput.value).trim();
    if (!prompt || state.abortController) return;

    const attachments = [...state.pendingUploads];
    state.pendingUploads = [];
    renderPendingUploads();
    el.chatInput.value = "";

    if (state.mode === "plan") {
      await runPlanFlow(prompt, attachments);
    } else {
      await streamExecution(prompt, attachments);
    }
  }

  // ── IME-Safe Enter-to-Submit on <textarea> (ime-safe-enter-submit) ────────
  let lastCompositionEndAt = null;
  el.chatInput.addEventListener("compositionend", (ev) => {
    lastCompositionEndAt = ev.timeStamp;
  });

  el.chatInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (event.isComposing || event.keyCode === 229) {
        return;
      }
      if (lastCompositionEndAt !== null && Math.abs(event.timeStamp - lastCompositionEndAt) < 50) {
        return;
      }
      el.composerForm.requestSubmit();
    }
  });

  el.composerForm.addEventListener("submit", (event) => {
    event.preventDefault();
    handleSubmitPrompt(el.chatInput.value);
  });

  // ── Usage & Volume Executive Ledger (PPTX-Style Telemetry Dashboard) ──────
  const numFmt = new Intl.NumberFormat("en-US");
  const compactFmt = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
  const TOOL_COLORS = ["#0f766e", "#3b82f6", "#8b5cf6", "#d97706", "#ec4899", "#10b981", "#6366f1"];
  const DOMAIN_COLORS = {
    niagads_open_access: "#0f766e",
    niagads_v2f: "#4f46e5",
    adsp_ancestry: "#0284c7",
    psp_tauopathy: "#d97706",
    neuro_proteomics: "#7c3aed",
    pharmacology: "#059669",
    bioinformatics: "#e11d48",
  };

  function fmtUsd(val) {
    const n = Number(val || 0);
    if (n === 0) return "$0.0000";
    if (n < 0.01) return `$${n.toFixed(4)}`;
    return `$${n.toFixed(2)}`;
  }

  function fmtBytes(bytes) {
    const b = Number(bytes || 0);
    if (b >= 1024 * 1024) return `${(b / (1024 * 1024)).toFixed(2)} MB`;
    if (b >= 1024) return `${(b / 1024).toFixed(1)} KB`;
    return `${b} B`;
  }

  function showUsageTip(ev, htmlContent) {
    if (!el.usageTooltip) return;
    el.usageTooltip.innerHTML = htmlContent;
    el.usageTooltip.hidden = false;
    moveUsageTip(ev);
  }

  function moveUsageTip(ev) {
    if (!el.usageTooltip || el.usageTooltip.hidden) return;
    const x = Math.min(window.innerWidth - 160, Math.max(160, ev.clientX));
    const y = Math.max(56, ev.clientY);
    el.usageTooltip.style.setProperty("--tip-x", `${x}px`);
    el.usageTooltip.style.setProperty("--tip-y", `${y}px`);
  }

  function hideUsageTip() {
    if (el.usageTooltip) el.usageTooltip.hidden = true;
  }

  function syncUsageExportLinks() {
    const d = encodeURIComponent(state.usageDays || "all");
    if (el.usageExportCsvLink) el.usageExportCsvLink.href = `/api/usage/export.csv?days=${d}`;
    if (el.usageExportJsonLink) el.usageExportJsonLink.href = `/api/usage/export.json?days=${d}`;
    if (el.usageExportMdLink) el.usageExportMdLink.href = `/api/usage/export.md?days=${d}`;
  }

  async function ensureUsageLoaded(force = false) {
    if (!force && state.usageData && state.usageData.window?.range === state.usageDays) {
      renderUsageDashboard(state.usageData);
      return;
    }
    await loadUsageDashboard(state.usageDays);
  }

  async function loadUsageDashboard(days = state.usageDays, { priority = "auto" } = {}) {
    state.usageDays = days || "all";
    syncUsageExportLinks();
    for (const btn of el.usageRangeGroup.querySelectorAll("[data-usage-days]")) {
      btn.classList.toggle("active", btn.dataset.usageDays === state.usageDays);
    }
    try {
      const data = await apiFetch(`/api/usage?days=${encodeURIComponent(state.usageDays)}`, { priority });
      state.usageData = data;
      if (state.activeTab === "usage") {
        renderUsageDashboard(data);
      }
    } catch (err) {
      if (state.activeTab === "usage" && el.usageBriefList) {
        el.usageBriefList.innerHTML = `<li style="color:var(--danger)">Failed to load telemetry: ${escapeHtml(err.message)}</li>`;
      }
    }
  }

  function buildSparklineSvg(points, priorAvg) {
    const vals = points && points.length ? points : [0, 0, 0, 0, 0, 0, 0];
    const maxV = Math.max(1e-6, ...vals, Number(priorAvg || 0) * 1.15);
    const w = 86;
    const h = 36;
    const pad = 4;
    const coords = vals.map((v, idx) => {
      const x = pad + (idx / Math.max(1, vals.length - 1)) * (w - pad * 2);
      const y = h - pad - (Number(v) / maxV) * (h - pad * 2);
      return [x.toFixed(1), y.toFixed(1)];
    });
    const linePts = coords.map(([x, y]) => `${x},${y}`).join(" ");
    const areaPts = `${pad},${h - pad} ${linePts} ${w - pad},${h - pad}`;
    const avgY = (h - pad - (Math.min(maxV, Number(priorAvg || 0)) / maxV) * (h - pad * 2)).toFixed(1);
    return `
      <svg class="pulse-spark" viewBox="0 0 ${w} ${h}" aria-hidden="true">
        <polygon points="${areaPts}" fill="currentColor" opacity="0.12" style="color:var(--brand-primary)"></polygon>
        <line x1="${pad}" y1="${avgY}" x2="${w - pad}" y2="${avgY}" stroke="var(--text-muted)" stroke-width="1" stroke-dasharray="2.5 2.5" opacity="0.6"></line>
        <polyline points="${linePts}" fill="none" stroke="var(--brand-primary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></polyline>
      </svg>
    `;
  }

  function renderUsageDashboard(data) {
    if (!data) return;
    const win = data.window || {};
    const vol = data.volume || {};
    const cost = data.cost || {};
    const qual = data.quality || {};
    const sav = data.savings || {};

    const stor = data.storage || {};
    const subNodes = ["Window: "];
    const winStrong = document.createElement("strong");
    winStrong.textContent = String(win.label || "All");
    subNodes.push(winStrong, " · Active Engine: ");
    const modelCode = document.createElement("code");
    modelCode.textContent = String(win.model || "gpt-6-luna");
    subNodes.push(modelCode);
    if (stor.label) {
      subNodes.push(" · 💾 ");
      const storStrong = document.createElement("strong");
      storStrong.textContent = String(stor.label);
      subNodes.push(storStrong, ` (${numFmt.format(stor.persisted_files || 0)} durable records)`);
    }
    subNodes.push(" · Refreshed ");
    const tsCode = document.createElement("code");
    tsCode.textContent = String(win.generated_at_iso || "");
    subNodes.push(tsCode);
    el.usageWindowSub.replaceChildren(...subNodes);

    // 1. 7-Day Pulse Sparklines
    el.usagePulseGrid.innerHTML = (data.pulse || [])
      .map((c) => {
        const sign = c.delta_pct > 0 ? "+" : "";
        return `
          <div class="pulse-card">
            <div>
              <div class="pulse-label">${escapeHtml(c.label)}</div>
              <div class="pulse-val-row">
                <span class="pulse-val">${escapeHtml(c.display)}</span>
                <span class="pulse-delta ${escapeHtml(c.delta_dir)}">${sign}${escapeHtml(c.delta_pct)}%</span>
              </div>
              <div class="pulse-sub">${escapeHtml(c.sub)}</div>
            </div>
            ${buildSparklineSvg(c.sparkline, c.prior_avg)}
          </div>
        `;
      })
      .join("");

    // 2. "In brief" Executive Summary
    el.usageBriefList.innerHTML = (data.brief || []).map((b) => `<li>${escapeHtml(b)}</li>`).join("");

    // 3. Hero Tile Wall + Total Spend Split
    const tiles = data.tiles || [];
    el.usageTileCaption.textContent = `${numFmt.format(tiles.length)} recent request${tiles.length === 1 ? "" : "s"} · hover any tile to inspect latency, tools & cost`;
    el.usageTileWall.innerHTML = "";
    if (!tiles.length) {
      el.usageTileWall.innerHTML = `<span class="setting-desc">No requests recorded yet — run a study or live NIAGADS query to populate the volume wall.</span>`;
    } else {
      for (const t of tiles) {
        const tile = document.createElement("span");
        tile.className = `usage-tile lvl-${t.level}`;
        tile.setAttribute("role", "listitem");
        tile.addEventListener("pointerenter", (ev) => {
          showUsageTip(
            ev,
            `<strong>${escapeHtml(t.title)}</strong><br>` +
              `${escapeHtml(t.domain_label)} · <code>${escapeHtml(t.event_type)}</code><br>` +
              `Latency: ${(t.elapsed_ms / 1000).toFixed(2)}s · Tools: ${t.tool_count} · Tokens: ${numFmt.format(t.total_tokens)}<br>` +
              `Cost: ${fmtUsd(t.total_cost_usd)} · ${escapeHtml(t.ts_iso)}`
          );
        });
        tile.addEventListener("pointermove", moveUsageTip);
        tile.addEventListener("pointerleave", hideUsageTip);
        el.usageTileWall.appendChild(tile);
      }
    }

    el.usageSpendTotal.textContent = fmtUsd(cost.total_usd);
    const mPct = cost.total_usd > 0 ? Math.max(4, cost.model_pct) : 50;
    const cPct = cost.total_usd > 0 ? Math.max(4, 100 - mPct) : 50;
    el.usageSplitModel.style.width = `${mPct}%`;
    el.usageSplitCloud.style.width = `${cPct}%`;
    el.usageModelPct.textContent = `${cost.model_pct || 0}%`;
    el.usageCloudPct.textContent = `${cost.cloud_pct || 0}%`;
    el.usageCostKpis.innerHTML = `
      <div class="mini-kpi">
        <div class="mini-kpi-lbl">Model Token Spend</div>
        <div class="mini-kpi-val">${fmtUsd(cost.model_usd)}</div>
      </div>
      <div class="mini-kpi">
        <div class="mini-kpi-lbl">Cloud Run Compute</div>
        <div class="mini-kpi-val">${fmtUsd(cost.cloud_usd)}</div>
      </div>
      <div class="mini-kpi">
        <div class="mini-kpi-lbl">Avg Cost / Study</div>
        <div class="mini-kpi-val">${fmtUsd(cost.avg_per_study_usd)}</div>
      </div>
      <div class="mini-kpi">
        <div class="mini-kpi-lbl">Prompt Cache Hit</div>
        <div class="mini-kpi-val">${escapeHtml(cost.cache_hit_pct || 0)}%</div>
      </div>
    `;
    el.usagePricingNote.textContent = cost.pricing_note || "";

    // 4. Four-Card Volume Strip
    const pk = vol.peak_day || { date: "—", total_events: 0, total_tokens: 0 };
    el.usageVolumeStrip.innerHTML = `
      <div class="vol-card">
        <div class="vol-card-lbl">Genomic &amp; Report Volume</div>
        <div class="vol-card-val">${fmtBytes(vol.bytes_processed)}</div>
        <div class="vol-card-sub">${numFmt.format(vol.completed_studies_count || 0)} reports · ${numFmt.format(vol.api_queries_count || 0)} live API payloads · ${numFmt.format(vol.uploads_count || 0)} uploads</div>
      </div>
      <div class="vol-card">
        <div class="vol-card-lbl">Model Token Volume</div>
        <div class="vol-card-val">${compactFmt.format(vol.total_tokens || 0)}</div>
        <div class="vol-card-sub">In ${compactFmt.format(vol.input_tokens || 0)} · Out ${compactFmt.format(vol.output_tokens || 0)} · Cached ${compactFmt.format(vol.cached_tokens || 0)}</div>
      </div>
      <div class="vol-card">
        <div class="vol-card-lbl">Workspaces &amp; Threads</div>
        <div class="vol-card-val">${numFmt.format(vol.unique_workspaces || 0)}</div>
        <div class="vol-card-sub">${numFmt.format(vol.threads_count || 0)} saved threads · ${escapeHtml(vol.avg_per_workspace || 0)} req / workspace</div>
      </div>
      <div class="vol-card">
        <div class="vol-card-lbl">Peak Activity Day</div>
        <div class="vol-card-val">${escapeHtml(pk.date)}</div>
        <div class="vol-card-sub">${numFmt.format(pk.total_events || 0)} requests · ${compactFmt.format(pk.total_tokens || 0)} tokens</div>
      </div>
    `;

    // 5. Interactive SVG Charts
    renderDailyVolumeChart(data.timeline || []);
    renderCumulativeSpendChart(data.timeline || []);
    renderLatencyScatterChart(data.scatter || []);
    renderArrivalHeatmapChart(data.heatmap || {});

    // 6. Grounded Tool Mix & Funnel
    const tools = data.tool_mix?.tools || [];
    const totTools = data.tool_mix?.total_calls || 0;
    el.usageToolSub.textContent = `${numFmt.format(totTools)} grounded tool & live endpoint call${totTools === 1 ? "" : "s"} in window`;
    el.usageToolBand.innerHTML = tools.length
      ? tools
          .map(
            (t) =>
              `<span style="width:${Math.max(2, t.pct)}%;background:${TOOL_COLORS[t.color_idx % TOOL_COLORS.length]}" title="${escapeHtml(t.name)}: ${t.count} (${t.pct}%)"></span>`
          )
          .join("")
      : `<span style="width:100%;background:var(--border-subtle)"></span>`;

    el.usageToolList.innerHTML = tools.length
      ? tools
          .map(
            (t) => `
          <div class="tool-mix-row">
            <span class="tool-mix-name">
              <i class="legend-dot" style="background:${TOOL_COLORS[t.color_idx % TOOL_COLORS.length]}"></i>
              ${escapeHtml(t.name)}
            </span>
            <span><strong>${numFmt.format(t.count)}</strong> (${t.pct}%)</span>
            <span style="color:var(--text-muted)">${numFmt.format(t.median_ms)} ms med</span>
          </div>
        `
          )
          .join("")
      : `<div class="setting-desc">No tool calls recorded in this window yet.</div>`;

    el.usageFunnelList.innerHTML = (data.funnel || [])
      .map(
        (f) => `
        <div class="funnel-row">
          <div class="funnel-top">
            <span>${escapeHtml(f.label)}</span>
            <span><strong>${numFmt.format(f.count)}</strong> · ${f.pct_of_top}%</span>
          </div>
          <div class="funnel-track">
            <div class="funnel-fill" style="width:${Math.max(2, f.pct_of_top)}%"></div>
          </div>
        </div>
      `
      )
      .join("");

    // 7. Biomedical Domains & Quality DL
    renderDomainBars(data.domains || []);
    el.usageQualityDl.innerHTML = `
      <div class="quality-item">
        <dt>Median Study Runtime</dt>
        <dd>${qual.median_elapsed_s || 0}s <span style="font-size:0.72rem;color:var(--text-muted)">(p90 ${qual.p90_elapsed_s || 0}s)</span></dd>
      </div>
      <div class="quality-item">
        <dt>Median First-Event TTFT</dt>
        <dd>${numFmt.format(qual.median_ttft_ms || 0)} ms</dd>
      </div>
      <div class="quality-item">
        <dt>Study Completion Rate</dt>
        <dd>${qual.completion_rate_pct ?? 100}%</dd>
        <div class="quality-meter-track"><div class="quality-meter-fill" style="width:${qual.completion_rate_pct ?? 100}%"></div></div>
      </div>
      <div class="quality-item">
        <dt>Exact Token Telemetry</dt>
        <dd>${qual.exact_token_pct ?? 100}%</dd>
        <div class="quality-meter-track"><div class="quality-meter-fill" style="width:${qual.exact_token_pct ?? 100}%"></div></div>
      </div>
      <div class="quality-item">
        <dt>⚡ Fast Mode Share</dt>
        <dd>${qual.fast_mode_pct ?? 100}%</dd>
      </div>
      <div class="quality-item">
        <dt>Avg Tools / Study</dt>
        <dd>${qual.avg_tools_per_study || 0}</dd>
      </div>
    `;

    // 8. Estimated Researcher Time Saved
    el.usageSavingsGrid.innerHTML = `
      <div class="mini-kpi">
        <div class="mini-kpi-lbl">Researcher Hours Saved</div>
        <div class="mini-kpi-val">${sav.hours_saved || 0} hrs <span style="font-size:0.74rem;color:var(--text-muted)">(${sav.minutes_saved || 0} min)</span></div>
      </div>
      <div class="mini-kpi">
        <div class="mini-kpi-lbl">Estimated Research Value</div>
        <div class="mini-kpi-val">$${Number(sav.value_usd || 0).toFixed(2)}</div>
      </div>
      <div class="mini-kpi">
        <div class="mini-kpi-lbl">Value / Compute Spend Multiple</div>
        <div class="mini-kpi-val">${sav.net_roi_multiple ? `${sav.net_roi_multiple}×` : "—"}</div>
      </div>
    `;
    el.usageSavingsNote.textContent = sav.assumptions_note || "";

    // 9. Ledger & Workspaces Tables
    renderUsageLedgerTable();
    renderWorkspacesTable(data.workspaces || []);
  }

  function renderDomainBars(domains) {
    el.usageClearDomainBtn.hidden = !state.usageLedgerDomain;
    el.usageDomainBars.innerHTML = "";
    if (!domains.length) {
      el.usageDomainBars.innerHTML = `<div class="setting-desc">No domain traffic in window.</div>`;
      return;
    }
    for (const d of domains) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "domain-bar-btn" + (state.usageLedgerDomain === d.id ? " active" : "");
      const fillCol = DOMAIN_COLORS[d.id] || "var(--brand-primary)";
      btn.innerHTML = `
        <div class="domain-bar-top">
          <span>${escapeHtml(d.label)}</span>
          <span>${numFmt.format(d.count)} (${d.pct}%) · ${d.avg_elapsed_s}s avg</span>
        </div>
        <div class="domain-track">
          <div class="domain-fill" style="width:${Math.max(2, d.pct)}%;background:${fillCol}"></div>
        </div>
      `;
      btn.addEventListener("click", () => {
        state.usageLedgerDomain = state.usageLedgerDomain === d.id ? "" : d.id;
        renderDomainBars(domains);
        renderUsageLedgerTable();
      });
      el.usageDomainBars.appendChild(btn);
    }
  }

  function renderDailyVolumeChart(timeline) {
    const svg = el.svgDailyVolume;
    const W = 540;
    const H = 210;
    const padL = 36;
    const padR = 14;
    const padT = 16;
    const padB = 30;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;
    const rows = timeline.length ? timeline : [{ date: "Today", studies: 0, api_queries: 0, triage: 0, total_events: 0 }];
    const maxV = Math.max(1, ...rows.map((r) => r.total_events || 0));

    let markup = `
      <line x1="${padL}" y1="${padT + plotH}" x2="${W - padR}" y2="${padT + plotH}" stroke="var(--border-strong)" stroke-width="1"/>
      <text x="${padL - 6}" y="${padT + 8}" text-anchor="end" font-size="10" fill="var(--text-muted)">${maxV}</text>
      <text x="${padL - 6}" y="${padT + plotH}" text-anchor="end" font-size="10" fill="var(--text-muted)">0</text>
    `;
    const step = plotW / rows.length;
    const barW = Math.max(3, Math.min(26, step * 0.68));
    rows.forEach((r, idx) => {
      const x = padL + idx * step + (step - barW) / 2;
      const totH = ((r.total_events || 0) / maxV) * plotH;
      const studyH = ((r.studies || 0) / maxV) * plotH;
      const yTop = padT + plotH - totH;
      const yStudy = padT + plotH - studyH;
      const apiFill = r.is_peak ? "#d97706" : "#6366f1";
      const studyFill = r.is_peak ? "#b45309" : "#0f766e";
      markup += `<g class="chart-bar-grp" data-idx="${idx}">`;
      if (totH > studyH) {
        markup += `<rect x="${x.toFixed(1)}" y="${yTop.toFixed(1)}" width="${barW.toFixed(1)}" height="${(totH - studyH).toFixed(1)}" rx="2" fill="${apiFill}" opacity="0.82"/>`;
      }
      if (studyH > 0) {
        markup += `<rect x="${x.toFixed(1)}" y="${yStudy.toFixed(1)}" width="${barW.toFixed(1)}" height="${studyH.toFixed(1)}" rx="2" fill="${studyFill}"/>`;
      }
      markup += `<rect x="${(padL + idx * step).toFixed(1)}" y="${padT}" width="${step.toFixed(1)}" height="${plotH}" fill="transparent"/>`;
      markup += `</g>`;
      if (idx === 0 || idx === rows.length - 1 || idx === Math.floor(rows.length / 2)) {
        markup += `<text x="${(x + barW / 2).toFixed(1)}" y="${H - 8}" text-anchor="middle" font-size="10" fill="var(--text-muted)">${escapeHtml(String(r.date).slice(5))}</text>`;
      }
    });
    svg.innerHTML = markup;
    for (const grp of svg.querySelectorAll(".chart-bar-grp")) {
      const r = rows[Number(grp.dataset.idx)];
      grp.addEventListener("pointerenter", (ev) => {
        showUsageTip(
          ev,
          `<strong>${escapeHtml(r.date)}</strong>${r.is_peak ? " · 🔥 Peak Day" : ""}<br>` +
            `Agent studies: <strong>${r.studies}</strong> · NIAGADS v2.0 API: <strong>${r.api_queries}</strong><br>` +
            `Tokens: ${numFmt.format(r.total_tokens || 0)} · Spend: ${fmtUsd(r.spend_usd)}`
        );
      });
      grp.addEventListener("pointermove", moveUsageTip);
      grp.addEventListener("pointerleave", hideUsageTip);
    }
  }

  function renderCumulativeSpendChart(timeline) {
    const svg = el.svgCumulativeSpend;
    const W = 540;
    const H = 210;
    const padL = 48;
    const padR = 16;
    const padT = 16;
    const padB = 30;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;
    const rows = timeline.length ? timeline : [{ date: "Today", cumulative_spend_usd: 0, cumulative_tokens: 0 }];
    const maxS = Math.max(0.0001, ...rows.map((r) => Number(r.cumulative_spend_usd || 0)));

    const pts = rows.map((r, idx) => {
      const x = padL + (idx / Math.max(1, rows.length - 1)) * plotW;
      const y = padT + plotH - (Number(r.cumulative_spend_usd || 0) / maxS) * plotH;
      return { x, y, r };
    });
    const lineStr = pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
    const areaStr = `${padL},${padT + plotH} ${lineStr} ${padL + plotW},${padT + plotH}`;

    let markup = `
      <line x1="${padL}" y1="${padT + plotH}" x2="${W - padR}" y2="${padT + plotH}" stroke="var(--border-strong)" stroke-width="1"/>
      <text x="${padL - 6}" y="${padT + 8}" text-anchor="end" font-size="10" fill="var(--text-muted)">${fmtUsd(maxS)}</text>
      <text x="${padL - 6}" y="${padT + plotH}" text-anchor="end" font-size="10" fill="var(--text-muted)">$0</text>
      <polygon points="${areaStr}" fill="#0f766e" opacity="0.14"/>
      <polyline points="${lineStr}" fill="none" stroke="#0f766e" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
    `;
    pts.forEach((p, idx) => {
      markup += `<circle class="cum-pt" data-idx="${idx}" cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="4" fill="#0f766e" opacity="${rows.length > 35 ? "0" : "0.9"}"/>`;
      if (idx === 0 || idx === pts.length - 1) {
        markup += `<text x="${p.x.toFixed(1)}" y="${H - 8}" text-anchor="${idx === 0 ? "start" : "end"}" font-size="10" fill="var(--text-muted)">${escapeHtml(String(p.r.date).slice(5))}</text>`;
      }
    });
    svg.innerHTML = markup;
    for (const c of svg.querySelectorAll(".cum-pt")) {
      const r = rows[Number(c.dataset.idx)];
      c.addEventListener("pointerenter", (ev) => {
        showUsageTip(
          ev,
          `<strong>${escapeHtml(r.date)}</strong><br>` +
            `Cumulative Spend: <strong>${fmtUsd(r.cumulative_spend_usd)}</strong><br>` +
            `Cumulative Tokens: <strong>${numFmt.format(r.cumulative_tokens || 0)}</strong>`
        );
      });
      c.addEventListener("pointermove", moveUsageTip);
      c.addEventListener("pointerleave", hideUsageTip);
    }
  }

  function renderLatencyScatterChart(scatter) {
    const svg = el.svgLatencyScatter;
    const W = 540;
    const H = 210;
    const padL = 42;
    const padR = 18;
    const padT = 16;
    const padB = 30;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;

    if (!scatter.length) {
      svg.innerHTML = `<text x="${W / 2}" y="${H / 2}" text-anchor="middle" font-size="12" fill="var(--text-muted)">Run a study in Research Studio to plot Latency vs. Grounded Tool Calls</text>`;
      return;
    }

    const maxTools = Math.max(4, ...scatter.map((s) => s.tool_count || 0));
    const maxSec = Math.max(5, ...scatter.map((s) => s.elapsed_s || 0.5));
    let markup = `
      <line x1="${padL}" y1="${padT + plotH}" x2="${W - padR}" y2="${padT + plotH}" stroke="var(--border-strong)" stroke-width="1"/>
      <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + plotH}" stroke="var(--border-strong)" stroke-width="1"/>
      <text x="${padL - 6}" y="${padT + 8}" text-anchor="end" font-size="10" fill="var(--text-muted)">${maxSec.toFixed(0)}s</text>
      <text x="${padL - 6}" y="${padT + plotH}" text-anchor="end" font-size="10" fill="var(--text-muted)">0s</text>
      <text x="${padL}" y="${H - 8}" font-size="10" fill="var(--text-muted)">0 tools</text>
      <text x="${W - padR}" y="${H - 8}" text-anchor="end" font-size="10" fill="var(--text-muted)">${maxTools} tools</text>
    `;

    scatter.forEach((pt, idx) => {
      const x = padL + ((pt.tool_count || 0) / maxTools) * plotW;
      const y = padT + plotH - (Math.min(maxSec, pt.elapsed_s || 0) / maxSec) * plotH;
      const col = DOMAIN_COLORS[pt.domain] || "#0f766e";
      const radius = pt.speed_mode === "fast" ? 5.2 : 6.4;
      markup += `<circle class="scat-pt" data-idx="${idx}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${radius}" fill="${col}" fill-opacity="0.82" stroke="#ffffff" stroke-width="1.2" style="cursor:pointer"/>`;
    });
    svg.innerHTML = markup;
    for (const c of svg.querySelectorAll(".scat-pt")) {
      const pt = scatter[Number(c.dataset.idx)];
      c.addEventListener("pointerenter", (ev) => {
        showUsageTip(
          ev,
          `<strong>${escapeHtml(pt.title)}</strong><br>` +
            `${escapeHtml(pt.domain_label)} · <code>${escapeHtml(pt.speed_mode)}</code><br>` +
            `Latency: <strong>${pt.elapsed_s}s</strong> (TTFT ${pt.ttft_ms} ms) · Tools: <strong>${pt.tool_count}</strong><br>` +
            `Tokens: ${numFmt.format(pt.total_tokens)} · Cost: ${fmtUsd(pt.cost_usd)}`
        );
      });
      c.addEventListener("pointermove", moveUsageTip);
      c.addEventListener("pointerleave", hideUsageTip);
    }
  }

  function renderArrivalHeatmapChart(heatmap) {
    const svg = el.svgArrivalHeatmap;
    const days = heatmap.weekday_labels || ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    const grid = heatmap.grid || Array.from({ length: 7 }, () => Array(24).fill(0));
    const maxC = Math.max(1, heatmap.max_count || 1);
    el.usageHeatmapSub.textContent = `Weekday × UTC hour · Peak slot: ${heatmap.peak_slot || "—"}`;

    const W = 540;
    const H = 210;
    const padL = 38;
    const padR = 12;
    const padT = 12;
    const padB = 26;
    const cellW = (W - padL - padR) / 24;
    const cellH = (H - padT - padB) / 7;

    let markup = "";
    for (let d = 0; d < 7; d++) {
      const y = padT + d * cellH;
      markup += `<text x="${padL - 6}" y="${(y + cellH * 0.72).toFixed(1)}" text-anchor="end" font-size="9.5" fill="var(--text-muted)">${days[d]}</text>`;
      for (let h = 0; h < 24; h++) {
        const cnt = grid[d]?.[h] || 0;
        const x = padL + h * cellW;
        const alpha = cnt === 0 ? 0.08 : 0.22 + 0.78 * (cnt / maxC);
        const fill = cnt === 0 ? "var(--border-strong)" : "#0f766e";
        markup += `<rect class="hm-cell" data-d="${d}" data-h="${h}" data-cnt="${cnt}" x="${(x + 1).toFixed(1)}" y="${(y + 1).toFixed(1)}" width="${(cellW - 2).toFixed(1)}" height="${(cellH - 2).toFixed(1)}" rx="2.5" fill="${fill}" fill-opacity="${alpha.toFixed(2)}"/>`;
      }
    }
    for (const hr of [0, 6, 12, 18, 23]) {
      const hx = padL + hr * cellW + cellW / 2;
      markup += `<text x="${hx.toFixed(1)}" y="${H - 7}" text-anchor="middle" font-size="9.5" fill="var(--text-muted)">${String(hr).padStart(2, "0")}h</text>`;
    }
    svg.innerHTML = markup;
    for (const r of svg.querySelectorAll(".hm-cell")) {
      r.addEventListener("pointerenter", (ev) => {
        const dName = days[Number(r.dataset.d)];
        const hh = String(r.dataset.h).padStart(2, "0");
        showUsageTip(ev, `<strong>${dName} ${hh}:00 UTC</strong><br>${r.dataset.cnt} request(s)`);
      });
      r.addEventListener("pointermove", moveUsageTip);
      r.addEventListener("pointerleave", hideUsageTip);
    }
  }

  function renderUsageLedgerTable() {
    const allRows = state.usageData?.ledger || [];
    const q = state.usageLedgerSearch.trim().toLowerCase();
    const filtered = allRows.filter((r) => {
      if (state.usageLedgerType !== "all" && r.event_type !== state.usageLedgerType) return false;
      if (state.usageLedgerDomain && r.domain !== state.usageLedgerDomain) return false;
      if (!q) return true;
      const hay = `${r.title} ${r.domain_label} ${r.workspace_label} ${r.event_type} ${r.id}`.toLowerCase();
      return hay.includes(q);
    });

    const col = state.usageSortCol;
    const dir = state.usageSortDir === "asc" ? 1 : -1;
    filtered.sort((a, b) => ((Number(a[col]) || 0) - (Number(b[col]) || 0)) * dir);

    el.usageLedgerCount.textContent =
      `Showing ${numFmt.format(filtered.length)} of ${numFmt.format(allRows.length)} recorded requests` +
      (state.usageLedgerDomain ? ` · Domain filter active` : "");

    if (!filtered.length) {
      el.usageLedgerTbody.innerHTML = `<tr><td colspan="10" style="text-align:center;color:var(--text-muted)">No matching requests in this filter/window.</td></tr>`;
      return;
    }

    const typeLabels = {
      study_run: "Study",
      niagads_api: "NIAGADS v2.0",
      plan_triage: "Plan/Triage",
      file_upload: "Upload",
    };

    el.usageLedgerTbody.innerHTML = filtered
      .slice(0, 120)
      .map((r) => {
        const latStr = r.elapsed_ms >= 1000 ? `${(r.elapsed_ms / 1000).toFixed(2)}s` : `${r.elapsed_ms} ms`;
        const modeBadge =
          r.event_type === "study_run"
            ? r.speed_mode === "deep"
              ? "🔬 Deep"
              : r.speed_mode === "critic"
                ? "🏛️ Critic"
                : "⚡ Fast"
            : "REST";
        const repHtml = r.report_url
          ? `<a href="${escapeHtml(r.report_url)}" class="link-btn" download>⬇ .md</a>`
          : `<span style="color:var(--text-muted)">—</span>`;
        return `
          <tr>
            <td>${escapeHtml(r.ts_iso.replace(" UTC", ""))}</td>
            <td><span class="ledger-type-pill ${escapeHtml(r.event_type)}">${escapeHtml(typeLabels[r.event_type] || r.event_type)}</span></td>
            <td><strong>${escapeHtml(r.title)}</strong></td>
            <td>${escapeHtml(r.domain_label)}</td>
            <td>${escapeHtml(modeBadge)}</td>
            <td>${escapeHtml(latStr)}</td>
            <td>${numFmt.format(r.tool_count || 0)}</td>
            <td>${numFmt.format(r.total_tokens || 0)}</td>
            <td>${fmtUsd(r.total_cost_usd)}</td>
            <td>${repHtml}</td>
          </tr>
        `;
      })
      .join("");
  }

  function renderWorkspacesTable(workspaces) {
    if (!workspaces.length) {
      el.usageWorkspacesTbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">No active workspaces in this window.</td></tr>`;
      return;
    }
    el.usageWorkspacesTbody.innerHTML = workspaces
      .map(
        (w) => `
        <tr>
          <td><strong>${escapeHtml(w.workspace_label)}</strong></td>
          <td>${numFmt.format(w.studies)}</td>
          <td>${numFmt.format(w.api_queries)}</td>
          <td>${numFmt.format(w.tool_calls)}</td>
          <td>${numFmt.format(w.total_tokens)}</td>
          <td>${fmtUsd(w.spend_usd)}</td>
          <td>${escapeHtml(w.last_seen_iso)}</td>
        </tr>
      `
      )
      .join("");
  }

  function exportSvgAsPng(svgId, filename) {
    const svgEl = document.getElementById(svgId);
    if (!svgEl) return;
    const clone = svgEl.cloneNode(true);
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    const resolvedText = getComputedStyle(document.documentElement).getPropertyValue("--text-muted").trim() || "#64748b";
    const resolvedBorder = getComputedStyle(document.documentElement).getPropertyValue("--border-strong").trim() || "#cbd5e1";
    const serialized = new XMLSerializer()
      .serializeToString(clone)
      .replace(/var\(--text-muted\)/g, resolvedText)
      .replace(/var\(--border-strong\)/g, resolvedBorder)
      .replace(/var\(--brand-primary\)/g, "#0f766e");

    const blob = new Blob([serialized], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = 1080;
      canvas.height = 420;
      const ctx = canvas.getContext("2d");
      const isDark = document.querySelector('meta[name="color-scheme"]')?.content === "dark";
      ctx.fillStyle = isDark ? "#141e29" : "#ffffff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      const a = document.createElement("a");
      a.download = filename || "ligase_chart.png";
      a.href = canvas.toDataURL("image/png");
      a.click();
    };
    img.src = url;
  }

  // Usage Dashboard Event Listeners
  el.usageRangeGroup.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-usage-days]");
    if (!btn) return;
    loadUsageDashboard(btn.dataset.usageDays);
  });

  el.usageRefreshBtn.addEventListener("click", () => {
    loadUsageDashboard(state.usageDays);
  });

  el.usagePrintPdfBtn.addEventListener("click", () => {
    el.usageExportDropdown.open = false;
    window.print();
  });

  el.usageClearDomainBtn.addEventListener("click", () => {
    state.usageLedgerDomain = "";
    renderDomainBars(state.usageData?.domains || []);
    renderUsageLedgerTable();
  });

  el.usageTypeFilterGroup.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-ledger-type]");
    if (!btn) return;
    state.usageLedgerType = btn.dataset.ledgerType;
    for (const b of el.usageTypeFilterGroup.querySelectorAll("[data-ledger-type]")) {
      b.classList.toggle("active", b === btn);
    }
    renderUsageLedgerTable();
  });

  el.usageLedgerSearch.addEventListener("input", () => {
    state.usageLedgerSearch = el.usageLedgerSearch.value;
    renderUsageLedgerTable();
  });

  for (const sortBtn of el.usageLedgerTable.querySelectorAll("[data-sort-col]")) {
    sortBtn.addEventListener("click", () => {
      const col = sortBtn.dataset.sortCol;
      if (state.usageSortCol === col) {
        state.usageSortDir = state.usageSortDir === "desc" ? "asc" : "desc";
      } else {
        state.usageSortCol = col;
        state.usageSortDir = "desc";
      }
      renderUsageLedgerTable();
    });
  }

  for (const pngBtn of document.querySelectorAll("[data-export-svg]")) {
    pngBtn.addEventListener("click", () => {
      exportSvgAsPng(pngBtn.dataset.exportSvg, pngBtn.dataset.exportName);
    });
  }

  document.addEventListener("keydown", (ev) => {
    if (
      state.activeTab === "usage" &&
      (ev.key === "r" || ev.key === "R") &&
      !ev.metaKey &&
      !ev.ctrlKey &&
      !ev.altKey &&
      !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName || "")
    ) {
      ev.preventDefault();
      loadUsageDashboard(state.usageDays);
    }
  });

  // ── Dialog Controls & Light-Dismiss Fallback ──────────────────────────────
  async function ensureFullMetaLoaded() {
    if (state.fullMetaLoaded && state.meta?.tools?.length) return;
    try {
      const fullMeta = await apiFetch("/api/meta", { priority: "low" });
      applyMetaState(fullMeta, { full: true });
    } catch {}
  }

  el.openCatalogBtn.addEventListener("click", async () => {
    await ensureFullMetaLoaded();
    el.catalogDialog.showModal();
  });
  el.inspectCatalogInline.addEventListener("click", async () => {
    await ensureFullMetaLoaded();
    el.catalogDialog.showModal();
  });
  el.openSettingsBtn.addEventListener("click", () => el.settingsDialog.showModal());

  for (const dlg of [el.catalogDialog, el.settingsDialog]) {
    dlg.addEventListener("close", () => {
      dlg.returnValue = "";
    });
  }

  if (!("closedBy" in HTMLDialogElement.prototype)) {
    const outside = (e, dialog) => {
      const r = dialog.getBoundingClientRect();
      return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
    };
    for (const dialog of document.querySelectorAll('dialog[closedby="any"]')) {
      let pressedOutside = false;
      dialog.addEventListener("pointerdown", (e) => {
        pressedOutside = outside(e, dialog);
      });
      dialog.addEventListener("pointerup", (e) => {
        if (pressedOutside && outside(e, dialog)) dialog.close();
      });
    }
  }

  // ── Theme Override Controls (dark-mode-toggle) ────────────────────────────
  const metaColorScheme = document.querySelector('meta[name="color-scheme"]');
  const themeButtons = Array.from(document.querySelectorAll("[data-theme-choice]"));

  function syncThemeButtons() {
    let stored = null;
    try {
      stored = localStorage.getItem("color-scheme");
    } catch {}
    const activeChoice = stored === "light" || stored === "dark" ? stored : "system";
    metaColorScheme.content = stored === "light" || stored === "dark" ? stored : "light dark";
    for (const btn of themeButtons) {
      btn.classList.toggle("active", btn.dataset.themeChoice === activeChoice);
    }
  }

  for (const btn of themeButtons) {
    btn.addEventListener("click", () => {
      const choice = btn.dataset.themeChoice;
      try {
        if (choice === "light" || choice === "dark") {
          localStorage.setItem("color-scheme", choice);
        } else {
          localStorage.removeItem("color-scheme");
        }
      } catch {}
      syncThemeButtons();
    });
  }

  window.addEventListener("storage", (ev) => {
    if (ev.key === "color-scheme") syncThemeButtons();
  });

  // ── Header / Sidebar Controls ─────────────────────────────────────────────
  el.profileAd1Btn.addEventListener("click", () => setProfile("ad1"));
  el.profileA1Btn.addEventListener("click", () => setProfile("a1"));
  el.speedFastBtn.addEventListener("click", () => setSpeedMode("fast"));
  el.speedDeepBtn.addEventListener("click", () => setSpeedMode("deep"));
  el.speedCriticBtn?.addEventListener("click", () => setSpeedMode("critic"));
  el.modeDirectBtn.addEventListener("click", () => setMode("direct"));
  el.modePlanBtn.addEventListener("click", () => setMode("plan"));
  el.newStudyBtn.addEventListener("click", startFreshStudy);
  el.openSidebarBtn.addEventListener("click", () => el.sidebar.classList.add("open"));
  el.closeSidebarBtn.addEventListener("click", () => el.sidebar.classList.remove("open"));
  el.maxIterSelect.addEventListener("change", () => {
    state.maxIterations = Number(el.maxIterSelect.value) || 10;
  });

  // ── Boot (Ultra-Lean SSR Hydration + Idle Low-Priority Background Sync) ───
  function readServerBootstrap() {
    const node = document.getElementById("ligase-bootstrap");
    if (!node || !node.textContent) return null;
    try {
      return JSON.parse(node.textContent);
    } catch {
      return null;
    }
  }

  function applyMetaState(meta, { full = false } = {}) {
    state.meta = { ...(state.meta || {}), ...meta };
    if (full || meta.tools?.length) {
      state.fullMetaLoaded = true;
    }
    if (meta.niagads?.open_access) {
      state.oaCatalog = meta.niagads.open_access;
    }
    el.appVersion.textContent = `v${state.meta.version}`;
    el.modelBadgeText.textContent = state.meta.model;
    el.statusDot.classList.toggle("offline", !state.meta.ready);
    el.diagnosticsSummary.textContent = `Model: ${state.meta.model} · Engine: Ligase v${state.meta.version} · Sandbox: ${state.meta.sandbox_mode} · Ready: ${state.meta.ready ? "Yes" : "Missing API Key"}`;
    renderStarters();
    if (state.meta.tools?.length) {
      renderCatalogDialog();
    }
  }

  function scheduleIdlePrefetch() {
    const runIdle =
      typeof window.requestIdleCallback === "function"
        ? (cb) => window.requestIdleCallback(cb, { timeout: 1200 })
        : (cb) => setTimeout(cb, 180);

    runIdle(async () => {
      try {
        if (!state.fullMetaLoaded) {
          await ensureFullMetaLoaded();
        }
        if (!state.mindmap) {
          state.mindmap = await apiFetch("/api/mindmap", { priority: "low" });
        }
        if (!state.usageData) {
          await loadUsageDashboard(state.usageDays, { priority: "low" });
        }
      } catch {}
    });
  }

  // ── Comments, Screenshots & Uploaded Figures Feedback Controller ─────────
  const fbState = {
    attachments: [], // [{ file, caption, objectUrl }]
    shippedLoaded: false,
    initialized: false,
  };

  const FB_CATEGORY_LABELS = {
    feature_request: "Feature Request",
    niagads_data: "NIAGADS / Genomics",
    ui_figures: "Figures & UI",
    agent_quality: "Agent Speed / Quality",
    bug_report: "Bug Report",
    general: "Improvement Brief",
  };

  function formatShortDate(iso) {
    if (!iso) return "—";
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return String(iso).slice(0, 10);
    return dt.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }

  function revokeFbObjectUrls() {
    for (const item of fbState.attachments) {
      if (item.objectUrl) {
        try {
          URL.revokeObjectURL(item.objectUrl);
        } catch {}
        item.objectUrl = "";
      }
    }
  }

  function renderFbAttachments() {
    const list = document.getElementById("fb-attachments-list");
    if (!list) return;
    list.replaceChildren();

    fbState.attachments.forEach((entry, index) => {
      const { file } = entry;
      const card = document.createElement("div");
      card.className = "fb-attachment-card";

      if (file.type && file.type.startsWith("image/")) {
        if (!entry.objectUrl) {
          entry.objectUrl = URL.createObjectURL(file);
        }
        const img = document.createElement("img");
        img.className = "fb-attachment-thumb";
        img.src = entry.objectUrl;
        img.alt = file.name;
        card.appendChild(img);
      } else {
        const icon = document.createElement("div");
        icon.className = "fb-attachment-icon";
        icon.setAttribute("aria-hidden", "true");
        const low = file.name.toLowerCase();
        icon.textContent = low.endsWith(".pdf")
          ? "📕"
          : /\.(pptx?|docx?|xlsx?)$/.test(low)
          ? "📘"
          : "📄";
        card.appendChild(icon);
      }

      const info = document.createElement("div");
      info.className = "fb-attachment-info";

      const metaRow = document.createElement("div");
      metaRow.className = "fb-attachment-meta";

      const nameSpan = document.createElement("span");
      nameSpan.className = "fb-attachment-name";
      nameSpan.textContent = file.name;
      nameSpan.title = file.name;

      const sizeSpan = document.createElement("span");
      sizeSpan.className = "fb-attachment-size";
      sizeSpan.textContent = fmtBytes(file.size);

      metaRow.append(nameSpan, sizeSpan);

      const capInput = document.createElement("input");
      capInput.type = "text";
      capInput.className = "fb-caption-input";
      capInput.maxLength = 280;
      capInput.placeholder = "Optional note on this screenshot or figure (included in email)…";
      capInput.setAttribute("aria-label", `Annotation for ${file.name}`);
      capInput.value = entry.caption || "";
      capInput.addEventListener("input", () => {
        entry.caption = capInput.value;
      });

      info.append(metaRow, capInput);
      card.appendChild(info);

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "fb-remove-btn";
      removeBtn.textContent = "✕";
      removeBtn.setAttribute("aria-label", `Remove ${file.name}`);
      removeBtn.addEventListener("click", () => {
        if (entry.objectUrl) {
          try {
            URL.revokeObjectURL(entry.objectUrl);
          } catch {}
        }
        fbState.attachments.splice(index, 1);
        renderFbAttachments();
      });
      card.appendChild(removeBtn);

      list.appendChild(card);
    });
  }

  function addFbFiles(rawFiles) {
    const MAX_FILE_BYTES = 25 * 1024 * 1024;
    const statusEl = document.getElementById("fb-status");
    for (const f of rawFiles) {
      if (f.size > MAX_FILE_BYTES) {
        if (statusEl) {
          statusEl.textContent = `File "${f.name}" exceeds the 25 MB per-file limit.`;
          statusEl.className = "fb-status-msg is-error";
        }
        continue;
      }
      let finalFile = f;
      if (fbState.attachments.some((a) => a.file.name === f.name)) {
        const dotIdx = f.name.lastIndexOf(".");
        const stem = dotIdx > 0 ? f.name.slice(0, dotIdx) : f.name;
        const ext = dotIdx > 0 ? f.name.slice(dotIdx) : "";
        finalFile = new File([f], `${stem}_${Date.now().toString().slice(-4)}${ext}`, {
          type: f.type,
        });
      }
      fbState.attachments.push({ file: finalFile, caption: "", objectUrl: "" });
    }
    renderFbAttachments();
  }

  async function captureBrowserScreenshot() {
    const statusEl = document.getElementById("fb-status");
    if (!navigator.mediaDevices?.getDisplayMedia) {
      if (statusEl) {
        statusEl.textContent = "Screen capture is not supported in this browser — press Cmd+V / Ctrl+V to paste a screenshot instead.";
        statusEl.className = "fb-status-msg is-error";
      }
      return;
    }
    let stream = null;
    try {
      stream = await navigator.mediaDevices.getDisplayMedia({
        video: { preferCurrentTab: true },
        audio: false,
      });
      const video = document.createElement("video");
      video.srcObject = stream;
      video.muted = true;
      await video.play();
      await new Promise((r) => requestAnimationFrame(r));

      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth || 1280;
      canvas.height = video.videoHeight || 800;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
      if (blob) {
        const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
        const shotFile = new File([blob], `ligase_screenshot_${stamp}.png`, { type: "image/png" });
        addFbFiles([shotFile]);
        if (statusEl) {
          statusEl.textContent = "✓ Live screenshot captured and attached!";
          statusEl.className = "fb-status-msg";
        }
      }
    } catch (err) {
      if (err?.name !== "NotAllowedError" && statusEl) {
        statusEl.textContent = `Could not capture screenshot (${err.message || "cancelled"}).`;
        statusEl.className = "fb-status-msg is-error";
      }
    } finally {
      if (stream) {
        for (const tr of stream.getTracks()) tr.stop();
      }
    }
  }

  async function loadShippedImprovements() {
    const listEl = document.getElementById("fb-shipped-list");
    const statusEl = document.getElementById("fb-shipped-status");
    if (!listEl || !statusEl || fbState.shippedLoaded) return;
    try {
      const data = await apiFetch("/api/feedback/resolved?limit=25");
      const items = Array.isArray(data.items) ? data.items : [];
      listEl.replaceChildren();
      for (const item of items) {
        const li = document.createElement("li");
        li.className = "fb-feed-item";

        const head = document.createElement("div");
        head.className = "fb-feed-head";

        const pill = document.createElement("span");
        pill.className = "fb-feed-pill";
        pill.textContent = FB_CATEGORY_LABELS[item.category] || "Shipped";

        const dateSpan = document.createElement("span");
        dateSpan.className = "fb-feed-date";
        dateSpan.textContent = `Shipped ${formatShortDate(item.resolved_at)}`;

        head.append(pill, dateSpan);

        const titleP = document.createElement("p");
        titleP.className = "fb-feed-title";
        titleP.textContent = String(item.problem || "");

        li.append(head, titleP);
        if (item.resolution) {
          const descP = document.createElement("p");
          descP.className = "fb-feed-desc";
          descP.textContent = String(item.resolution);
          li.appendChild(descP);
        }
        listEl.appendChild(li);
      }
      statusEl.textContent = items.length
        ? `${items.length} improvement${items.length === 1 ? "" : "s"} shipped from user instructions.`
        : "Resolved improvements appear here once deployed.";
      fbState.shippedLoaded = true;
    } catch (err) {
      statusEl.textContent = `Could not load shipped list: ${err.message}`;
    }
  }

  async function loadWorkspaceRecentFeedback() {
    const listEl = document.getElementById("fb-recent-list");
    const statusEl = document.getElementById("fb-recent-status");
    if (!listEl || !statusEl) return;
    try {
      const data = await apiFetch("/api/feedback/recent?limit=15");
      const items = Array.isArray(data.items) ? data.items : [];
      listEl.replaceChildren();
      if (!items.length) {
        statusEl.textContent = "No submissions from this browser workspace yet.";
        return;
      }
      statusEl.textContent = `${items.length} durable submission${items.length === 1 ? "" : "s"} saved from this workspace.`;
      for (const it of items) {
        const li = document.createElement("li");
        li.className = "fb-feed-item";

        const head = document.createElement("div");
        head.className = "fb-feed-head";

        const pill = document.createElement("span");
        pill.className = "fb-feed-pill";
        pill.textContent = `${FB_CATEGORY_LABELS[it.category] || "Feedback"} · ${it.target_area_label || it.target_area}`;

        const badgeSpan = document.createElement("span");
        badgeSpan.className = "fb-feed-date";
        const mailTxt = it.emailed ? "✉️ Emailed" : "💾 Saved";
        const attTxt = it.attachment_count ? ` · 📎 ${it.attachment_count}` : "";
        badgeSpan.textContent = `${mailTxt}${attTxt} · ${formatShortDate(it.created_at)}`;

        head.append(pill, badgeSpan);

        const bodyP = document.createElement("p");
        bodyP.className = "fb-feed-desc";
        bodyP.textContent = String(it.comment_preview || "");

        li.append(head, bodyP);
        listEl.appendChild(li);
      }
    } catch (err) {
      statusEl.textContent = `Could not load workspace submissions: ${err.message}`;
    }
  }

  function setupFeedbackValidation(formEl) {
    // Sync aria-invalid with native :user-invalid + provide WeakMap fallback for older engines
    const supportsUserInvalid = typeof CSS !== "undefined" && CSS.supports && CSS.supports("selector(:user-invalid)");
    const dirtyState = new WeakMap();

    const syncField = (field) => {
      if (!field || typeof field.checkValidity !== "function") return;
      if (supportsUserInvalid) {
        field.setAttribute("aria-invalid", field.matches(":user-invalid") ? "true" : "false");
      } else {
        const valid = field.checkValidity();
        field.classList.toggle("user-invalid-fallback", !valid);
        field.setAttribute("aria-invalid", valid ? "false" : "true");
      }
    };

    formEl.addEventListener(
      "blur",
      (ev) => {
        const target = ev.target;
        if (!target || typeof target.checkValidity !== "function") return;
        const st = dirtyState.get(target) || { interacted: false };
        if (st.interacted || supportsUserInvalid) syncField(target);
      },
      true
    );

    formEl.addEventListener("input", (ev) => {
      const target = ev.target;
      if (!target || typeof target.checkValidity !== "function") return;
      dirtyState.set(target, { interacted: true });
      if (target.hasAttribute("aria-invalid") || target.classList.contains("user-invalid-fallback")) {
        syncField(target);
      }
    });
  }

  function initFeedbackController() {
    if (fbState.initialized) return;
    fbState.initialized = true;

    const formEl = document.getElementById("feedback-form");
    const dropzone = document.getElementById("fb-dropzone");
    const fileInput = document.getElementById("fb-file-input");
    const captureBtn = document.getElementById("fb-capture-screen-btn");
    const submitBtn = document.getElementById("fb-submit-btn");
    const statusEl = document.getElementById("fb-status");
    const successBox = document.getElementById("fb-success-box");
    const successDetail = document.getElementById("fb-success-detail");
    const anotherBtn = document.getElementById("fb-submit-another-btn");
    const refreshRecentBtn = document.getElementById("fb-refresh-recent-btn");
    const commentInput = document.getElementById("fb-comment");

    if (!formEl) return;
    setupFeedbackValidation(formEl);

    // Pre-fill saved researcher name/email on this browser if previously entered
    try {
      const savedName = localStorage.getItem("ligase_fb_name") || "";
      const savedEmail = localStorage.getItem("ligase_fb_email") || "";
      const nameInput = document.getElementById("fb-name");
      const emailInput = document.getElementById("fb-email");
      if (nameInput && !nameInput.value && savedName) nameInput.value = savedName;
      if (emailInput && !emailInput.value && savedEmail) emailInput.value = savedEmail;
    } catch {}

    if (dropzone && fileInput) {
      dropzone.addEventListener("click", (ev) => {
        if (ev.target === fileInput) return;
        fileInput.click();
      });
      dropzone.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          fileInput.click();
        }
      });
      dropzone.addEventListener("dragover", (ev) => {
        ev.preventDefault();
        dropzone.classList.add("is-dragover");
      });
      dropzone.addEventListener("dragleave", () => {
        dropzone.classList.remove("is-dragover");
      });
      dropzone.addEventListener("drop", (ev) => {
        ev.preventDefault();
        dropzone.classList.remove("is-dragover");
        if (ev.dataTransfer?.files?.length) {
          addFbFiles(Array.from(ev.dataTransfer.files));
        }
      });
      fileInput.addEventListener("change", () => {
        if (fileInput.files?.length) {
          addFbFiles(Array.from(fileInput.files));
          fileInput.value = "";
        }
      });
    }

    captureBtn?.addEventListener("click", () => {
      captureBrowserScreenshot();
    });

    refreshRecentBtn?.addEventListener("click", () => {
      loadWorkspaceRecentFeedback();
    });

    // Global clipboard paste of screenshots when the Feedback tab is active
    document.addEventListener("paste", (ev) => {
      if (state.activeTab !== "feedback") return;
      const items = ev.clipboardData?.items;
      if (!items) return;
      for (let i = 0; i < items.length; i++) {
        if (items[i].type && items[i].type.startsWith("image/")) {
          ev.preventDefault();
          const blob = items[i].getAsFile();
          if (blob) {
            const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
            const ext = (blob.type.split("/")[1] || "png").replace(/[^a-z0-9]/gi, "");
            const pastedFile = new File([blob], `pasted_screenshot_${stamp}.${ext}`, {
              type: blob.type || "image/png",
            });
            addFbFiles([pastedFile]);
            if (statusEl) {
              statusEl.textContent = "📋 Screenshot pasted from clipboard and attached!";
              statusEl.className = "fb-status-msg";
            }
          }
          break;
        }
      }
    });

    // Cmd/Ctrl+Enter shortcut on comment textarea (IME-safe via isComposing check)
    commentInput?.addEventListener("keydown", (ev) => {
      if (ev.isComposing) return;
      if ((ev.metaKey || ev.ctrlKey) && ev.key === "Enter") {
        ev.preventDefault();
        formEl.requestSubmit();
      }
    });

    formEl.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      if (!formEl.checkValidity()) {
        const firstInvalid = formEl.querySelector(":invalid");
        if (firstInvalid) {
          firstInvalid.classList.add("user-invalid-fallback");
          firstInvalid.setAttribute("aria-invalid", "true");
          firstInvalid.focus();
        }
        if (statusEl) {
          statusEl.textContent = "Please complete the required comment field (and check email format if provided).";
          statusEl.className = "fb-status-msg is-error";
        }
        return;
      }

      const nameVal = document.getElementById("fb-name")?.value?.trim() || "";
      const emailVal = document.getElementById("fb-email")?.value?.trim() || "";
      const catVal = document.getElementById("fb-category")?.value || "feature_request";
      const areaVal = document.getElementById("fb-target-area")?.value || "portal";
      const commentVal = commentInput?.value?.trim() || "";

      try {
        if (nameVal) localStorage.setItem("ligase_fb_name", nameVal);
        if (emailVal) localStorage.setItem("ligase_fb_email", emailVal);
      } catch {}

      const fd = new FormData();
      fd.append("name", nameVal);
      fd.append("email", emailVal);
      fd.append("category", catVal);
      fd.append("target_area", areaVal);
      fd.append("comment", commentVal);
      fd.append("page_url", window.location.href);
      fd.append("captions_json", JSON.stringify(fbState.attachments.map((a) => a.caption || "")));
      for (const att of fbState.attachments) {
        fd.append("files", att.file);
      }

      const origBtnText = submitBtn.textContent;
      submitBtn.disabled = true;
      submitBtn.textContent = "Uploading & Emailing Brief…";
      if (statusEl) {
        statusEl.textContent = "Saving to persistent storage & dispatching email…";
        statusEl.className = "fb-status-msg";
      }

      try {
        const resp = await fetch("/api/feedback", {
          method: "POST",
          headers: { "X-Ligase-Client-Id": CLIENT_ID },
          body: fd,
        });
        const resJson = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          throw new Error(resJson.detail || `HTTP ${resp.status}`);
        }

        revokeFbObjectUrls();
        fbState.attachments = [];
        renderFbAttachments();
        if (commentInput) {
          commentInput.value = "";
          commentInput.removeAttribute("aria-invalid");
          commentInput.classList.remove("user-invalid-fallback");
        }
        state.usageData = null;

        formEl.hidden = true;
        if (successBox && successDetail) {
          const attCount = Number(resJson.attachment_count || 0);
          const mailQueued = resJson.email_delivery?.queued || resJson.email_delivery?.sent;
          successDetail.textContent =
            `Record ${String(resJson.feedback_id || "").slice(0, 8)} saved durably` +
            (attCount ? ` with ${attCount} attached screenshot/figure file${attCount === 1 ? "" : "s"}` : "") +
            (mailQueued
              ? " and emailed with inline visual previews & engineering instructions."
              : " to persistent storage.");
          successBox.hidden = false;
          successBox.focus();
        }
        if (statusEl) statusEl.textContent = "";
        await loadWorkspaceRecentFeedback();
      } catch (err) {
        if (statusEl) {
          statusEl.textContent = err.message || "Failed to submit feedback.";
          statusEl.className = "fb-status-msg is-error";
        }
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = origBtnText;
      }
    });

    anotherBtn?.addEventListener("click", () => {
      if (successBox) successBox.hidden = true;
      formEl.hidden = false;
      if (statusEl) {
        statusEl.textContent = "";
        statusEl.className = "fb-status-msg";
      }
      commentInput?.focus();
    });
  }

  async function ensureFeedbackTabLoaded() {
    initFeedbackController();
    await Promise.all([loadShippedImprovements(), loadWorkspaceRecentFeedback()]);
  }

  // ── NIAGADS Bond Strip & Global Cmd/Ctrl+K Command Palette ────────────────
  const CMDK_LOCI = [
    { id: "v06_fm_bin1", group: "NIAGADS v0.6 Quantitative V2F Suite", title: "BIN1 — Wakefield ABF Fine-Mapping + FunGen-xQTL Coloc", sub: "95% FILER enhancer-weighted credible set + MiGA NG00105 microglia colocalization (PP.H4)", badge: "Coloc · BIN1", action: "finemap_coloc", target: "BIN1", flank: 50000 },
    { id: "v06_mr_prs", group: "NIAGADS v0.6 Quantitative V2F Suite", title: "Microglia Endolysosomal TwoSampleMR + 4-Ancestry NIAGADS PRS", sub: "IVW, MR-Egger pleiotropy intercept & Weighted Median + EUR/AFR/AMR/EAS PRS transferability", badge: "2SMR + PRS", action: "mr_prs", target: "microglia_endolysosomal", flank: 0 },
    { id: "v06_reg_rs", group: "NIAGADS v0.6 Quantitative V2F Suite", title: "rs6733839 — ADSP R5 + FILER Deep-Regulatory Score (0–100)", sub: "5-modality microglia ATAC, SPI1/MEF2C enhancer, FunGen eQTL & GA4GH VRS impact", badge: "0–100 V2F", action: "rare_regulatory", target: "rs6733839", flank: 0 },
    { id: "v06_aria_apoe", group: "NIAGADS v0.6 Quantitative V2F Suite", title: "APOE — ARIA-E/ARIA-H Safety & Live ClinicalTrials.gov v2", sub: "Anti-amyloid boxed-warning pharmacogenomics + disease-modifying ADRD trials", badge: "ARIA + NCT", action: "translational_trials", target: "APOE", flank: 0 },
    { id: "loc_bin1", group: "NIAGADS V2F Locus Dossiers", title: "BIN1 — 4-Way Parallel V2F Locus Dossier", sub: "2q14.3 microglia enhancer locus · GVC TopGene + GWAS + GRCh38 exons + FILER", badge: "Dossier · BIN1", action: "locus_dossier", target: "BIN1", flank: 10000 },
    { id: "loc_apoe", group: "NIAGADS V2F Locus Dossiers", title: "APOE — 4-Way Parallel V2F Locus Dossier", sub: "19q13.32 canonical AD locus · TopGenes + multi-ancestry GWAS + exons + FILER", badge: "Dossier · APOE", action: "locus_dossier", target: "APOE", flank: 10000 },
    { id: "loc_trem2", group: "NIAGADS V2F Locus Dossiers", title: "TREM2 — 4-Way Parallel V2F Locus Dossier", sub: "6p21.1 microglial receptor · exon architecture + GWAS + FILER", badge: "Dossier · TREM2", action: "locus_dossier", target: "TREM2", flank: 10000 },
    { id: "loc_abca7", group: "NIAGADS V2F Locus Dossiers", title: "ABCA7 — 4-Way Parallel V2F Locus Dossier", sub: "19p13.3 lipid transporter · African ancestry PAF enrichment + GWAS + exons", badge: "Dossier · ABCA7", action: "locus_dossier", target: "ABCA7", flank: 10000 },
    { id: "loc_sorl1", group: "NIAGADS V2F Locus Dossiers", title: "SORL1 — 4-Way Parallel V2F Locus Dossier", sub: "11q24.1 endosomal sorting receptor · coding & GWAS architecture", badge: "Dossier · SORL1", action: "locus_dossier", target: "SORL1", flank: 10000 },
    { id: "loc_rs6733839", group: "NIAGADS V2F Locus Dossiers", title: "rs6733839 — BIN1 Microglia Enhancer SNV Dossier", sub: "ADSP R5 VRS digest + GWAS p-values + +/-2.5 kb R5 SNVs + FILER SPI1/MEF2C", badge: "Dossier · SNV", action: "locus_dossier", target: "rs6733839", flank: 0 },
    { id: "loc_rs429358", group: "NIAGADS V2F Locus Dossiers", title: "rs429358 — APOE ε4 (Cys112Arg) Variant Dossier", sub: "chr19:44908684:T:C · GA4GH VRS + gnomAD/TOPMed AFs + GWAS", badge: "Dossier · SNV", action: "locus_dossier", target: "rs429358", flank: 0 },
    { id: "loc_rs7412", group: "NIAGADS V2F Locus Dossiers", title: "rs7412 — APOE ε2 (Arg158Cys) Variant Dossier", sub: "chr19:44908822:C:T · AD protective vs. PSP risk reversal", badge: "Dossier · SNV", action: "locus_dossier", target: "rs7412", flank: 0 },
    { id: "loc_batch_genes", group: "NIAGADS V2F Locus Dossiers", title: "AD 6-Gene Panel (APOE, BIN1, TREM2, ABCA7, SORL1, PLCG2)", sub: "Single-request NIAGADS Open Access v2.0 batch gene lookup", badge: "Batch ×6", action: "gene", target: "APOE,BIN1,TREM2,ABCA7,SORL1,PLCG2", flank: 0 },
  ];

  let cmdkInitialized = false;
  let cmdkActiveIndex = 0;
  let cmdkVisibleItems = [];

  function buildCmdkCatalogItems(queryRaw) {
    const q = (queryRaw || "").trim();
    const qLow = q.toLowerCase();
    const allItems = [];

    // Dynamic custom NIAGADS target when user types a gene, rsID, region, or NG* track
    if (q.length >= 2 && /^(rs\d+|chr[\w:,-]+|ng\d{5}\w*|ensg\d+|[a-z][a-z0-9-]{1,11})$/i.test(q)) {
      allItems.push({
        group: "Instant Live NIAGADS Lookup",
        title: `Run Live NIAGADS V2F Locus Dossier on "${q}"`,
        sub: "Parallel Open Access v2.0 record + GWAS signals + structure/variants + FILER overlap",
        badge: "Live API ↵",
        run: async () => {
          await switchPortalTab("niagads-api", { focusHeading: true });
          applyAndRunOaPreset("locus_dossier", q, "", 0);
        },
      });
      allItems.push({
        group: "Instant Live NIAGADS Lookup",
        title: `Synthesize "${q}" in Research Studio (${state.meta?.model || "gpt-6-luna"})`,
        sub: "Grounded AD1 study combining NIAGADS Open Access v2.0, multi-cohort panels & UniProt",
        badge: "Studio ↵",
        run: () => {
          launchPromptInStudio(
            `Run a quantitative NIAGADS V2F analysis on \`${q}\` using \`niagads_open_access_api\` (action='locus_dossier') and \`query_niagads\`, summarizing genetic risk, functional genomics, and cross-ancestry evidence.`,
            "niagads_api"
          );
        },
      });
    }

    for (const loc of CMDK_LOCI) {
      allItems.push({
        group: loc.group,
        title: loc.title,
        sub: loc.sub,
        badge: loc.badge,
        run: async () => {
          await switchPortalTab("niagads-api", { focusHeading: true });
          applyAndRunOaPreset(loc.action, loc.target, "", loc.flank);
        },
      });
    }

    // Portal Views & Actions
    const navItems = [
      { title: "Watch 1-Minute Grok-Narrated Video Tour (Ara & Rex)", sub: "60s 1080p showcase of NIAGADS Open Access v2.0, BIN1 94.6% PIP, ABCA7 8.7x PAF & PSP 56.8x shift", badge: "1:00 Video", run: () => focusAndPlayShowcaseVideo() },
      { title: "Open NIAGADS Bonded Ecosystem Shelf (5 Live Launchers)", sub: "Open Access v2.0 BIN1 dossier, GenomicsDB 6-gene batch, ADSP R5 VRS, FILER 58k+ & 24 NG* cohorts", badge: "NIAGADS", run: async () => { await switchPortalTab("studio", { focusHeading: false }); if (el.welcomeView?.hidden) el.newStudyBtn?.click(); switchStudioShelf("niagads"); } },
      { title: "Switch to Research Studio", sub: "Streaming gpt-6-luna co-scientist & grounded tool trace", badge: "Tab 1", run: () => switchPortalTab("studio", { focusHeading: true }) },
      { title: "Switch to Capabilities Mindmap", sub: "Interactive 6-pillar · 36-component SVG graph & accessible matrix", badge: "Tab 2", run: () => switchPortalTab("mindmap", { focusHeading: true }) },
      { title: "Switch to NIAGADS Open Access v2.0 Explorer", sub: "Interactive REST console + SVG genomics charts", badge: "Tab 3", run: () => switchPortalTab("niagads-api", { focusHeading: true }) },
      { title: "Switch to Usage & Volume Ledger", sub: "Persistent Cloud Storage telemetry, token volume & CSV/MD exports", badge: "Tab 4", run: () => switchPortalTab("usage", { focusHeading: true }) },
      { title: "Switch to Comments, Screenshots & Feedback", sub: "Paste screenshots (Cmd+V) & email structured engineering briefs", badge: "Tab 5", run: () => switchPortalTab("feedback", { focusHeading: true }) },
      { title: "Copy NIH/NIA NIAGADS Citation & BibTeX (U24AG041689)", sub: "Official NIAGADS Open Access v2.0 + Cooperative Agreement U24AG041689 attribution", badge: "Provenance", run: () => copyNiagadsCitation("Ligase Portal") },
      { title: "Open Full NIAGADS 24-Cohort & Tool Reference Catalog", sub: "Inspect NG00049–NG00182 datasets and 180+ Biomni modules", badge: "Catalog", run: async () => { await ensureFullMetaLoaded(); el.catalogDialog?.showModal(); } },
    ];
    for (const nav of navItems) {
      allItems.push({ group: "Portal Views & Provenance", ...nav });
    }

    // 24 NIAGADS NG* DSS Datasets (when hydrated)
    const datasets = state.meta?.niagads?.datasets || [];
    for (const ds of datasets) {
      allItems.push({
        group: "NIAGADS DSS Cohorts (NG00049–NG00182)",
        title: `${ds.id} — ${ds.title}`,
        sub: ds.description || "NIAGADS Data Sharing Service curated cohort",
        badge: ds.access === "open" ? "Open DSS" : "NIAGADS DSS",
        run: () => {
          launchPromptInStudio(
            `Summarize NIAGADS study \`${ds.id}\` (${ds.title}) using \`query_niagads\` and cross-reference any live open-access summary tracks on \`niagads_open_access_api\`.`,
            "niagads_api"
          );
        },
      });
    }

    if (!qLow) {
      return allItems.slice(0, 18);
    }
    return allItems
      .filter((item) => `${item.title} ${item.sub} ${item.badge} ${item.group}`.toLowerCase().includes(qLow))
      .slice(0, 24);
  }

  function renderCmdkList() {
    if (!el.cmdkResults) return;
    el.cmdkResults.replaceChildren();
    cmdkVisibleItems = buildCmdkCatalogItems(el.cmdkInput?.value || "");
    if (cmdkActiveIndex >= cmdkVisibleItems.length) cmdkActiveIndex = 0;

    if (!cmdkVisibleItems.length) {
      const empty = document.createElement("div");
      empty.className = "cmdk-empty";
      empty.textContent = "No matching genes, variants, NIAGADS cohorts, or actions found.";
      el.cmdkResults.appendChild(empty);
      return;
    }

    let currentGroup = "";
    cmdkVisibleItems.forEach((item, idx) => {
      if (item.group !== currentGroup) {
        currentGroup = item.group;
        const grp = document.createElement("div");
        grp.className = "cmdk-group-label";
        grp.textContent = currentGroup;
        el.cmdkResults.appendChild(grp);
      }

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "cmdk-item" + (idx === cmdkActiveIndex ? " active" : "");
      btn.setAttribute("role", "option");
      btn.setAttribute("aria-selected", idx === cmdkActiveIndex ? "true" : "false");

      const main = document.createElement("div");
      main.className = "cmdk-item-main";
      const t = document.createElement("span");
      t.className = "cmdk-item-title";
      t.textContent = item.title;
      const s = document.createElement("span");
      s.className = "cmdk-item-sub";
      s.textContent = item.sub;
      main.append(t, s);

      const b = document.createElement("span");
      b.className = "cmdk-item-badge";
      b.textContent = item.badge;

      btn.append(main, b);
      btn.addEventListener("mouseenter", () => {
        cmdkActiveIndex = idx;
        for (const [i, node] of Array.from(el.cmdkResults.querySelectorAll(".cmdk-item")).entries()) {
          node.classList.toggle("active", i === cmdkActiveIndex);
          node.setAttribute("aria-selected", i === cmdkActiveIndex ? "true" : "false");
        }
      });
      btn.addEventListener("click", () => {
        el.cmdkDialog?.close();
        item.run();
      });
      el.cmdkResults.appendChild(btn);
    });
  }

  async function openCommandPalette() {
    if (!el.cmdkDialog) return;
    ensureFullMetaLoaded().then(() => {
      if (el.cmdkDialog.open) renderCmdkList();
    });
    cmdkActiveIndex = 0;
    if (el.cmdkInput) el.cmdkInput.value = "";
    renderCmdkList();
    if (!el.cmdkDialog.open) {
      el.cmdkDialog.showModal();
    }
    requestAnimationFrame(() => el.cmdkInput?.focus());
  }

  function initBondAndCommandPalette() {
    if (cmdkInitialized) return;
    cmdkInitialized = true;

    el.openCmdkBtn?.addEventListener("click", openCommandPalette);
    el.heroOpenCmdkBtn?.addEventListener("click", openCommandPalette);
    el.copyNiagadsAckBtn?.addEventListener("click", () => copyNiagadsCitation("Ligase NIAGADS Bonded Portal"));

    for (const chip of document.querySelectorAll("[data-bond-action]")) {
      chip.addEventListener("click", async () => {
        const act = chip.dataset.bondAction || "locus_dossier";
        const tgt = chip.dataset.bondTarget || "BIN1";
        await switchPortalTab("niagads-api", { focusHeading: true });
        applyAndRunOaPreset(act, tgt, "", act === "locus_dossier" && tgt === "BIN1" ? 10000 : 0);
      });
    }

    for (const catChip of document.querySelectorAll("[data-bond-catalog]")) {
      catChip.addEventListener("click", async () => {
        await ensureFullMetaLoaded();
        el.catalogDialog?.showModal();
      });
    }

    el.cmdkInput?.addEventListener("input", () => {
      cmdkActiveIndex = 0;
      renderCmdkList();
    });

    el.cmdkInput?.addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowDown") {
        ev.preventDefault();
        if (cmdkVisibleItems.length) {
          cmdkActiveIndex = (cmdkActiveIndex + 1) % cmdkVisibleItems.length;
          renderCmdkList();
          el.cmdkResults?.querySelector(".cmdk-item.active")?.scrollIntoView({ block: "nearest" });
        }
      } else if (ev.key === "ArrowUp") {
        ev.preventDefault();
        if (cmdkVisibleItems.length) {
          cmdkActiveIndex = (cmdkActiveIndex - 1 + cmdkVisibleItems.length) % cmdkVisibleItems.length;
          renderCmdkList();
          el.cmdkResults?.querySelector(".cmdk-item.active")?.scrollIntoView({ block: "nearest" });
        }
      } else if (ev.key === "Enter") {
        ev.preventDefault();
        const chosen = cmdkVisibleItems[cmdkActiveIndex];
        if (chosen) {
          el.cmdkDialog?.close();
          chosen.run();
        }
      }
    });

    document.addEventListener("keydown", (ev) => {
      if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "k") {
        ev.preventDefault();
        if (el.cmdkDialog?.open) {
          el.cmdkDialog.close();
        } else {
          openCommandPalette();
        }
      }
    });
  }

  function hydrateDeferredMedia(media) {
    if (!media) return;
    let mutated = false;
    if (media.dataset.poster) {
      media.poster = media.dataset.poster;
      delete media.dataset.poster;
      mutated = true;
    }
    if (media.dataset.preload) {
      media.preload = media.dataset.preload;
      delete media.dataset.preload;
      mutated = true;
    }
    if (media.dataset.src) {
      media.src = media.dataset.src;
      delete media.dataset.src;
      mutated = true;
    }
    for (const source of media.querySelectorAll("source[data-src]")) {
      source.src = source.dataset.src;
      delete source.dataset.src;
      mutated = true;
    }
    if (mutated) {
      media.load();
    }
  }

  let activeStudioShelf = "studies";
  let allStudioShelvesExpanded = false;

  function switchStudioShelf(targetName = "studies") {
    const shelf = document.getElementById("studio-home-shelf");
    if (!shelf) return;
    activeStudioShelf = targetName;
    allStudioShelvesExpanded = false;

    const expandBtn = document.getElementById("shelf-expand-all-btn");
    if (expandBtn) {
      expandBtn.setAttribute("aria-pressed", "false");
      expandBtn.textContent = "⊞ Show All";
    }

    for (const pane of shelf.querySelectorAll(".studio-shelf-pane[data-shelf-pane]")) {
      if (pane.dataset.shelfPane === targetName) {
        pane.removeAttribute("hidden");
      } else {
        pane.setAttribute("hidden", "until-found");
      }
    }

    for (const btn of shelf.querySelectorAll(".studio-shelf-btn[data-shelf-target]")) {
      const isMatch = btn.dataset.shelfTarget === targetName;
      btn.classList.toggle("active", isMatch);
      btn.setAttribute("aria-expanded", isMatch ? "true" : "false");
    }

    const video = document.getElementById("ligase-showcase-video");
    if (video) {
      if (targetName === "video") {
        hydrateDeferredMedia(video);
        if (video.preload === "none") {
          video.preload = "metadata";
        }
      } else if (!video.paused) {
        video.pause();
      }
    }
  }

  function setAllStudioShelvesExpanded(expanded) {
    const shelf = document.getElementById("studio-home-shelf");
    if (!shelf) return;
    if (!expanded) {
      switchStudioShelf(activeStudioShelf || "studies");
      return;
    }
    allStudioShelvesExpanded = true;
    const expandBtn = document.getElementById("shelf-expand-all-btn");
    if (expandBtn) {
      expandBtn.setAttribute("aria-pressed", "true");
      expandBtn.textContent = "⊟ Compact View";
    }
    for (const pane of shelf.querySelectorAll(".studio-shelf-pane[data-shelf-pane]")) {
      pane.removeAttribute("hidden");
    }
    for (const btn of shelf.querySelectorAll(".studio-shelf-btn[data-shelf-target]")) {
      btn.classList.add("active");
      btn.setAttribute("aria-expanded", "true");
    }
    const video = document.getElementById("ligase-showcase-video");
    if (video) hydrateDeferredMedia(video);
  }

  function initStudioHomeShelf() {
    const shelf = document.getElementById("studio-home-shelf");
    if (!shelf) return;

    for (const btn of shelf.querySelectorAll(".studio-shelf-btn[data-shelf-target]")) {
      btn.addEventListener("click", () => {
        switchStudioShelf(btn.dataset.shelfTarget || "studies");
      });
    }

    const expandBtn = document.getElementById("shelf-expand-all-btn");
    expandBtn?.addEventListener("click", () => {
      setAllStudioShelvesExpanded(!allStudioShelvesExpanded);
    });

    // Fallback for browsers without hidden="until-found" / onbeforematch support (e.g. Safari) per modern-web-guidance
    if (!("onbeforematch" in HTMLElement.prototype)) {
      setAllStudioShelvesExpanded(true);
      return;
    }

    // Synchronize mutually exclusive shelf panes & ARIA state on browser Find-in-Page (search-hidden-content)
    shelf.addEventListener("beforematch", (ev) => {
      const matchedPane =
        ev.target instanceof Element ? ev.target.closest(".studio-shelf-pane[data-shelf-pane]") : null;
      if (!matchedPane) return;
      const matchedName = matchedPane.dataset.shelfPane || "studies";
      activeStudioShelf = matchedName;
      allStudioShelvesExpanded = false;
      if (expandBtn) {
        expandBtn.setAttribute("aria-pressed", "false");
        expandBtn.textContent = "⊞ Show All";
      }
      for (const pane of shelf.querySelectorAll(".studio-shelf-pane[data-shelf-pane]")) {
        if (pane !== matchedPane) {
          pane.setAttribute("hidden", "until-found");
        }
      }
      for (const btn of shelf.querySelectorAll(".studio-shelf-btn[data-shelf-target]")) {
        const controls = btn.getAttribute("aria-controls");
        const isMatch = controls === matchedPane.id;
        btn.classList.toggle("active", isMatch);
        btn.setAttribute("aria-expanded", isMatch ? "true" : "false");
      }
      if (matchedName === "video") {
        hydrateDeferredMedia(document.getElementById("ligase-showcase-video"));
      }
    });
  }

  async function focusAndPlayShowcaseVideo(seekTimeSec = null) {
    if (state.activeTab !== "studio") {
      await switchPortalTab("studio", { focusHeading: false });
    }
    if (el.welcomeView?.hidden) {
      el.newStudyBtn?.click();
    }
    switchStudioShelf("video");
    const card = document.getElementById("video-showcase-card");
    const video = document.getElementById("ligase-showcase-video");
    if (!video) return;

    hydrateDeferredMedia(video);
    if (video.preload === "none") {
      video.preload = "metadata";
    }
    card?.scrollIntoView({ behavior: "smooth", block: "center" });

    if (typeof seekTimeSec === "number" && Number.isFinite(seekTimeSec)) {
      const applySeek = () => {
        try {
          video.currentTime = seekTimeSec;
        } catch {
          /* wait for metadata */
        }
      };
      if (video.readyState >= 1) {
        applySeek();
      } else {
        video.addEventListener("loadedmetadata", applySeek, { once: true });
      }
    }

    try {
      await video.play();
    } catch {
      video.focus();
    }
  }

  function initShowcaseVideo() {
    const video = document.getElementById("ligase-showcase-video");
    const card = document.getElementById("video-showcase-card");
    const heroBtn = document.getElementById("hero-watch-video-btn");
    const playToggleBtn = document.getElementById("video-play-toggle-btn");
    const wideToggleBtn = document.getElementById("video-wide-toggle-btn");
    const chapterBtns = Array.from(document.querySelectorAll(".video-chapter-btn[data-video-seek]"));

    if (!video) return;

    // Cross-browser lazy-media fallback per modern-web-guidance (Firefox & Safari lack HTMLMediaElement.prototype.loading)
    const supportsLazyMedia =
      typeof HTMLMediaElement !== "undefined" && Object.hasOwn(HTMLMediaElement.prototype, "loading");
    if (!supportsLazyMedia && typeof IntersectionObserver !== "undefined") {
      const lazyMediaElements = document.querySelectorAll('video[loading="lazy"], audio[loading="lazy"][controls]');
      const mediaObserver = new IntersectionObserver(
        (entries, observer) => {
          for (const entry of entries) {
            if (!entry.isIntersecting) continue;
            hydrateDeferredMedia(entry.target);
            observer.unobserve(entry.target);
          }
        },
        { rootMargin: "200px 0px" }
      );
      for (const media of lazyMediaElements) {
        if (media.hasAttribute("poster")) {
          media.dataset.poster = media.getAttribute("poster");
          media.removeAttribute("poster");
        }
        if (media.hasAttribute("preload") && media.getAttribute("preload") !== "none") {
          media.dataset.preload = media.getAttribute("preload");
        }
        media.preload = "none";
        mediaObserver.observe(media);
      }
    }

    // Honor prefers-reduced-motion on any autoplaying motion media
    if (typeof window.matchMedia === "function") {
      const reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
      const syncReducedMotion = (prefersReduced) => {
        for (const v of document.querySelectorAll("video[autoplay]")) {
          if (prefersReduced) {
            v.removeAttribute("autoplay");
            v.pause();
          }
        }
      };
      syncReducedMotion(reducedMotionQuery.matches);
      reducedMotionQuery.addEventListener?.("change", (ev) => syncReducedMotion(ev.matches));
    }

    heroBtn?.addEventListener("click", () => focusAndPlayShowcaseVideo());

    playToggleBtn?.addEventListener("click", async () => {
      hydrateDeferredMedia(video);
      if (video.paused) {
        try {
          await video.play();
        } catch {
          video.focus();
        }
      } else {
        video.pause();
      }
    });

    const syncPlayLabel = () => {
      if (!playToggleBtn) return;
      playToggleBtn.textContent = video.paused ? "▶ Play 1-Min Tour" : "⏸ Pause Tour";
    };
    video.addEventListener("play", syncPlayLabel);
    video.addEventListener("pause", syncPlayLabel);
    video.addEventListener("ended", syncPlayLabel);

    wideToggleBtn?.addEventListener("click", () => {
      if (!card) return;
      const expanded = card.classList.toggle("is-wide");
      wideToggleBtn.setAttribute("aria-pressed", expanded ? "true" : "false");
      wideToggleBtn.textContent = expanded ? "🗗 Standard View" : "⛶ Wide View";
    });

    for (const btn of chapterBtns) {
      btn.addEventListener("click", () => {
        const sec = parseFloat(btn.dataset.videoSeek || "0");
        for (const b of chapterBtns) b.classList.toggle("active", b === btn);
        focusAndPlayShowcaseVideo(sec);
      });
    }

    video.addEventListener("timeupdate", () => {
      const t = video.currentTime || 0;
      for (const btn of chapterBtns) {
        const s = parseFloat(btn.dataset.videoSeek || "0");
        const e = parseFloat(btn.dataset.videoEnd || "999");
        btn.classList.toggle("active", t >= s - 0.15 && t < e);
      }
    });

    // Pause video cleanly if user switches to another portal tab
    el.portalTablist?.addEventListener("click", () => {
      if (state.activeTab !== "studio" && !video.paused) {
        video.pause();
      }
    });
  }

  // ── Batch VCF / Variant List V2F Annotator & AD-V2F-Bench Runner ──────────
  function initBatchVcfAndBenchmark() {
    const runBtn = document.getElementById("niagads-vcf-run-btn");
    const csvBtn = document.getElementById("niagads-vcf-csv-btn");
    const benchBtn = document.getElementById("niagads-bench-btn");
    const vcfInput = document.getElementById("niagads-vcf-input");
    const outBox = document.getElementById("niagads-vcf-output");
    let lastCsv = "";

    runBtn?.addEventListener("click", async () => {
      const vcfText = (vcfInput?.value || "").trim();
      if (!vcfText) return;
      const orig = runBtn.textContent;
      runBtn.disabled = true;
      runBtn.textContent = "Annotating via NIAGADS Open Access v2.0…";
      if (outBox) {
        outBox.hidden = false;
        outBox.innerHTML = `<p style="color:var(--text-muted)">Prioritizing variants across NIAGADS ADSP R5 VRS + FILER hg38…</p>`;
      }
      try {
        const resp = await fetch("/api/niagads/vcf-annotate", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Ligase-Client-Id": CLIENT_ID,
          },
          body: JSON.stringify({ vcf_text: vcfText }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || !data.ok) {
          throw new Error(data.summary_markdown || data.detail || `HTTP ${resp.status}`);
        }
        lastCsv = data.csv || "";
        if (csvBtn) csvBtn.hidden = !lastCsv;
        if (outBox) outBox.innerHTML = renderMarkdown(data.summary_markdown || "");
      } catch (err) {
        if (outBox) {
          outBox.innerHTML = `<p style="color:var(--danger)"><strong>Batch V2F error:</strong> ${escapeHtml(err.message)}</p>`;
        }
      } finally {
        runBtn.disabled = false;
        runBtn.textContent = orig;
      }
    });

    csvBtn?.addEventListener("click", () => {
      if (!lastCsv) return;
      const blob = new Blob([lastCsv], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "niagads_v2f_prioritized_callset.csv";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });

    benchBtn?.addEventListener("click", async () => {
      const orig = benchBtn.textContent;
      benchBtn.disabled = true;
      benchBtn.textContent = "Evaluating AD-HeurekaBench v0.8…";
      try {
        const b = await apiFetch("/api/niagads/benchmark");
        const rowsMd = (b.results || [])
          .map(
            (r) =>
              `| \`${r.locus}\` | **${r.gold_gene}** | \`${r.gold_variant}\` | \`${r.predicted_lead}\` (${r.top1_match ? "✓" : "✗"}) | **${(r.top_pip_filer * 100).toFixed(1)}%** | **${(r.coloc_pp_h4 * 100).toFixed(1)}%** | ${r.latency_ms} ms |`
          )
          .join("\n");
        const wfRowsMd = (b.workflows || [])
          .map(
            (w) =>
              `| \`${w.workflow_id}\` | ${w.title || w.paper_anchor || "Grounded workflow"} | ${w.passed ? "✓ PASS" : "✗ FAIL"} | \`${w.metric}\` |`
          )
          .join("\n");
        const wfBlock = wfRowsMd
          ? [
              "",
              `#### Multi-Step Translational Workflows (\`${b.multi_step_workflows_evaluated || 0}\` evaluated · Pass Rate: **${((b.workflow_pass_rate || 0) * 100).toFixed(1)}%**)`,
              "",
              "| Workflow ID | Grounded Task | Status | Verified Quantitative Readout |",
              "|---|---|---:|---|",
              wfRowsMd,
            ]
          : [];
        const md = [
          `### 🏆 ${b.benchmark} — Top-1 Causal Recall: **${(b.top1_causal_variant_accuracy * 100).toFixed(1)}%** · Mean Coloc \`PP.H4\`: **${(b.mean_coloc_pp_h4 * 100).toFixed(1)}%**`,
          "",
          "| Locus | GVC Gold Gene | Gold Causal Variant | Predicted Top PIP | FILER PIP | FunGen `PP.H4` | Compute |",
          "|---|---|---|---|---:|---:|---:|",
          rowsMd,
          ...wfBlock,
        ].join("\n");
        if (outBox) {
          outBox.hidden = false;
          outBox.innerHTML = renderMarkdown(md);
        }
      } catch (err) {
        showToast(`Benchmark error: ${err.message}`);
      } finally {
        benchBtn.disabled = false;
        benchBtn.textContent = orig;
      }
    });

    // Interactive ADSP Release 5 (58,507 WGS) Power Planner & NIH DAR / Specific-Aims Co-Pilot
    const darRunBtn = document.getElementById("niagads-dar-run-btn");
    const darMdBtn = document.getElementById("niagads-dar-md-btn");
    const darCsvBtn = document.getElementById("niagads-dar-csv-btn");
    const darTargetInput = document.getElementById("dar-target-input");
    const darModeSelect = document.getElementById("dar-mode-select");
    const darDomainSelect = document.getElementById("dar-domain-select");
    const darEffectInput = document.getElementById("dar-effect-input");
    const darMafInput = document.getElementById("dar-maf-input");
    let lastDarMd = "";
    let lastDarCsv = "";
    let lastDarTarget = "ABCA7";

    darRunBtn?.addEventListener("click", async () => {
      const target = (darTargetInput?.value || "ABCA7").trim() || "ABCA7";
      const testMode = darModeSelect?.value || "staar_o_burden";
      const domain = darDomainSelect?.value || "case_control_ad";
      const effectSize = Number(darEffectInput?.value || 0);
      const customMaf = Number(darMafInput?.value || 0);

      const orig = darRunBtn.textContent;
      darRunBtn.disabled = true;
      darRunBtn.textContent = "Computing ADSP R5 Power & Drafting NIH DAR…";
      el.oaResultCard.hidden = false;
      el.oaResultMeta.innerHTML = `<span class="spinner" aria-hidden="true"></span><span>Computing ADSP Release 5 (58,507 WGS) power &amp; NIH DAR packet…</span>`;

      try {
        const resp = await fetch("/api/niagads/power-dar", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Ligase-Client-Id": CLIENT_ID,
          },
          body: JSON.stringify({
            target,
            test_mode: testMode,
            phenotype_domain: domain,
            effect_size: effectSize,
            custom_maf: customMaf,
          }),
        });
        const res = await resp.json().catch(() => ({}));
        if (!resp.ok || !res.ok) {
          throw new Error(res.summary_markdown || res.detail || `HTTP ${resp.status}`);
        }
        lastDarTarget = target;
        lastDarMd = res.dar_specific_aims_markdown || res.summary_markdown || "";
        lastDarCsv = res.csv || "";
        if (darMdBtn) darMdBtn.hidden = !lastDarMd;
        if (darCsvBtn) darCsvBtn.hidden = !lastDarCsv;

        state.lastOaResult = {
          action: "adsp_r5_power_dar",
          target,
          loc: `${testMode}|${domain}|${effectSize || ""}`,
          flank: 0,
          ...res,
        };
        el.oaResultMeta.innerHTML = `
          <span class="oa-status-pill">✓ HTTP 200 OK · ${escapeHtml(res.elapsed_ms)} ms</span>
          <span>Endpoint: <code>${escapeHtml(res.endpoint)}</code></span>
        `;
        renderOaEcosystemAndVisuals(res);
        el.oaResultMarkdown.innerHTML = renderMarkdown(res.summary_markdown || "");
        el.oaResultJson.textContent = JSON.stringify(res.raw, null, 2);
        state.usageData = null;
      } catch (err) {
        showToast(`Power/DAR error: ${err.message}`);
      } finally {
        darRunBtn.disabled = false;
        darRunBtn.textContent = orig;
      }
    });

    darMdBtn?.addEventListener("click", () => {
      if (!lastDarMd) return;
      const blob = new Blob([lastDarMd], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `niagads_adsp_r5_dar_specific_aims_${lastDarTarget.replace(/[^a-zA-Z0-9_-]/g, "_")}.md`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });

    darCsvBtn?.addEventListener("click", () => {
      if (!lastDarCsv) return;
      const blob = new Blob([lastDarCsv], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `niagads_adsp_r5_power_${lastDarTarget.replace(/[^a-zA-Z0-9_-]/g, "_")}.csv`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }

  // ── Shareable Read-Only NIAGADS Study Permalink Loader (?study=run_...) ───
  async function loadSharedPermalinkIfPresent() {
    let studyId = "";
    try {
      studyId = (new URLSearchParams(window.location.search).get("study") || "").trim();
    } catch {}
    if (!studyId) return false;
    try {
      const shared = await apiFetch(`/api/shared/${encodeURIComponent(studyId)}`);
      if (!shared?.ok) return false;
      await switchPortalTab("studio", { updateHash: false });
      showWelcomeOrTranscript(true);
      el.transcript.innerHTML = "";

      const banner = document.createElement("div");
      banner.className = "shared-permalink-banner";
      banner.innerHTML = `
        <span>🔗 <strong>Shared NIAGADS Study Permalink</strong> · <code>${escapeHtml(shared.run_id)}</code> · NIH/NIA U24AG041689 Grounded</span>
        <a class="artifact-btn" href="${escapeHtml(shared.notebook_url)}" download>📓 Download Reproducible .ipynb</a>
      `;
      el.transcript.appendChild(banner);
      appendUserBubble(shared.prompt || "");
      appendCompletedAssistantCard(shared.answer || "", shared);
      return true;
    } catch {
      return false;
    }
  }

  // ── Browser WebMCP Tool Registration (document.modelContext) ──────────────
  let webMcpController = null;
  async function registerNiagadsWebMcpTools() {
    if (typeof document === "undefined" || !("modelContext" in document) || !document.modelContext?.registerTool) {
      return;
    }
    webMcpController?.abort();
    webMcpController = new AbortController();
    const { signal: regSignal } = webMcpController;

    const tools = [
      {
        name: "run_niagads_finemap_coloc",
        description:
          "Runs NIAGADS Wakefield ABF fine-mapping, FILER enhancer-weighted 95% credible sets, and FunGen-xQTL Bayesian colocalization on an Alzheimer's gene or variant and displays the multi-track LocusZoom plot.",
        inputSchema: {
          type: "object",
          properties: {
            target: {
              type: "string",
              description: "Gene symbol or variant identifier to fine-map and colocalize.",
            },
          },
          required: ["target"],
        },
        async execute(input, { signal }) {
          const target = typeof input?.target === "string" ? input.target.trim() : "";
          if (!target) {
            return { error: "Provide a non-empty gene symbol or variant identifier." };
          }
          try {
            const qs = new URLSearchParams({ action: "finemap_coloc", target, flank: "50000" });
            const resp = await fetch(`/api/niagads/live?${qs.toString()}`, {
              headers: { "X-Ligase-Client-Id": CLIENT_ID },
              signal,
            });
            if (!resp.ok) {
              return { error: `NIAGADS fine-mapping request failed with status ${resp.status}.` };
            }
            const data = await resp.json();
            await switchPortalTab("niagads-api", { updateHash: false });
            el.oaResultCard.hidden = false;
            renderOaEcosystemAndVisuals(data);
            el.oaResultMarkdown.innerHTML = renderMarkdown(data.summary_markdown || "");
            return {
              endpoint: data.endpoint,
              coloc: data.raw?.coloc || {},
              credibleSet95: data.visual?.locuszoom?.credible_set_95 || [],
              summaryMarkdown: data.summary_markdown,
            };
          } catch (err) {
            if (signal?.aborted) {
              throw err;
            }
            return { error: err instanceof Error ? err.message : String(err) };
          }
        },
        annotations: { readOnlyHint: true },
      },
      {
        name: "run_niagads_translational_trials",
        description:
          "Retrieves NIAGADS locus pharmacology, APOE ARIA-E/ARIA-H anti-amyloid safety stratification, and live ClinicalTrials.gov Alzheimer's studies.",
        inputSchema: {
          type: "object",
          properties: {
            target: {
              type: "string",
              default: "APOE",
              description: "Target Alzheimer's risk gene symbol.",
            },
          },
          required: ["target"],
        },
        async execute(input, { signal }) {
          const target = typeof input?.target === "string" && input.target.trim() ? input.target.trim() : "APOE";
          try {
            const qs = new URLSearchParams({ action: "translational_trials", target });
            const resp = await fetch(`/api/niagads/live?${qs.toString()}`, {
              headers: { "X-Ligase-Client-Id": CLIENT_ID },
              signal,
            });
            if (!resp.ok) {
              return { error: `Translational trials query failed with status ${resp.status}.` };
            }
            const data = await resp.json();
            return {
              gene: data.raw?.gene || target,
              ariaSafety: data.raw?.translational?.aria_safety || "",
              trials: data.rows || [],
              summaryMarkdown: data.summary_markdown,
            };
          } catch (err) {
            if (signal?.aborted) {
              throw err;
            }
            return { error: err instanceof Error ? err.message : String(err) };
          }
        },
        annotations: { readOnlyHint: true },
      },
      {
        name: "run_niagads_adsp_r5_power_dar",
        description:
          "Computes ancestry-stratified statistical power across ADSP Release 5 (58,507 WGS / 57,302 subjects) and ADSP-PHC domains, selects NG* datasets, and drafts a NIAGADS DARM Data Access Request + NIH R01/R21 Specific Aims packet.",
        inputSchema: {
          type: "object",
          properties: {
            target: { type: "string", default: "ABCA7", description: "Target Alzheimer's gene or variant." },
            test_mode: { type: "string", default: "staar_o_burden", description: "staar_o_burden | single_variant | endophenotype_qtl" },
            phenotype_domain: { type: "string", default: "case_control_ad", description: "ADSP-PHC phenotype domain" },
          },
          required: ["target"],
        },
        async execute(input, { signal }) {
          const target = typeof input?.target === "string" && input.target.trim() ? input.target.trim() : "ABCA7";
          const test_mode = typeof input?.test_mode === "string" ? input.test_mode : "staar_o_burden";
          const phenotype_domain = typeof input?.phenotype_domain === "string" ? input.phenotype_domain : "case_control_ad";
          try {
            const resp = await fetch("/api/niagads/power-dar", {
              method: "POST",
              headers: { "Content-Type": "application/json", "X-Ligase-Client-Id": CLIENT_ID },
              body: JSON.stringify({ target, test_mode, phenotype_domain }),
              signal,
            });
            if (!resp.ok) return { error: `Power/DAR query failed with status ${resp.status}.` };
            const data = await resp.json();
            return {
              gene: data.raw?.gene || target,
              strata: data.rows || [],
              darMarkdown: data.dar_specific_aims_markdown || "",
            };
          } catch (err) {
            if (signal?.aborted) throw err;
            return { error: err instanceof Error ? err.message : String(err) };
          }
        },
        annotations: { readOnlyHint: true },
      },
    ];

    for (const toolDef of tools) {
      try {
        await document.modelContext.registerTool(toolDef, { signal: regSignal });
      } catch {
        /* ignore duplicate or unsupported registration errors */
      }
    }
  }

  async function boot() {
    syncThemeButtons();
    syncWorkflowHint();
    syncUsageExportLinks();
    initFeedbackController();
    initBondAndCommandPalette();
    initStudioHomeShelf();
    initShowcaseVideo();
    initBatchVcfAndBenchmark();
    registerNiagadsWebMcpTools();

    const bootstrap = readServerBootstrap();
    if (bootstrap?.mindmap) {
      state.mindmap = bootstrap.mindmap;
    }
    if (bootstrap?.boot) {
      applyMetaState(bootstrap.boot, { full: false });
    } else if (bootstrap?.meta) {
      applyMetaState(bootstrap.meta, { full: true });
    } else {
      try {
        const meta = await apiFetch("/api/meta");
        applyMetaState(meta, { full: true });
      } catch (err) {
        el.statusDot.classList.add("offline");
        el.diagnosticsSummary.textContent = `Could not reach backend: ${err.message}`;
      }
    }

    // Honor initial pathname (/usage, /admin, /feedback, /comments) or URL hash
    const pathLower = (window.location.pathname || "").toLowerCase();
    const hashTab = (window.location.hash || "").replace(/^#/, "").trim();
    if (pathLower === "/usage" || pathLower === "/admin" || hashTab === "usage") {
      switchPortalTab("usage", { updateHash: false });
    } else if (pathLower === "/feedback" || pathLower === "/comments" || hashTab === "feedback" || hashTab === "comments") {
      switchPortalTab("feedback", { updateHash: false });
    } else if (hashTab === "mindmap" || hashTab === "niagads-api") {
      switchPortalTab(hashTab, { updateHash: false });
    } else if (hashTab === "video" || hashTab === "shelf-video") {
      switchStudioShelf("video");
    } else if (hashTab === "shelf-niagads" || hashTab === "niagads") {
      switchStudioShelf("niagads");
    }

    // Fetch saved study threads, check ?study= permalink, and warm secondary tab payloads at low priority
    loadSharedPermalinkIfPresent();
    refreshThreads();
    scheduleIdlePrefetch();
  }

  boot();
})();
