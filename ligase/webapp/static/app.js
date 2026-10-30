/* Ligase Biomedical Co-Scientist WebApp Client
 * Zero external CDN dependencies · SSE live tool/token streaming · GFM responsive tables.
 */

(() => {
  "use strict";

  // ── Client Workspace ID (isolates threads/uploads per browser) ────────────
  function getClientId() {
    const key = "ligase_client_id";
    try {
      let id = localStorage.getItem(key);
      if (!id || id.length < 12) {
        id = "cli_" + (crypto.randomUUID ? crypto.randomUUID().replace(/-/g, "").slice(0, 20) : Math.random().toString(36).slice(2) + Date.now().toString(36));
        localStorage.setItem(key, id);
      }
      return id;
    } catch {
      return "local_default";
    }
  }

  const CLIENT_ID = getClientId();

  const state = {
    meta: null,
    threads: [],
    activeThreadId: null,
    profile: "ad1",
    mode: "direct", // "direct" | "plan"
    maxIterations: 10,
    pendingUploads: [], // [{name, token, size_bytes}]
    activeRunId: null,
    abortController: null,
  };

  // ── DOM Elements ──────────────────────────────────────────────────────────
  const el = {
    sidebar: document.getElementById("sidebar"),
    openSidebarBtn: document.getElementById("open-sidebar-btn"),
    closeSidebarBtn: document.getElementById("close-sidebar-btn"),
    appVersion: document.getElementById("app-version"),
    newStudyBtn: document.getElementById("new-study-btn"),
    threadList: document.getElementById("thread-list"),
    profileAd1Btn: document.getElementById("profile-ad1-btn"),
    profileA1Btn: document.getElementById("profile-a1-btn"),
    modeDirectBtn: document.getElementById("mode-direct-btn"),
    modePlanBtn: document.getElementById("mode-plan-btn"),
    statusDot: document.getElementById("status-dot"),
    modelBadgeText: document.getElementById("model-badge-text"),
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
        detail = err.detail || err.message || detail;
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

  function renderInline(line) {
    const codeSpans = [];
    let s = String(line ?? "").replace(/`([^`]+)`/g, (_, code) => {
      const idx = codeSpans.length;
      codeSpans.push(`<code>${escapeHtml(code)}</code>`);
      return `\u0000CODE${idx}\u0000`;
    });
    s = escapeHtml(s);
    s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|[\s(])\*([^*\n]+)\*(?=[\s).,;:!?]|$)/g, "$1<em>$2</em>");
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

      // Code fence
      if (line.trim().startsWith("```")) {
        const lang = line.trim().slice(3).trim();
        const buf = [];
        i++;
        while (i < lines.length && !lines[i].trim().startsWith("```")) {
          buf.push(lines[i]);
          i++;
        }
        i++; // skip closing fence
        out.push(`<pre><code data-lang="${escapeHtml(lang)}">${escapeHtml(buf.join("\n"))}</code></pre>`);
        continue;
      }

      // GFM Table -> Accessible Responsive Table Wrapper
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

      // Headings
      const hMatch = line.match(/^(#{1,4})\s+(.*)$/);
      if (hMatch) {
        const lvl = hMatch[1].length;
        out.push(`<h${lvl}>${renderInline(hMatch[2])}</h${lvl}>`);
        i++;
        continue;
      }

      // Blockquote
      if (line.trim().startsWith(">")) {
        const qBuf = [];
        while (i < lines.length && lines[i].trim().startsWith(">")) {
          qBuf.push(lines[i].trim().replace(/^>\s?/, ""));
          i++;
        }
        out.push(`<blockquote>${qBuf.map(renderInline).join("<br>")}</blockquote>`);
        continue;
      }

      // Unordered list
      if (/^\s*[-*+]\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
          items.push(`<li>${renderInline(lines[i].replace(/^\s*[-*+]\s+/, ""))}</li>`);
          i++;
        }
        out.push(`<ul>${items.join("")}</ul>`);
        continue;
      }

      // Ordered list
      if (/^\s*\d+[.)]\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
          items.push(`<li>${renderInline(lines[i].replace(/^\s*\d+[.)]\s+/, ""))}</li>`);
          i++;
        }
        out.push(`<ol>${items.join("")}</ol>`);
        continue;
      }

      // Horizontal rule
      if (/^\s*---+\s*$/.test(line)) {
        out.push("<hr>");
        i++;
        continue;
      }

      // Blank line
      if (!line.trim()) {
        i++;
        continue;
      }

      // Paragraph
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

  // ── UI Rendering Helpers ──────────────────────────────────────────────────
  function setProfile(profile) {
    state.profile = profile === "a1" ? "a1" : "ad1";
    el.profileAd1Btn.classList.toggle("active", state.profile === "ad1");
    el.profileA1Btn.classList.toggle("active", state.profile === "a1");

    if (state.profile === "ad1") {
      el.heroEyebrow.textContent = "ALZHEIMER'S GENOMICS · NIAGADS · MULTI-OMICS CO-SCIENTIST";
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
        : "Direct execution · live tool trace & downloadable Markdown report";
    el.sendBtn.textContent = state.mode === "plan" ? "Propose Plan ↵" : "Run Study ↵";
  }

  function showWelcomeOrTranscript(showTranscript) {
    el.welcomeView.hidden = showTranscript;
    el.transcript.hidden = !showTranscript;
  }

  function scrollCanvasToBottom() {
    el.canvas.scrollTop = el.canvas.scrollHeight;
  }

  function renderStarters() {
    const starters = state.meta?.starters || [];
    el.starterGrid.innerHTML = "";
    for (const s of starters) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "starter-card";
      btn.innerHTML = `
        <span class="starter-badge">${escapeHtml(s.badge)}</span>
        <div class="starter-title">${escapeHtml(s.title)}</div>
        <div class="starter-sub">${escapeHtml(s.subtitle)}</div>
      `;
      btn.addEventListener("click", () => {
        setProfile(s.profile || "ad1");
        el.chatInput.value = s.question;
        el.chatInput.focus();
        handleSubmitPrompt(s.question);
      });
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
      empty.style.padding = "0.55rem 0.6rem";
      empty.style.fontSize = "0.8rem";
      empty.style.color = "var(--text-muted)";
      empty.textContent = "No saved studies yet.";
      el.threadList.appendChild(empty);
      return;
    }

    for (const t of state.threads) {
      const row = document.createElement("div");
      row.className = "thread-item" + (t.id === state.activeThreadId ? " active" : "");
      row.tabIndex = 0;
      row.setAttribute("role", "button");

      const titleSpan = document.createElement("span");
      titleSpan.className = "thread-item-title";
      titleSpan.textContent = t.title;

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "thread-del-btn";
      delBtn.title = "Delete study";
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

      row.addEventListener("click", () => openThread(t.id));
      row.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          openThread(t.id);
        }
      });

      row.append(titleSpan, delBtn);
      el.threadList.appendChild(row);
    }
  }

  async function refreshThreads() {
    try {
      const data = await apiFetch("/api/threads");
      state.threads = data.threads || [];
      renderThreads();
    } catch {}
  }

  function startFreshStudy() {
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
    if (meta.tool_trace?.length) statsParts.push(`${meta.tool_trace.length} tool call${meta.tool_trace.length === 1 ? "" : "s"}`);

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
    planCard.innerHTML = `<div class="plan-card-header">📋 Generating Scientific Plan (${escapeHtml(state.meta?.model || "gpt-6-luna")})…</div><div class="md-body"><p>Triaging question and matching NIAGADS / biomedical tools…</p></div>`;
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
        <input type="text" placeholder="Describe how to revise the plan (e.g., also cross-check NG00075 IGAP)…" aria-label="Plan revision instructions">
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
      streamExecution(prompt, attachments, planMarkdown, /* skipUserBubble */ true);
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
      planCard.innerHTML = `<div class="plan-card-header">🚫 Execution Cancelled</div><p style="margin:0;font-size:0.86rem;color:var(--text-muted)">Nothing was executed.</p>`;
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
    mdContainer.innerHTML = `<p style="color:var(--text-muted)">Reasoning &amp; grounding with domain tools…</p>`;

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

  // ── IME-Safe Enter-to-Submit (modern-web-guidance: ime-safe-enter-submit) ──
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

  // ── Dialog Controls & Light-Dismiss Fallback (modern-web-guidance: dialog) ──
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

  // ── Theme Override Controls (modern-web-guidance: dark-mode-toggle) ───────
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

  // ── Boot ──────────────────────────────────────────────────────────────────
  async function boot() {
    syncThemeButtons();
    try {
      const meta = await apiFetch("/api/meta");
      state.meta = meta;
      el.appVersion.textContent = `v${meta.version}`;
      el.modelBadgeText.textContent = meta.model;
      el.statusDot.classList.toggle("offline", !meta.ready);
      el.diagnosticsSummary.textContent = `Model: ${meta.model} · Engine: Ligase v${meta.version} · Sandbox: ${meta.sandbox_mode} · Ready: ${meta.ready ? "Yes" : "Missing API Key"}`;
      renderStarters();
      renderCatalogDialog();
    } catch (err) {
      el.statusDot.classList.add("offline");
      el.diagnosticsSummary.textContent = `Could not reach backend: ${err.message}`;
    }
    await refreshThreads();
  }

  boot();
})();
