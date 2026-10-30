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
  };

  const OA_PRESETS = [
    { label: "🧬 APOE Gene + GVC TopGenes", action: "gene", target: "APOE", loc: "", flank: 0 },
    { label: "⚡ rs6733839 Auto (ADSP R5 + GWAS + FILER)", action: "auto", target: "rs6733839", loc: "", flank: 0 },
    { label: "🧪 rs429358 ADSP R5 & GA4GH VRS", action: "variant", target: "rs429358", loc: "", flank: 0 },
    { label: "📐 TREM2 Exon Structure", action: "gene_structure", target: "TREM2", loc: "", flank: 0 },
    { label: "📊 BIN1 GWAS Associations", action: "gene_associations", target: "BIN1", loc: "", flank: 0 },
    { label: "🗺️ APOE Locus ADSP R5 Variants", action: "region_variants", target: "chr19:44908500-44909000", loc: "", flank: 0 },
    { label: "🎯 Track Slice: NG00166 @ BIN1", action: "track_data", target: "NG00166_04BE648F_STD_OA", loc: "chr2:127134000-127136000", flank: 0 },
    { label: "🔎 Search Tracks: African American", action: "search_tracks", target: "African American", loc: "", flank: 0 },
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
    mode: "direct", // "direct" | "plan"
    maxIterations: 10,
    pendingUploads: [], // [{name, token, size_bytes}]
    activeRunId: null,
    abortController: null,
    // Mindmap & Explorer render flags
    mmRendered: false,
    oaRendered: false,
    mmFilterPillar: "all",
    mmSearch: "",
    mmViewMode: "graph", // "graph" | "table"
    mmZoom: 1.0,
    mmCollapsed: new Set(),
    mmSelectedId: "mm_oa_variants",
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
    studioModeGroup: document.getElementById("studio-mode-group"),
    profileAd1Btn: document.getElementById("profile-ad1-btn"),
    profileA1Btn: document.getElementById("profile-a1-btn"),
    modeDirectBtn: document.getElementById("mode-direct-btn"),
    modePlanBtn: document.getElementById("mode-plan-btn"),
    statusDot: document.getElementById("status-dot"),
    modelBadgeText: document.getElementById("model-badge-text"),
    panelStudio: document.getElementById("panel-studio"),
    panelMindmap: document.getElementById("panel-mindmap"),
    panelNiagadsApi: document.getElementById("panel-niagads-api"),
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
    oaResultMarkdown: document.getElementById("oa-result-markdown"),
    oaResultJson: document.getElementById("oa-result-json"),
    oaSendStudioBtn: document.getElementById("oa-send-studio-btn"),
    oaCopyJsonBtn: document.getElementById("oa-copy-json-btn"),
    oaEndpointsTbody: document.getElementById("oa-endpoints-tbody"),
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
    m = m.replace(/\\([A-Za-z]+)/g, (full, cmd) => GREEK_MAP[cmd] || cmd);
    m = m.replace(/\\([%&_# ])/g, (_, ch) => (ch === " " ? "\u00a0" : ch));
    m = m.replace(/_\{([^{}]+)\}/g, "<sub>$1</sub>");
    m = m.replace(/\^\{([^{}]+)\}/g, "<sup>$1</sup>");
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
    s = s.replace(/\\\((.+?)\\\)|\$(?!\s)([^$\n]+?)(?<!\s)\$/g, (full, p1, p2) => {
      const expr = p1 ?? p2 ?? "";
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
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
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

  // ── Accessible Multi-Tab Navigation ───────────────────────────────────────
  async function switchPortalTab(tabId, { focusTab = false, updateHash = true } = {}) {
    const valid = tabId === "mindmap" || tabId === "niagads-api" ? tabId : "studio";
    state.activeTab = valid;

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

    // Studio-specific topbar segmented switches
    const isStudio = valid === "studio";
    el.studioProfileGroup.hidden = !isStudio;
    el.studioModeGroup.hidden = !isStudio;

    // Sidebar view shortcut active highlight
    for (const sc of document.querySelectorAll("[data-goto-tab]")) {
      if (sc.classList.contains("ghost-footer-btn")) {
        sc.classList.toggle("active", sc.dataset.gotoTab === valid);
      }
    }

    document.title = TAB_TITLES[valid] || TAB_TITLES.studio;
    if (updateHash) {
      try {
        history.replaceState(null, "", valid === "studio" ? window.location.pathname : `#${valid}`);
      } catch {}
    }
    el.sidebar.classList.remove("open");

    if (valid === "mindmap") {
      await ensureMindmapLoaded();
      requestAnimationFrame(() => drawMindmapConnectors());
    } else if (valid === "niagads-api") {
      await ensureOaCatalogLoaded();
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
      switchPortalTab(gotoBtn.dataset.gotoTab);
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

  function applyAndRunOaPreset(action, target, loc = "", flank = 0) {
    el.oaActionSelect.value = action;
    el.oaTargetInput.value = target;
    el.oaLocInput.value = loc;
    el.oaFlankInput.value = String(flank || 0);
    runLiveNiagadsQuery();
  }

  async function runLiveNiagadsQuery() {
    const action = el.oaActionSelect.value;
    const target = el.oaTargetInput.value.trim();
    const loc = el.oaLocInput.value.trim();
    const flank = Number(el.oaFlankInput.value || 0);
    if (!target && !loc) return;

    el.oaSubmitBtn.disabled = true;
    el.oaSubmitBtn.textContent = "Querying api.niagads.org…";
    el.oaResultCard.hidden = false;
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
      el.oaResultMarkdown.innerHTML = renderMarkdown(res.summary_markdown || "");
      el.oaResultJson.textContent = JSON.stringify(res.raw, null, 2);
    } catch (err) {
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

  function setMode(mode) {
    state.mode = mode === "plan" ? "plan" : "direct";
    el.modeDirectBtn.classList.toggle("active", state.mode === "direct");
    el.modePlanBtn.classList.toggle("active", state.mode === "plan");
    el.workflowHint.textContent =
      state.mode === "plan"
        ? "Plan-then-Approve · review & edit numbered methodology before tools execute"
        : "Direct execution · live NIAGADS API + tool trace & downloadable Markdown report";
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

    if (meta.report_url) {
      const repLink = document.createElement("a");
      repLink.className = "artifact-btn";
      repLink.href = meta.report_url;
      repLink.download = "";
      repLink.textContent = "⬇ Download report.md";
      bar.appendChild(repLink);
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
            statusRight.textContent = `${payload.elapsed_s}s · ${payload.iterations} round${payload.iterations === 1 ? "" : "s"} · ${toolCount} tool call${toolCount === 1 ? "" : "s"}`;
            card.appendChild(buildArtifactBar(finalMd, payload));
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

  // ── Dialog Controls & Light-Dismiss Fallback ──────────────────────────────
  el.openCatalogBtn.addEventListener("click", () => el.catalogDialog.showModal());
  el.inspectCatalogInline.addEventListener("click", () => el.catalogDialog.showModal());
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
  el.modeDirectBtn.addEventListener("click", () => setMode("direct"));
  el.modePlanBtn.addEventListener("click", () => setMode("plan"));
  el.newStudyBtn.addEventListener("click", startFreshStudy);
  el.openSidebarBtn.addEventListener("click", () => el.sidebar.classList.add("open"));
  el.closeSidebarBtn.addEventListener("click", () => el.sidebar.classList.remove("open"));
  el.maxIterSelect.addEventListener("change", () => {
    state.maxIterations = Number(el.maxIterSelect.value) || 10;
  });

  // ── Boot (Zero-Waterfall SSR Hydration + Low-Priority Background Sync) ────
  function readServerBootstrap() {
    const node = document.getElementById("ligase-bootstrap");
    if (!node || !node.textContent) return null;
    try {
      return JSON.parse(node.textContent);
    } catch {
      return null;
    }
  }

  function applyMetaState(meta) {
    state.meta = meta;
    if (meta.niagads?.open_access) {
      state.oaCatalog = meta.niagads.open_access;
    }
    el.appVersion.textContent = `v${meta.version}`;
    el.modelBadgeText.textContent = meta.model;
    el.statusDot.classList.toggle("offline", !meta.ready);
    el.diagnosticsSummary.textContent = `Model: ${meta.model} · Engine: Ligase v${meta.version} · Sandbox: ${meta.sandbox_mode} · Ready: ${meta.ready ? "Yes" : "Missing API Key"}`;
    renderStarters();
    renderCatalogDialog();
  }

  async function boot() {
    syncThemeButtons();
    const bootstrap = readServerBootstrap();
    if (bootstrap?.mindmap) {
      state.mindmap = bootstrap.mindmap;
    }
    if (bootstrap?.meta) {
      applyMetaState(bootstrap.meta);
    } else {
      try {
        const meta = await apiFetch("/api/meta");
        applyMetaState(meta);
      } catch (err) {
        el.statusDot.classList.add("offline");
        el.diagnosticsSummary.textContent = `Could not reach backend: ${err.message}`;
      }
    }

    // Honor initial URL hash (#mindmap or #niagads-api) immediately without waiting on /api/threads
    const hashTab = (window.location.hash || "").replace(/^#/, "").trim();
    if (hashTab === "mindmap" || hashTab === "niagads-api") {
      switchPortalTab(hashTab, { updateHash: false });
    }

    // Fetch saved study threads in the background at low priority
    refreshThreads();
  }

  boot();
})();
