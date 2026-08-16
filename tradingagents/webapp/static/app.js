(function () {
  "use strict";

  const SETTINGS_KEY = "tradingagents.web.settings.v1";
  const POLL_INTERVAL_MS = 1600;
  const TERMINAL_STATUSES = new Set(["completed", "failed", "error", "cancelled", "canceled"]);
  const ACTIVE_STATUSES = new Set(["queued", "pending", "running", "processing", "in_progress"]);
  const CRYPTO_BASES = new Set(["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LTC", "BCH", "DOT", "AVAX", "LINK"]);
  const CRYPTO_QUOTES = ["USDT", "USDC", "USD"];

  const state = {
    options: null,
    providers: new Map(),
    currentRun: null,
    currentRunId: null,
    pollGeneration: 0,
    pollFailures: 0,
    historyGeneration: 0,
    historyDate: "",
    activeTab: "live",
    decisionText: "",
    reportsText: "",
  };

  const dom = {};

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    cacheDom();
    bindEvents();
    startClock();

    const today = toLocalISODate(new Date());
    dom.analysisDate.value = today;
    dom.analysisDate.max = today;
    dom.historyDate.value = today;
    dom.historyDate.max = today;
    state.historyDate = today;
    updateHistoryDateLabel(today);

    loadOptions();
    loadHistory(today);
  }

  function cacheDom() {
    const ids = [
      "session-state", "storage-dot", "storage-status", "clock-date", "clock-time", "clock-zone",
      "analysis-form", "ticker-input", "analysis-date", "language-select", "custom-language-input",
      "depth-select", "analyst-options", "crypto-analyst-note", "provider-select", "quick-model-select", "deep-model-select",
      "custom-quick-model", "custom-deep-model", "backend-url-group", "backend-url-select",
      "backend-url-input", "backend-url-requirement", "thinking-control-group", "thinking-control-label",
      "thinking-control-select",
      "form-message", "launch-button", "launch-subtitle", "storage-note", "active-symbol", "run-state",
      "run-status-text", "progress-fill", "run-id-label", "run-phase-label", "run-progress-label",
      "live-count", "report-count", "decision-count", "agent-total", "phase-list", "live-indicator",
      "wire-feed", "report-list", "reports-title", "copy-reports", "decision-content", "copy-decision",
      "history-refresh", "history-prev", "history-next", "history-date", "history-today", "history-count",
      "history-date-label", "history-list", "toast-region"
    ];

    ids.forEach(function (id) {
      const element = document.getElementById(id);
      if (!element) {
        throw new Error("Missing required UI element: #" + id);
      }
      dom[toCamelCase(id)] = element;
    });

    dom.analystFieldset = document.querySelector(".analyst-fieldset");
    dom.tabs = Array.from(document.querySelectorAll('[role="tab"][data-tab]'));
    dom.tabPanels = Array.from(document.querySelectorAll('[role="tabpanel"]'));
  }

  function bindEvents() {
    dom.analysisForm.addEventListener("submit", submitRun);
    dom.analysisForm.addEventListener("change", function () {
      clearFormMessage();
      saveSettings();
    });
    dom.analysisForm.addEventListener("input", saveSettings);

    dom.tickerInput.addEventListener("input", function () {
      const selectionStart = dom.tickerInput.selectionStart;
      dom.tickerInput.value = dom.tickerInput.value.toUpperCase();
      if (selectionStart !== null) {
        dom.tickerInput.setSelectionRange(selectionStart, selectionStart);
      }
      syncAnalystsForTicker();
    });
    dom.providerSelect.addEventListener("change", function () {
      configureProvider(dom.providerSelect.value, false);
      saveSettings();
    });
    dom.quickModelSelect.addEventListener("change", function () {
      syncCustomModelInput("quick");
      saveSettings();
    });
    dom.deepModelSelect.addEventListener("change", function () {
      syncCustomModelInput("deep");
      saveSettings();
    });
    dom.languageSelect.addEventListener("change", function () {
      syncCustomLanguage();
      saveSettings();
    });
    dom.backendUrlSelect.addEventListener("change", function () {
      syncBackendInput();
      saveSettings();
    });

    dom.tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        activateTab(tab.dataset.tab, true);
      });
      tab.addEventListener("keydown", handleTabKeydown);
    });

    dom.copyReports.addEventListener("click", function () {
      copyText(state.reportsText, "All reports copied.");
    });
    dom.copyDecision.addEventListener("click", function () {
      copyText(state.decisionText, "Decision copied.");
    });

    dom.historyRefresh.addEventListener("click", function () {
      loadHistory(dom.historyDate.value);
    });
    dom.historyDate.addEventListener("change", function () {
      loadHistory(dom.historyDate.value);
    });
    dom.historyPrev.addEventListener("click", function () {
      shiftHistoryDate(-1);
    });
    dom.historyNext.addEventListener("click", function () {
      shiftHistoryDate(1);
    });
    dom.historyToday.addEventListener("click", function () {
      const today = toLocalISODate(new Date());
      dom.historyDate.value = today;
      loadHistory(today);
    });

    document.addEventListener("keydown", function (event) {
      if (event.ctrlKey && event.key === "Enter") {
        event.preventDefault();
        if (!dom.launchButton.disabled) {
          dom.analysisForm.requestSubmit();
        }
        return;
      }
      if (!event.ctrlKey && !event.altKey && !event.metaKey && /^F[1-3]$/.test(event.key)) {
        event.preventDefault();
        activateTab({ F1: "live", F2: "reports", F3: "decision" }[event.key], true);
      }
    });

    window.addEventListener("online", function () {
      setSessionState("ONLINE");
      showToast("Network connection restored.", "success");
    });
    window.addEventListener("offline", function () {
      setSessionState("OFFLINE");
      showToast("Network connection lost.", "error");
    });
  }

  async function loadOptions() {
    setSessionState("CONNECTING");
    setFormEnabled(false, "Loading server options");

    try {
      const options = await requestJSON("/api/options");
      state.options = options || {};
      hydrateOptions(state.options);
      setSessionState(navigator.onLine ? "READY" : "OFFLINE");
      clearFormMessage();
    } catch (error) {
      setSessionState("API ERROR");
      setStorageStatus({ mode: "unavailable", configured: false, message: "Unable to read server storage configuration." });
      setFormEnabled(false, "Server options unavailable");
      showFormMessage("Could not load configuration: " + error.message);
    }
  }

  function hydrateOptions(options) {
    const saved = readSettings();
    const defaults = isPlainObject(options.defaults) ? options.defaults : {};

    const languages = normalizeOptionList(options.output_languages || options.languages);
    if (!languages.some(function (language) { return language.id.toLowerCase() === "custom"; })) {
      languages.push({ id: "custom", label: "Custom language" });
    }
    const depths = normalizeOptionList(options.research_depths || options.depths);
    const analysts = normalizeOptionList(options.analysts);
    const providers = normalizeProviderList(options.providers);

    if (!languages.length || !depths.length || !analysts.length || !providers.length) {
      throw new Error("The server returned an incomplete options payload.");
    }

    fillSelect(dom.languageSelect, languages, {
      selected: saved.output_language || pick(defaults, ["output_language", "language"]),
    });
    fillSelect(dom.depthSelect, depths, {
      selected: stringValue(saved.research_depth || pick(defaults, ["research_depth", "max_debate_rounds"])),
    });

    dom.analystOptions.replaceChildren();
    const defaultAnalysts = arrayValue(saved.analysts).length
      ? arrayValue(saved.analysts)
      : arrayValue(pick(defaults, ["analysts", "selected_analysts"]));
    const selectedAnalysts = new Set(defaultAnalysts.map(String));
    analysts.forEach(function (analyst, index) {
      const wrapper = createElement("div", "analyst-option");
      const checkbox = document.createElement("input");
      const label = document.createElement("label");
      checkbox.type = "checkbox";
      checkbox.name = "analysts";
      checkbox.value = analyst.id;
      checkbox.id = "analyst-option-" + index;
      checkbox.checked = selectedAnalysts.size ? selectedAnalysts.has(analyst.id) : true;
      label.htmlFor = checkbox.id;
      label.textContent = analyst.label;
      wrapper.append(checkbox, label);
      dom.analystOptions.append(wrapper);
    });
    state.providers.clear();
    providers.forEach(function (provider) {
      state.providers.set(provider.id, provider);
    });
    fillSelect(dom.providerSelect, providers, {
      selected: saved.llm_provider || pick(defaults, ["llm_provider", "provider"]),
    });

    const initialTicker = saved.ticker || defaults.ticker;
    if (initialTicker) {
      dom.tickerInput.value = String(initialTicker).toUpperCase();
    }
    syncAnalystsForTicker();
    if (saved.analysis_date && saved.analysis_date <= toLocalISODate(new Date())) {
      dom.analysisDate.value = saved.analysis_date;
    }

    dom.languageSelect.disabled = false;
    dom.depthSelect.disabled = false;
    dom.providerSelect.disabled = false;
    dom.analystFieldset.disabled = false;
    syncCustomLanguage(saved.custom_language);
    configureProvider(dom.providerSelect.value, true, saved);
    setStorageStatus(options.storage || options.firebase || options.firebase_status || {});
    setFormEnabled(true, "Ready to launch");
  }

  function normalizeProviderList(input) {
    const source = normalizeObjectCollection(input);
    return source.map(function (raw, index) {
      if (!isPlainObject(raw)) {
        return { id: String(raw), label: String(raw), raw: {} };
      }
      const id = stringValue(raw.id || raw.value || raw.key || raw.name || index);
      return {
        id: id,
        label: stringValue(raw.label || raw.display || raw.title || raw.name || id),
        raw: raw,
      };
    }).filter(function (provider) {
      return Boolean(provider.id);
    });
  }

  function configureProvider(providerId, restore, explicitSettings) {
    const provider = state.providers.get(providerId);
    if (!provider) {
      fillSelect(dom.quickModelSelect, [], { placeholder: "No models available" });
      fillSelect(dom.deepModelSelect, [], { placeholder: "No models available" });
      dom.quickModelSelect.disabled = true;
      dom.deepModelSelect.disabled = true;
      hideProviderControls();
      return;
    }

    const raw = provider.raw || {};
    const defaults = isPlainObject(state.options && state.options.defaults) ? state.options.defaults : {};
    const saved = explicitSettings || readSettings();
    const quickModels = normalizeOptionList(raw.quick_models || raw.quick || raw.models);
    const deepModels = normalizeOptionList(raw.deep_models || raw.deep || raw.models);

    const quickSelection = restore
      ? saved.quick_model_choice || saved.quick_model || raw.default_quick_model || pick(defaults, ["quick_model", "quick_think_llm"])
      : raw.default_quick_model || pick(defaults, ["quick_model", "quick_think_llm"]);
    const deepSelection = restore
      ? saved.deep_model_choice || saved.deep_model || raw.default_deep_model || pick(defaults, ["deep_model", "deep_think_llm"])
      : raw.default_deep_model || pick(defaults, ["deep_model", "deep_think_llm"]);

    fillSelect(dom.quickModelSelect, quickModels, { selected: stringValue(quickSelection) });
    fillSelect(dom.deepModelSelect, deepModels, { selected: stringValue(deepSelection) });
    dom.quickModelSelect.disabled = !quickModels.length;
    dom.deepModelSelect.disabled = !deepModels.length;

    if (restore && saved.custom_quick_model) {
      dom.customQuickModel.value = saved.custom_quick_model;
    }
    if (restore && saved.custom_deep_model) {
      dom.customDeepModel.value = saved.custom_deep_model;
    }
    syncCustomModelInput("quick");
    syncCustomModelInput("deep");
    configureBackendControl(raw, restore ? saved : {});
    configureThinkingControl(raw, restore ? saved : {});
  }

  function configureBackendControl(provider, saved) {
    const backendOptions = normalizeOptionList(
      provider.backend_urls || provider.backends || provider.endpoints || provider.regions
    );
    const defaultUrl = stringValue(
      provider.default_backend_url ||
      (typeof provider.backend_url === "string" ? provider.backend_url : "") ||
      pick(state.options && state.options.defaults, ["backend_url"])
    );
    const show = backendOptions.length > 0 || Boolean(
      provider.supports_backend_url || provider.allow_custom_backend || provider.requires_backend_url
    );

    dom.backendUrlGroup.hidden = !show;
    dom.backendUrlInput.required = Boolean(provider.requires_backend_url);
    dom.backendUrlRequirement.textContent = provider.requires_backend_url ? "REQUIRED" : "OPTIONAL";
    if (!show) {
      dom.backendUrlSelect.hidden = true;
      dom.backendUrlSelect.disabled = true;
      dom.backendUrlInput.hidden = false;
      dom.backendUrlInput.disabled = true;
      dom.backendUrlInput.value = "";
      return;
    }

    if (backendOptions.length) {
      fillSelect(dom.backendUrlSelect, backendOptions, {
        selected: saved.backend_url_choice || saved.backend_url || defaultUrl,
      });
      dom.backendUrlSelect.hidden = false;
      dom.backendUrlSelect.disabled = false;
      dom.backendUrlInput.value = saved.custom_backend_url || (dom.backendUrlSelect.value === "custom" ? defaultUrl : "");
      syncBackendInput();
    } else {
      dom.backendUrlSelect.hidden = true;
      dom.backendUrlSelect.disabled = true;
      dom.backendUrlInput.hidden = false;
      dom.backendUrlInput.disabled = false;
      dom.backendUrlInput.value = saved.backend_url || defaultUrl;
    }
  }

  function configureThinkingControl(provider, saved) {
    const control = findThinkingControl(provider);
    if (!control || !control.options.length) {
      dom.thinkingControlGroup.hidden = true;
      dom.thinkingControlSelect.disabled = true;
      dom.thinkingControlSelect.removeAttribute("data-payload-key");
      dom.thinkingControlSelect.replaceChildren();
      return;
    }

    const defaults = isPlainObject(state.options && state.options.defaults) ? state.options.defaults : {};
    const selected = saved[control.key] || control.defaultValue || defaults[control.key];
    dom.thinkingControlGroup.hidden = false;
    dom.thinkingControlLabel.textContent = control.label;
    dom.thinkingControlSelect.dataset.payloadKey = control.key;
    fillSelect(dom.thinkingControlSelect, control.options, {
      selected: stringValue(selected),
      placeholder: control.required ? "Select a mode" : "Provider default",
      includePlaceholder: !control.required,
    });
    dom.thinkingControlSelect.disabled = false;
    dom.thinkingControlSelect.required = Boolean(control.required);
  }

  function findThinkingControl(provider) {
    let rawControl = provider.thinking_control || provider.thinking_controls;
    if (Array.isArray(rawControl)) {
      rawControl = rawControl[0];
    } else if (isPlainObject(rawControl) && !rawControl.options && !rawControl.values) {
      const knownKey = ["thinking_level", "reasoning_effort", "anthropic_effort"].find(function (key) {
        return rawControl[key] !== undefined;
      });
      if (knownKey) {
        const value = rawControl[knownKey];
        rawControl = isPlainObject(value)
          ? Object.assign({ key: knownKey }, value)
          : { key: knownKey, options: value };
      }
    }

    if (rawControl) {
      if (Array.isArray(rawControl) || typeof rawControl === "string") {
        rawControl = { options: rawControl };
      }
      if (isPlainObject(rawControl)) {
        const key = stringValue(rawControl.key || rawControl.name || rawControl.payload_key || "thinking_level");
        return {
          key: key,
          label: stringValue(rawControl.label || humanize(key)),
          options: normalizeOptionList(rawControl.options || rawControl.values),
          defaultValue: rawControl.default,
          required: Boolean(rawControl.required),
        };
      }
    }

    const candidates = [
      ["thinking_level", provider.thinking_levels || provider.thinking_options, "Thinking Mode"],
      ["reasoning_effort", provider.reasoning_efforts, "Reasoning Effort"],
      ["anthropic_effort", provider.anthropic_efforts || provider.effort_levels, "Effort Level"],
    ];
    const match = candidates.find(function (candidate) {
      return normalizeOptionList(candidate[1]).length > 0;
    });
    return match ? {
      key: match[0],
      options: normalizeOptionList(match[1]),
      label: match[2],
      defaultValue: provider["default_" + match[0]],
      required: false,
    } : null;
  }

  function hideProviderControls() {
    dom.backendUrlGroup.hidden = true;
    dom.thinkingControlGroup.hidden = true;
    dom.backendUrlInput.disabled = true;
    dom.backendUrlSelect.disabled = true;
    dom.thinkingControlSelect.disabled = true;
    dom.customQuickModel.hidden = true;
    dom.customQuickModel.disabled = true;
    dom.customDeepModel.hidden = true;
    dom.customDeepModel.disabled = true;
  }

  function syncCustomModelInput(kind) {
    const select = kind === "quick" ? dom.quickModelSelect : dom.deepModelSelect;
    const input = kind === "quick" ? dom.customQuickModel : dom.customDeepModel;
    const isCustom = select.value.toLowerCase() === "custom";
    input.hidden = !isCustom;
    input.disabled = !isCustom;
    input.required = isCustom;
    if (isCustom && document.activeElement === select) {
      window.requestAnimationFrame(function () { input.focus(); });
    }
  }

  function syncAnalystsForTicker() {
    const fundamentals = dom.analystOptions.querySelector('input[value="fundamentals"]');
    if (!fundamentals) return;
    const crypto = isCryptoTicker(dom.tickerInput.value);
    if (crypto && !fundamentals.disabled) {
      fundamentals.dataset.previousChecked = String(fundamentals.checked);
      fundamentals.checked = false;
    } else if (!crypto && fundamentals.disabled) {
      fundamentals.checked = fundamentals.dataset.previousChecked !== "false";
      delete fundamentals.dataset.previousChecked;
    }
    fundamentals.disabled = crypto;
    dom.cryptoAnalystNote.hidden = !crypto;
  }

  function isCryptoTicker(value) {
    const ticker = String(value || "").trim().toUpperCase().replace(/\+$/, "");
    if (["-USD", "-USDT", "-USDC", "-BTC", "-ETH"].some(function (suffix) {
      return ticker.endsWith(suffix);
    })) {
      return true;
    }
    const compact = ticker.replace(/-/g, "");
    return CRYPTO_QUOTES.some(function (quote) {
      return compact.endsWith(quote) && CRYPTO_BASES.has(compact.slice(0, -quote.length));
    });
  }

  function syncCustomLanguage(savedValue) {
    if (savedValue && !dom.customLanguageInput.value) {
      dom.customLanguageInput.value = savedValue;
    }
    const isCustom = dom.languageSelect.value.toLowerCase() === "custom";
    dom.customLanguageInput.hidden = !isCustom;
    dom.customLanguageInput.disabled = !isCustom;
    dom.customLanguageInput.required = isCustom;
    if (isCustom && document.activeElement === dom.languageSelect) {
      window.requestAnimationFrame(function () { dom.customLanguageInput.focus(); });
    }
  }

  function syncBackendInput() {
    const custom = dom.backendUrlSelect.value.toLowerCase() === "custom";
    dom.backendUrlInput.hidden = !custom;
    dom.backendUrlInput.disabled = !custom;
    if (custom && document.activeElement === dom.backendUrlSelect) {
      window.requestAnimationFrame(function () { dom.backendUrlInput.focus(); });
    }
  }

  async function submitRun(event) {
    event.preventDefault();
    clearFormMessage();

    const validation = buildRunPayload();
    if (!validation.ok) {
      showFormMessage(validation.message);
      if (validation.focus) {
        validation.focus.focus();
      }
      return;
    }

    setLaunchBusy(true);
    saveSettings();
    activateTab("live", false);
    state.pollGeneration += 1;
    const generation = state.pollGeneration;
    let acceptedActiveRun = false;

    try {
      const response = await requestJSON("/api/runs", {
        method: "POST",
        body: JSON.stringify(validation.payload),
      });
      const run = unwrapRun(response);
      const runId = getRunId(run) || getRunId(response);
      if (!runId) {
        throw new Error("The server did not return a run_id.");
      }

      state.currentRunId = runId;
      state.currentRun = Object.assign({}, validation.payload, run, { run_id: runId });
      state.pollFailures = 0;
      renderRun(state.currentRun);
      showToast("Analysis run accepted: " + shortId(runId), "success");

      if (TERMINAL_STATUSES.has(normalizeStatus(state.currentRun.status))) {
        loadHistory(dom.historyDate.value);
      } else {
        acceptedActiveRun = true;
        pollRun(runId, generation);
      }
    } catch (error) {
      showFormMessage("Unable to start analysis: " + error.message);
      showToast("Run request failed.", "error");
      renderRunError(error.message);
    } finally {
      if (acceptedActiveRun) {
        setLaunchRunActive(true);
      } else {
        setLaunchBusy(false);
      }
    }
  }

  function buildRunPayload() {
    const ticker = dom.tickerInput.value.trim().toUpperCase();
    const analysts = Array.from(dom.analystOptions.querySelectorAll('input[name="analysts"]:checked'))
      .map(function (input) { return input.value; });
    const quickModel = selectedModelValue("quick");
    const deepModel = selectedModelValue("deep");
    const language = dom.languageSelect.value === "custom"
      ? dom.customLanguageInput.value.trim()
      : dom.languageSelect.value;

    if (!ticker) {
      return invalid("Enter a ticker or supported asset symbol.", dom.tickerInput);
    }
    if (!/^(?:[A-Z0-9._^=\-]{1,32}|[A-Z0-9._^=\-]{1,31}\+)$/.test(ticker)) {
      return invalid("Ticker contains unsupported characters.", dom.tickerInput);
    }
    if (!dom.analysisDate.value) {
      return invalid("Select an analysis date.", dom.analysisDate);
    }
    if (dom.analysisDate.value > toLocalISODate(new Date())) {
      return invalid("Analysis date cannot be in the future.", dom.analysisDate);
    }
    if (!language) {
      return invalid("Select or enter an output language.", dom.languageSelect.value === "custom" ? dom.customLanguageInput : dom.languageSelect);
    }
    if (!analysts.length) {
      const first = dom.analystOptions.querySelector('input[name="analysts"]');
      return invalid("Select at least one analyst.", first);
    }
    if (isCryptoTicker(ticker) && analysts.includes("fundamentals")) {
      const fundamentals = dom.analystOptions.querySelector('input[value="fundamentals"]');
      return invalid("Fundamentals analysis is unavailable for crypto instruments.", fundamentals);
    }
    if (!dom.depthSelect.value) {
      return invalid("Select a research depth.", dom.depthSelect);
    }
    if (!dom.providerSelect.value) {
      return invalid("Select an LLM provider.", dom.providerSelect);
    }
    if (!quickModel) {
      return invalid("Select or enter a quick-thinking model ID.", dom.quickModelSelect.value === "custom" ? dom.customQuickModel : dom.quickModelSelect);
    }
    if (!deepModel) {
      return invalid("Select or enter a deep-thinking model ID.", dom.deepModelSelect.value === "custom" ? dom.customDeepModel : dom.deepModelSelect);
    }

    const depth = /^-?\d+(\.\d+)?$/.test(dom.depthSelect.value)
      ? Number(dom.depthSelect.value)
      : dom.depthSelect.value;
    const payload = {
      ticker: ticker,
      analysis_date: dom.analysisDate.value,
      output_language: language,
      analysts: analysts,
      research_depth: depth,
      llm_provider: dom.providerSelect.value,
      quick_model: quickModel,
      deep_model: deepModel,
    };

    const backendUrl = selectedBackendUrl();
    const selectedProvider = state.providers.get(dom.providerSelect.value);
    const backendRequired = Boolean(
      selectedProvider && selectedProvider.raw && selectedProvider.raw.requires_backend_url
    );
    if (backendRequired && !backendUrl) {
      return invalid("Enter the required backend URL for this provider.", dom.backendUrlInput);
    }
    if (backendUrl) {
      try {
        const parsedBackend = new URL(backendUrl);
        if (!["http:", "https:"].includes(parsedBackend.protocol) || parsedBackend.username ||
            parsedBackend.password || parsedBackend.search || parsedBackend.hash) {
          throw new Error("unsupported URL components");
        }
      } catch (_error) {
        return invalid("Backend URL must be an absolute HTTP(S) URL without credentials, query parameters, or a fragment.", dom.backendUrlInput);
      }
      payload.backend_url = backendUrl;
    }

    if (!dom.thinkingControlGroup.hidden && !dom.thinkingControlSelect.disabled) {
      const key = dom.thinkingControlSelect.dataset.payloadKey;
      if (key && dom.thinkingControlSelect.value) {
        payload[key] = dom.thinkingControlSelect.value;
      }
    }

    return { ok: true, payload: payload };
  }

  function invalid(message, focus) {
    return { ok: false, message: message, focus: focus };
  }

  async function pollRun(runId, generation) {
    if (generation !== state.pollGeneration || runId !== state.currentRunId) {
      return;
    }

    try {
      const response = await requestJSON("/api/runs/" + encodeURIComponent(runId));
      if (generation !== state.pollGeneration || runId !== state.currentRunId) {
        return;
      }
      const run = unwrapRun(response);
      state.currentRun = Object.assign({}, state.currentRun || {}, run, { run_id: runId });
      state.pollFailures = 0;
      renderRun(state.currentRun);

      const status = normalizeStatus(state.currentRun.status);
      if (TERMINAL_STATUSES.has(status)) {
        setLaunchRunActive(false);
        loadHistory(dom.historyDate.value);
        showToast(
          status === "completed" ? "Analysis completed." : "Analysis ended with status: " + status,
          status === "completed" ? "success" : "error"
        );
        return;
      }
    } catch (error) {
      if (generation !== state.pollGeneration) {
        return;
      }
      state.pollFailures += 1;
      if (state.pollFailures === 1 || state.pollFailures % 5 === 0) {
        showToast("Live update unavailable; retrying. " + error.message, "error");
      }
      dom.liveIndicator.textContent = "RECONNECTING";
      dom.liveIndicator.classList.remove("active");
    }

    const delay = state.pollFailures ? Math.min(10000, 2500 + state.pollFailures * 1000) : POLL_INTERVAL_MS;
    window.setTimeout(function () {
      pollRun(runId, generation);
    }, delay);
  }

  function renderRun(run) {
    const status = normalizeStatus(run.status || "unknown");
    const runId = getRunId(run) || state.currentRunId;
    const ticker = stringValue(run.ticker || run.symbol || run.asset || "UNKNOWN").toUpperCase();
    const phase = stringValue(run.current_phase || run.phase || run.current_agent || "—");
    const progress = extractProgress(run);

    dom.activeSymbol.textContent = ticker + (run.analysis_date ? " // " + run.analysis_date : "");
    dom.runState.dataset.status = cssStatus(status);
    dom.runStatusText.textContent = displayStatus(status);
    dom.progressFill.style.width = progress + "%";
    dom.runIdLabel.textContent = "RUN " + shortId(runId || "—");
    dom.runPhaseLabel.textContent = "PHASE " + phase;
    dom.runProgressLabel.textContent = Math.round(progress) + "%";
    dom.liveIndicator.textContent = ACTIVE_STATUSES.has(status) ? "LIVE" : displayStatus(status);
    dom.liveIndicator.classList.toggle("active", ACTIVE_STATUSES.has(status));
    setSessionState(ACTIVE_STATUSES.has(status) ? "RUNNING" : (navigator.onLine ? "READY" : "OFFLINE"));

    renderPhases(run);
    renderEvents(run);
    renderReports(run);
    renderDecision(run);
  }

  function renderRunError(message) {
    dom.runState.dataset.status = "error";
    dom.runStatusText.textContent = "REQUEST FAILED";
    dom.liveIndicator.textContent = "ERROR";
    dom.liveIndicator.classList.remove("active");
    dom.wireFeed.replaceChildren();
    const banner = createElement("div", "wire-error-banner");
    banner.textContent = message;
    dom.wireFeed.append(banner);
  }

  function renderPhases(run) {
    const phases = extractPhases(run);
    dom.phaseList.replaceChildren();
    dom.agentTotal.textContent = phases.length + (phases.length === 1 ? " NODE" : " NODES");

    if (!phases.length) {
      const empty = createElement("div", "rail-empty");
      const count = createElement("span", "", "00");
      const text = createElement("p", "", "No agent activity");
      empty.append(count, text);
      dom.phaseList.append(empty);
      return;
    }

    const fragment = document.createDocumentFragment();
    phases.forEach(function (phase, index) {
      const item = createElement("div", "phase-item");
      const normalized = cssStatus(normalizeStatus(phase.status));
      item.dataset.status = normalized;
      const number = createElement("span", "phase-index", String(index + 1).padStart(2, "0"));
      const copy = createElement("div", "phase-copy");
      const title = createElement("strong", "", phase.name);
      const status = createElement("small", "", displayStatus(normalized));
      const dot = createElement("span", "phase-status-dot");
      dot.setAttribute("aria-hidden", "true");
      copy.append(title, status);
      item.append(number, copy, dot);
      fragment.append(item);
    });
    dom.phaseList.append(fragment);
  }

  function extractPhases(run) {
    const result = [];
    const source = run.phases || run.agent_status || run.agentStatus || run.agents;

    if (Array.isArray(source)) {
      source.forEach(function (item, index) {
        if (isPlainObject(item)) {
          result.push({
            name: stringValue(item.label || item.name || item.agent || item.phase || "Node " + (index + 1)),
            status: item.status || item.state || "pending",
          });
        } else {
          result.push({ name: stringValue(item), status: "pending" });
        }
      });
    } else if (isPlainObject(source)) {
      Object.entries(source).forEach(function (entry) {
        const value = entry[1];
        result.push({
          name: humanize(entry[0]),
          status: isPlainObject(value) ? value.status || value.state : value,
        });
      });
    }

    if (!result.length && (run.current_agent || run.current_phase)) {
      result.push({
        name: stringValue(run.current_agent || run.current_phase),
        status: ACTIVE_STATUSES.has(normalizeStatus(run.status)) ? "running" : run.status,
      });
    }
    return result;
  }

  function renderEvents(run) {
    const events = extractEvents(run);
    const wasNearBottom = dom.wireFeed.scrollHeight - dom.wireFeed.scrollTop - dom.wireFeed.clientHeight < 80;
    dom.wireFeed.replaceChildren();
    dom.liveCount.textContent = String(events.length);

    if (!events.length) {
      const empty = createElement("div", "workspace-empty");
      const grid = createElement("div", "empty-grid");
      grid.setAttribute("aria-hidden", "true");
      const code = createElement("span", "empty-code", ACTIVE_STATUSES.has(normalizeStatus(run.status)) ? "TA://RUNNING" : "TA://NO-EVENTS");
      const heading = createElement("h3", "", ACTIVE_STATUSES.has(normalizeStatus(run.status)) ? "Agents are initializing" : "No response events available");
      const text = createElement("p", "", ACTIVE_STATUSES.has(normalizeStatus(run.status))
        ? "The server accepted this run. Responses will appear as agents publish updates."
        : "This run does not contain a response wire payload.");
      empty.append(grid, code, heading, text);
      dom.wireFeed.append(empty);
    } else {
      const fragment = document.createDocumentFragment();
      events.slice(-500).forEach(function (event) {
        const row = createElement("article", "wire-event");
        row.dataset.type = normalizeStatus(event.type || "message");
        row.dataset.status = cssStatus(normalizeStatus(event.status || ""));
        const time = createElement("time", "wire-time", formatEventTime(event.timestamp));
        if (event.timestamp) {
          time.dateTime = stringValue(event.timestamp);
        }
        const source = createElement("div", "wire-source", event.agent || "SYSTEM");
        source.title = event.agent || "System";
        const message = createElement("div", "wire-message", event.message);
        row.append(time, source, message);
        fragment.append(row);
      });
      dom.wireFeed.append(fragment);
    }

    const error = extractError(run);
    if (error) {
      const banner = createElement("div", "wire-error-banner");
      banner.textContent = error;
      dom.wireFeed.append(banner);
    }

    if (wasNearBottom || ACTIVE_STATUSES.has(normalizeStatus(run.status))) {
      window.requestAnimationFrame(function () {
        dom.wireFeed.scrollTop = dom.wireFeed.scrollHeight;
      });
    }
  }

  function extractEvents(run) {
    let source = run.events || run.messages || run.activity || run.feed || [];
    if (isPlainObject(source)) {
      source = Object.values(source);
    }
    if (!Array.isArray(source)) {
      source = [source];
    }

    return source.filter(function (item) {
      return item !== null && item !== undefined;
    }).map(function (item, index) {
      if (!isPlainObject(item)) {
        return { id: index, timestamp: "", agent: "SYSTEM", type: "message", status: "", message: valueToText(item) };
      }
      const nestedMessage = item.message;
      let content = normalizeStatus(item.type) === "report"
        ? item.message || item.content
        : item.content || item.text || item.summary || item.detail || item.output;
      if (!content && isPlainObject(nestedMessage)) {
        content = nestedMessage.content || nestedMessage.text || nestedMessage.message || nestedMessage;
      } else if (!content) {
        content = nestedMessage;
      }
      return {
        id: item.id || item.event_id || index,
        timestamp: item.timestamp || item.created_at || item.time || item.updated_at || "",
        agent: stringValue(item.agent || item.source || item.name || item.node || item.role || "SYSTEM"),
        type: stringValue(item.type || item.event_type || "message"),
        status: stringValue(item.status || item.state || ""),
        message: valueToText(content || item),
      };
    });
  }

  function renderReports(run) {
    const reports = collectReports(run);
    dom.reportList.replaceChildren();
    dom.reportCount.textContent = String(reports.length);
    dom.reportsTitle.textContent = reports.length ? "Generated Reports // " + reports.length : "Generated Reports";
    state.reportsText = reports.map(function (report) {
      return report.label.toUpperCase() + "\n" + report.content;
    }).join("\n\n" + "-".repeat(60) + "\n\n");
    dom.copyReports.disabled = !reports.length;

    if (!reports.length) {
      const empty = createElement("div", "content-empty");
      empty.append(
        createElement("span", "", "REPORT QUEUE EMPTY"),
        createElement("p", "", "Completed analyst and debate reports will be filed here.")
      );
      dom.reportList.append(empty);
      return;
    }

    const fragment = document.createDocumentFragment();
    reports.forEach(function (report, index) {
      const card = createElement("details", "report-card");
      card.open = index === reports.length - 1;
      const summary = document.createElement("summary");
      const title = createElement("span", "", report.label);
      const meta = createElement("small", "", countWords(report.content) + " WORDS");
      const body = createElement("pre", "report-body", report.content);
      summary.append(title, meta);
      card.append(summary, body);
      fragment.append(card);
    });
    dom.reportList.append(fragment);
  }

  function collectReports(run) {
    const reports = [];
    const seen = new Set();
    const add = function (label, content) {
      const text = valueToText(content).trim();
      if (!text || text === "{}" || text === "[]") {
        return;
      }
      const fingerprint = String(label) + "\u0000" + text;
      if (seen.has(fingerprint)) {
        return;
      }
      seen.add(fingerprint);
      reports.push({ label: humanize(label), content: text });
    };

    const source = run.reports || (isPlainObject(run.result) ? run.result.reports : null);
    if (Array.isArray(source)) {
      source.forEach(function (report, index) {
        if (isPlainObject(report)) {
          add(report.label || report.title || report.name || report.agent || "Report " + (index + 1),
            report.content || report.report || report.text || report.output || report);
        } else {
          add("Report " + (index + 1), report);
        }
      });
    } else if (isPlainObject(source)) {
      Object.entries(source).forEach(function (entry) {
        const value = entry[1];
        if (isPlainObject(value) && (value.content || value.report || value.text || value.output)) {
          add(value.label || value.title || value.name || entry[0], value.content || value.report || value.text || value.output);
        } else if (isPlainObject(value)) {
          Object.entries(value).forEach(function (nested) {
            add(humanize(entry[0]) + " // " + humanize(nested[0]), nested[1]);
          });
        } else {
          add(entry[0], value);
        }
      });
    }

    const finalState = run.final_state || (isPlainObject(run.result) ? run.result.final_state : null) ||
      (hasKnownReportFields(run.result) ? run.result : null) || (hasKnownReportFields(run) ? run : null);
    if (isPlainObject(finalState)) {
      [
        ["Market Analyst", "market_report"],
        ["Sentiment Analyst", "sentiment_report"],
        ["News Analyst", "news_report"],
        ["Fundamentals Analyst", "fundamentals_report"],
        ["Trader Investment Plan", "trader_investment_plan"],
      ].forEach(function (mapping) {
        if (finalState[mapping[1]]) {
          add(mapping[0], finalState[mapping[1]]);
        }
      });

      const investment = finalState.investment_debate_state;
      if (isPlainObject(investment)) {
        add("Bull Researcher", investment.bull_history);
        add("Bear Researcher", investment.bear_history);
        add("Research Manager", investment.judge_decision);
      }
      const risk = finalState.risk_debate_state;
      if (isPlainObject(risk)) {
        add("Aggressive Risk Analyst", risk.aggressive_history);
        add("Conservative Risk Analyst", risk.conservative_history);
        add("Neutral Risk Analyst", risk.neutral_history);
      }
    }
    return reports;
  }

  function renderDecision(run) {
    const decision = extractDecision(run);
    dom.decisionContent.replaceChildren();
    state.decisionText = decision === null || decision === undefined ? "" : valueToText(decision);
    dom.copyDecision.disabled = !state.decisionText;
    dom.decisionCount.textContent = state.decisionText ? "1" : "—";

    if (!state.decisionText) {
      const empty = createElement("div", "content-empty decision-empty");
      empty.append(
        createElement("span", "", "AWAITING CONSENSUS"),
        createElement("p", "", "The portfolio manager decision will appear after research and risk debates complete.")
      );
      dom.decisionContent.append(empty);
      return;
    }

    const card = createElement("article", "decision-card");
    const hero = createElement("header", "decision-hero");
    const heroCopy = document.createElement("div");
    heroCopy.append(createElement("small", "", "PORTFOLIO MANAGER VERDICT"));

    let headline = "DECISION FILED";
    let narrative = state.decisionText;
    const fields = [];
    if (isPlainObject(decision)) {
      const actionEntry = findObjectEntry(decision, ["action", "recommendation", "decision", "signal", "trade_action", "rating"]);
      if (actionEntry) {
        headline = valueToText(actionEntry[1]);
      }
      const narrativeEntry = findObjectEntry(decision, ["rationale", "reasoning", "analysis", "summary", "content", "plan", "final_decision"]);
      if (narrativeEntry) {
        narrative = valueToText(narrativeEntry[1]);
      }
      Object.entries(decision).forEach(function (entry) {
        if (actionEntry && entry[0] === actionEntry[0]) return;
        if (narrativeEntry && entry[0] === narrativeEntry[0]) return;
        if (entry[1] === null || entry[1] === undefined || typeof entry[1] === "object") return;
        fields.push({ label: humanize(entry[0]), value: valueToText(entry[1]) });
      });
    }

    const headlineNode = createElement("strong", "", headline);
    heroCopy.append(headlineNode);
    const badge = createElement("span", "decision-badge", "FINAL");
    badge.dataset.signal = normalizeStatus(headline);
    hero.append(heroCopy, badge);
    card.append(hero);

    if (fields.length) {
      const list = createElement("dl", "decision-fields");
      fields.slice(0, 12).forEach(function (field) {
        const wrapper = createElement("div", "decision-field");
        wrapper.append(createElement("dt", "", field.label), createElement("dd", "", field.value));
        list.append(wrapper);
      });
      card.append(list);
    }

    card.append(createElement("pre", "decision-narrative", narrative));
    dom.decisionContent.append(card);
  }

  function extractDecision(run) {
    const result = isPlainObject(run.result) ? run.result : {};
    const finalState = run.final_state || result.final_state || (hasKnownReportFields(result) ? result : {});
    const signal = run.decision || run.final_decision ||
      result.decision || result.final_decision || null;
    const reports = isPlainObject(run.reports) ? run.reports : {};
    const narrative = reports.final_trade_decision || run.final_trade_decision ||
      result.final_trade_decision ||
      (isPlainObject(finalState) ? finalState.final_trade_decision : null) ||
      (isPlainObject(finalState.risk_debate_state) ? finalState.risk_debate_state.judge_decision : null);
    if (narrative) {
      if (isPlainObject(signal)) {
        return Object.assign({}, signal, { rationale: narrative });
      }
      return { action: signal || "Decision filed", rationale: narrative };
    }
    return signal || run.final_trade_decision ||
      result.decision || result.final_decision || result.final_trade_decision ||
      (isPlainObject(finalState) ? finalState.final_trade_decision : null) ||
      (isPlainObject(finalState.risk_debate_state) ? finalState.risk_debate_state.judge_decision : null) || null;
  }

  async function loadHistory(date) {
    if (!date) {
      return;
    }
    state.historyDate = date;
    const generation = ++state.historyGeneration;
    updateHistoryDateLabel(date);
    setHistoryLoading();

    try {
      const response = await requestJSON("/api/history?date=" + encodeURIComponent(date));
      if (generation !== state.historyGeneration) {
        return;
      }
      const runs = Array.isArray(response)
        ? response
        : arrayValue(response.runs || response.history || response.items || response.results);
      renderHistory(runs, date);
    } catch (error) {
      if (generation !== state.historyGeneration) {
        return;
      }
      renderHistoryError(error.message);
    }
  }

  function setHistoryLoading() {
    dom.historyRefresh.disabled = true;
    dom.historyList.replaceChildren();
    const loading = createElement("div", "history-loading");
    const spinner = createElement("span", "mini-spinner");
    spinner.setAttribute("aria-hidden", "true");
    loading.append(spinner, createElement("p", "", "Loading archive..."));
    dom.historyList.append(loading);
  }

  function renderHistory(runs, date) {
    dom.historyRefresh.disabled = false;
    dom.historyList.replaceChildren();
    dom.historyCount.textContent = runs.length + (runs.length === 1 ? " RUN" : " RUNS");
    updateHistoryDateLabel(date);

    if (!runs.length) {
      const empty = createElement("div", "history-empty");
      empty.append(
        createElement("span", "status-tag", "NO DATA"),
        createElement("p", "", "No analysis runs were stored for this day.")
      );
      dom.historyList.append(empty);
      return;
    }

    const fragment = document.createDocumentFragment();
    runs.forEach(function (run) {
      const id = getRunId(run);
      const status = cssStatus(normalizeStatus(run.status || "unknown"));
      const button = createElement("button", "history-item");
      button.type = "button";
      button.dataset.runId = id;
      button.setAttribute("aria-label", "Open " + stringValue(run.ticker || run.symbol || "run") + " analysis details");

      const top = createElement("div", "history-item-top");
      const symbol = createElement("strong", "history-symbol", stringValue(run.ticker || run.symbol || run.asset || "—").toUpperCase());
      const tag = createElement("span", "status-tag", displayStatus(status));
      tag.dataset.status = status;
      const time = createElement("time", "history-time", formatEventTime(run.created_at || run.started_at || run.updated_at));
      top.append(symbol, tag, time);

      const meta = createElement("div", "history-item-meta");
      meta.append(
        createElement("span", "", shortId(id || "—")),
        createElement("span", "", stringValue(run.llm_provider || run.provider || "provider —"))
      );

      const summary = createElement("p", "history-item-summary", historySummary(run));
      button.append(top, meta, summary);
      button.addEventListener("click", function () {
        loadHistoryDetail(id, button);
      });
      fragment.append(button);
    });
    dom.historyList.append(fragment);
  }

  function renderHistoryError(message) {
    dom.historyRefresh.disabled = false;
    dom.historyList.replaceChildren();
    dom.historyCount.textContent = "ARCHIVE ERROR";
    const error = createElement("div", "history-error");
    error.append(
      createElement("span", "status-tag", "ERROR"),
      createElement("p", "", message)
    );
    dom.historyList.append(error);
  }

  async function loadHistoryDetail(runId, button) {
    if (!runId) {
      showToast("This history entry has no run ID.", "error");
      return;
    }
    const currentStatus = normalizeStatus(state.currentRun && state.currentRun.status);
    if (state.currentRunId && state.currentRunId !== runId && ACTIVE_STATUSES.has(currentStatus)) {
      showToast("Wait for the active analysis to finish before opening another run.", "error");
      return;
    }
    state.pollGeneration += 1;
    state.currentRunId = runId;
    Array.from(dom.historyList.querySelectorAll(".history-item")).forEach(function (item) {
      const active = item === button;
      item.classList.toggle("active", active);
      if (active) item.setAttribute("aria-current", "true");
      else item.removeAttribute("aria-current");
    });

    setRunLoading(runId);
    try {
      const response = await requestJSON("/api/history/" + encodeURIComponent(runId));
      const run = unwrapRun(response);
      state.currentRun = Object.assign({}, run, { run_id: getRunId(run) || runId });
      state.currentRunId = getRunId(state.currentRun);
      renderRun(state.currentRun);
      activateTab("live", false);

      if (!TERMINAL_STATUSES.has(normalizeStatus(state.currentRun.status))) {
        setLaunchRunActive(true);
        const generation = state.pollGeneration;
        pollRun(state.currentRunId, generation);
      } else {
        setLaunchRunActive(false);
      }
    } catch (error) {
      renderRunError("Unable to load archived run: " + error.message);
      showToast("History detail could not be loaded.", "error");
    }
  }

  function setRunLoading(runId) {
    dom.activeSymbol.textContent = "LOADING ARCHIVED RUN";
    dom.runState.dataset.status = "running";
    dom.runStatusText.textContent = "LOADING";
    dom.progressFill.style.width = "0%";
    dom.runIdLabel.textContent = "RUN " + shortId(runId);
    dom.runPhaseLabel.textContent = "PHASE ARCHIVE RETRIEVAL";
    dom.runProgressLabel.textContent = "—";
    dom.liveCount.textContent = "0";
    dom.reportCount.textContent = "0";
    dom.decisionCount.textContent = "—";
    dom.phaseList.replaceChildren();
    dom.phaseList.append(createElement("div", "rail-empty", "Retrieving agent matrix..."));
    dom.agentTotal.textContent = "— NODES";
    dom.wireFeed.replaceChildren();
    const loading = createElement("div", "workspace-empty");
    loading.append(
      createElement("span", "mini-spinner"),
      createElement("h3", "", "Loading run detail"),
      createElement("p", "", "Retrieving stored events, reports, and decision data.")
    );
    dom.wireFeed.append(loading);
    dom.reportList.replaceChildren(createElement("div", "content-empty", "Loading stored reports..."));
    dom.decisionContent.replaceChildren(createElement("div", "content-empty", "Loading stored decision..."));
    state.reportsText = "";
    state.decisionText = "";
    dom.copyReports.disabled = true;
    dom.copyDecision.disabled = true;
    activateTab("live", false);
  }

  function activateTab(name, focus) {
    const target = dom.tabs.find(function (tab) { return tab.dataset.tab === name; });
    if (!target) return;
    state.activeTab = name;
    dom.tabs.forEach(function (tab) {
      const active = tab === target;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    dom.tabPanels.forEach(function (panel) {
      panel.hidden = panel.id !== "panel-" + name;
    });
    if (focus) target.focus();
  }

  function handleTabKeydown(event) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    let index = dom.tabs.indexOf(event.currentTarget);
    if (event.key === "ArrowRight") index = (index + 1) % dom.tabs.length;
    else if (event.key === "ArrowLeft") index = (index - 1 + dom.tabs.length) % dom.tabs.length;
    else if (event.key === "Home") index = 0;
    else if (event.key === "End") index = dom.tabs.length - 1;
    else return;
    event.preventDefault();
    activateTab(dom.tabs[index].dataset.tab, true);
  }

  function setStorageStatus(storage) {
    let mode = "local";
    let configured = false;
    let message = "Runs are stored by the server's local persistence layer.";

    if (typeof storage === "string") {
      mode = storage.toLowerCase();
      configured = mode === "firebase" || mode === "firestore";
    } else if (isPlainObject(storage)) {
      mode = stringValue(storage.mode || storage.backend || storage.type || (storage.configured ? "firebase" : "local")).toLowerCase();
      configured = Boolean(storage.configured || storage.enabled || storage.connected || storage.available);
      if (storage.message || storage.detail) {
        message = stringValue(storage.message || storage.detail);
      }
    }

    dom.storageDot.className = "status-dot";
    if ((mode === "firebase" || mode === "firestore") && configured) {
      dom.storageDot.classList.add("online");
      dom.storageStatus.textContent = "FIREBASE";
      updateStorageNote("Firebase / Firestore active", message || "Run history is persisted in Firestore.");
    } else if (mode === "unavailable") {
      dom.storageDot.classList.add("error");
      dom.storageStatus.textContent = "UNAVAILABLE";
      updateStorageNote("Storage status unavailable", message);
    } else {
      dom.storageDot.classList.add("local");
      dom.storageStatus.textContent = "LOCAL";
      updateStorageNote("Local storage mode", message || "Add Firebase credentials to persist runs in Firestore.");
    }
  }

  function updateStorageNote(title, message) {
    const icon = createElement("span", "storage-note-icon", "DB");
    icon.setAttribute("aria-hidden", "true");
    const copy = document.createElement("p");
    copy.append(createElement("strong", "", title), createElement("span", "", message));
    dom.storageNote.replaceChildren(icon, copy);
  }

  function setFormEnabled(enabled, subtitle) {
    dom.launchButton.disabled = !enabled;
    dom.launchSubtitle.textContent = subtitle;
  }

  function setLaunchBusy(busy) {
    dom.launchButton.disabled = busy || !state.options;
    dom.launchButton.classList.toggle("is-loading", busy);
    dom.launchButton.setAttribute("aria-busy", String(busy));
    dom.launchSubtitle.textContent = busy ? "Dispatching agents" : "Ready to launch";
  }

  function setLaunchRunActive(active) {
    dom.launchButton.disabled = active || !state.options;
    dom.launchButton.classList.remove("is-loading");
    dom.launchButton.setAttribute("aria-busy", "false");
    dom.launchSubtitle.textContent = active ? "Analysis in progress" : "Ready to launch";
  }

  function showFormMessage(message) {
    dom.formMessage.textContent = message;
    dom.formMessage.hidden = false;
  }

  function clearFormMessage() {
    dom.formMessage.textContent = "";
    dom.formMessage.hidden = true;
  }

  function setSessionState(value) {
    dom.sessionState.textContent = value;
  }

  function startClock() {
    const formatter = new Intl.DateTimeFormat(undefined, {
      hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    });
    const dateFormatter = new Intl.DateTimeFormat(undefined, {
      weekday: "short", day: "2-digit", month: "short", year: "numeric",
    });
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "LOCAL";
    dom.clockZone.textContent = timezone.split("/").pop().replace(/_/g, " ").toUpperCase();

    const update = function () {
      const now = new Date();
      dom.clockTime.textContent = formatter.format(now);
      dom.clockDate.textContent = dateFormatter.format(now).toUpperCase();
    };
    update();
    window.setInterval(update, 1000);
  }

  function shiftHistoryDate(days) {
    const current = parseLocalISODate(dom.historyDate.value || state.historyDate);
    current.setDate(current.getDate() + days);
    const value = toLocalISODate(current);
    const today = toLocalISODate(new Date());
    if (value > today) return;
    dom.historyDate.value = value;
    loadHistory(value);
  }

  function updateHistoryDateLabel(date) {
    const parsed = parseLocalISODate(date);
    dom.historyDateLabel.textContent = new Intl.DateTimeFormat(undefined, {
      day: "2-digit", month: "short", year: "numeric",
    }).format(parsed).toUpperCase();
    dom.historyNext.disabled = date >= toLocalISODate(new Date());
  }

  function saveSettings() {
    if (!state.options) return;
    const analysts = Array.from(dom.analystOptions.querySelectorAll('input[name="analysts"]'))
      .filter(function (input) {
        return input.checked || (
          input.value === "fundamentals" && input.disabled && input.dataset.previousChecked === "true"
        );
      })
      .map(function (input) { return input.value; });
    const settings = {
      ticker: dom.tickerInput.value.trim(),
      analysis_date: dom.analysisDate.value,
      output_language: dom.languageSelect.value,
      custom_language: dom.customLanguageInput.value.trim(),
      research_depth: dom.depthSelect.value,
      analysts: analysts,
      llm_provider: dom.providerSelect.value,
      quick_model_choice: dom.quickModelSelect.value,
      deep_model_choice: dom.deepModelSelect.value,
      custom_quick_model: dom.customQuickModel.value.trim(),
      custom_deep_model: dom.customDeepModel.value.trim(),
      backend_url_choice: dom.backendUrlSelect.hidden ? "" : dom.backendUrlSelect.value,
      backend_url: selectedBackendUrl(),
      custom_backend_url: dom.backendUrlInput.value.trim(),
    };
    const thinkingKey = dom.thinkingControlSelect.dataset.payloadKey;
    if (thinkingKey && dom.thinkingControlSelect.value) {
      settings[thinkingKey] = dom.thinkingControlSelect.value;
    }
    try {
      window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    } catch (_error) {
      // Private browsing or a storage policy may make localStorage unavailable.
    }
  }

  function readSettings() {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(SETTINGS_KEY) || "{}");
      return isPlainObject(parsed) ? parsed : {};
    } catch (_error) {
      return {};
    }
  }

  function selectedModelValue(kind) {
    const select = kind === "quick" ? dom.quickModelSelect : dom.deepModelSelect;
    const custom = kind === "quick" ? dom.customQuickModel : dom.customDeepModel;
    return select.value.toLowerCase() === "custom" ? custom.value.trim() : select.value;
  }

  function selectedBackendUrl() {
    if (dom.backendUrlGroup.hidden) return "";
    if (!dom.backendUrlSelect.hidden) {
      return dom.backendUrlSelect.value.toLowerCase() === "custom"
        ? dom.backendUrlInput.value.trim()
        : dom.backendUrlSelect.value;
    }
    return dom.backendUrlInput.value.trim();
  }

  async function requestJSON(url, options) {
    const requestOptions = Object.assign({
      method: "GET",
      headers: { "Accept": "application/json" },
      credentials: "same-origin",
    }, options || {});
    requestOptions.headers = Object.assign({}, requestOptions.headers);
    if (requestOptions.body) {
      requestOptions.headers["Content-Type"] = "application/json";
    }

    let response;
    try {
      response = await fetch(url, requestOptions);
    } catch (error) {
      throw new Error(navigator.onLine ? "Cannot reach the TradingAgents API." : "Browser is offline.");
    }

    const text = await response.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch (_error) {
        if (!response.ok) {
          throw new Error("Server returned HTTP " + response.status + ".");
        }
        throw new Error("Server returned an invalid JSON response.");
      }
    }

    if (!response.ok) {
      const detail = isPlainObject(data)
        ? data.detail || data.error || data.message
        : null;
      throw new Error(valueToText(detail || ("HTTP " + response.status + " " + response.statusText)));
    }
    return data || {};
  }

  function unwrapRun(payload) {
    if (!isPlainObject(payload)) return {};
    if (isPlainObject(payload.run)) {
      const merged = Object.assign({}, payload.run);
      ["events", "reports", "decision", "error"].forEach(function (key) {
        if (payload[key] !== undefined && merged[key] === undefined) {
          merged[key] = payload[key];
        }
      });
      return merged;
    }
    return payload;
  }

  function fillSelect(select, options, config) {
    const settings = config || {};
    const desired = stringValue(settings.selected);
    select.replaceChildren();
    if (settings.includePlaceholder || (!options.length && settings.placeholder)) {
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = settings.placeholder || "Select an option";
      select.append(placeholder);
    }
    options.forEach(function (item) {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = item.label;
      select.append(option);
    });
    if (desired && options.some(function (item) { return item.id === desired; })) {
      select.value = desired;
    } else if (desired.toLowerCase() === "custom" && options.some(function (item) { return item.id.toLowerCase() === "custom"; })) {
      select.value = options.find(function (item) { return item.id.toLowerCase() === "custom"; }).id;
    }
  }

  function normalizeOptionList(input) {
    const source = normalizeObjectCollection(input);
    return source.map(function (item, index) {
      if (Array.isArray(item)) {
        if (item.length > 1) return { id: stringValue(item[1]), label: stringValue(item[0]) };
        return { id: stringValue(item[0]), label: stringValue(item[0]) };
      }
      if (isPlainObject(item)) {
        const id = stringValue(item.id !== undefined ? item.id : item.value !== undefined ? item.value : item.key !== undefined ? item.key : item.name !== undefined ? item.name : index);
        return {
          id: id,
          label: stringValue(item.label || item.display || item.title || item.description || item.name || id),
        };
      }
      return { id: stringValue(item), label: stringValue(item) };
    }).filter(function (item) { return item.id !== ""; });
  }

  function normalizeObjectCollection(input) {
    if (Array.isArray(input)) return input;
    if (!isPlainObject(input)) return input === undefined || input === null ? [] : [input];
    return Object.entries(input).map(function (entry) {
      if (isPlainObject(entry[1])) {
        return Object.assign({ id: entry[0] }, entry[1]);
      }
      if (Array.isArray(entry[1])) {
        return { id: entry[0], label: humanize(entry[0]), values: entry[1] };
      }
      return { id: entry[0], label: stringValue(entry[1]) };
    });
  }

  function extractProgress(run) {
    let value = run.progress;
    if (isPlainObject(value)) {
      if (value.percent !== undefined) {
        value = value.percent;
      } else if (value.fraction !== undefined) {
        value = Number(value.fraction) * 100;
      } else {
        value = value.value;
      }
    }
    value = Number(value);
    if (Number.isFinite(value)) {
      return Math.max(0, Math.min(100, value));
    }
    const phases = extractPhases(run);
    if (phases.length) {
      const completed = phases.filter(function (phase) {
        return cssStatus(normalizeStatus(phase.status)) === "completed";
      }).length;
      return (completed / phases.length) * 100;
    }
    return normalizeStatus(run.status) === "completed" ? 100 : 0;
  }

  function extractError(run) {
    const error = run.error || run.error_message || run.failure_reason;
    if (!error) return "";
    if (isPlainObject(error)) return valueToText(error.message || error.detail || error);
    return valueToText(error);
  }

  function historySummary(run) {
    const decision = extractDecision(run);
    if (decision) {
      if (isPlainObject(decision)) {
        const entry = findObjectEntry(decision, ["action", "recommendation", "decision", "signal", "summary"]);
        if (entry) return humanize(entry[0]) + ": " + valueToText(entry[1]);
      }
      return valueToText(decision).replace(/\s+/g, " ").slice(0, 100);
    }
    return stringValue(run.current_phase || run.phase || "Open stored analysis");
  }

  function getRunId(run) {
    if (!run) return "";
    return stringValue(run.run_id || run.id || run.uuid || "");
  }

  function normalizeStatus(value) {
    return stringValue(value || "unknown").trim().toLowerCase().replace(/[\s-]+/g, "_");
  }

  function cssStatus(status) {
    if (["in_progress", "processing", "active", "started"].includes(status)) return "running";
    if (["done", "success", "succeeded", "complete"].includes(status)) return "completed";
    if (["failure", "errored"].includes(status)) return "failed";
    if (status === "canceled") return "cancelled";
    return status || "unknown";
  }

  function displayStatus(status) {
    return humanize(cssStatus(status)).toUpperCase();
  }

  function hasKnownReportFields(value) {
    if (!isPlainObject(value)) return false;
    return ["market_report", "sentiment_report", "news_report", "fundamentals_report", "trader_investment_plan", "risk_debate_state"]
      .some(function (key) { return value[key] !== undefined; });
  }

  function findObjectEntry(object, keys) {
    if (!isPlainObject(object)) return null;
    const actualKeys = Object.keys(object);
    for (const key of keys) {
      const found = actualKeys.find(function (actual) { return actual.toLowerCase() === key; });
      if (found !== undefined) return [found, object[found]];
    }
    return null;
  }

  function valueToText(value) {
    if (value === null || value === undefined) return "";
    if (typeof value === "string") return value;
    if (typeof value === "number" || typeof value === "boolean") return String(value);
    try {
      return JSON.stringify(value, null, 2);
    } catch (_error) {
      return String(value);
    }
  }

  function humanize(value) {
    return stringValue(value)
      .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
      .replace(/[_-]+/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .replace(/\b\w/g, function (letter) { return letter.toUpperCase(); });
  }

  function stringValue(value) {
    return value === null || value === undefined ? "" : String(value);
  }

  function arrayValue(value) {
    if (Array.isArray(value)) return value;
    if (value === null || value === undefined || value === "") return [];
    return [value];
  }

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function pick(object, keys) {
    if (!isPlainObject(object)) return "";
    for (const key of keys) {
      if (object[key] !== undefined && object[key] !== null) return object[key];
    }
    return "";
  }

  function createElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function toCamelCase(value) {
    return value.replace(/-([a-z])/g, function (_match, letter) { return letter.toUpperCase(); });
  }

  function shortId(value) {
    const id = stringValue(value);
    return id.length > 12 ? id.slice(0, 8) + "…" + id.slice(-3) : id;
  }

  function countWords(value) {
    const matches = stringValue(value).trim().match(/\S+/g);
    return matches ? matches.length : 0;
  }

  function formatEventTime(value) {
    if (!value) return "--:--:--";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return stringValue(value).slice(0, 8);
    }
    return new Intl.DateTimeFormat(undefined, {
      hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    }).format(date);
  }

  function toLocalISODate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return year + "-" + month + "-" + day;
  }

  function parseLocalISODate(value) {
    const parts = stringValue(value).split("-").map(Number);
    if (parts.length !== 3 || parts.some(Number.isNaN)) return new Date();
    return new Date(parts[0], parts[1] - 1, parts[2]);
  }

  function showToast(message, type) {
    const toast = createElement("div", "toast " + (type || ""), message);
    dom.toastRegion.append(toast);
    window.setTimeout(function () {
      toast.remove();
    }, 4200);
  }

  async function copyText(value, successMessage) {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      showToast(successMessage, "success");
    } catch (_error) {
      showToast("Clipboard access was denied by the browser.", "error");
    }
  }
})();
