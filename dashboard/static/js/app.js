/**
 * Offshore ESP SCADA Mission Control - Refactored Application Engine
 * High-performance, modular ES6+ architecture with interactive downhole wellbore
 * visualization, multi-view orchestration, and strict G10 acceptance compliance.
 */

(function () {
  "use strict";

  // System Configuration & Engineering Baselines
  const CONFIG = {
    POLL_INTERVAL_SECONDS: 10,
    UNAVAILABLE_THRESHOLD_SECONDS: 45,
    MAX_SPARKLINE_POINTS: 24,
    API_ENDPOINTS: {
      PUMPS: "/api/v1/pumps",
      KPIS: "/api/v1/kpis/latest",
      HEALTH: "/api/v1/health"
    },
    STORAGE_KEYS: {
      AUDIO_MUTED: "esp_dashboard_audio_muted",
      ACTIVE_VIEW: "esp_dashboard_active_view",
      SELECTED_WELL: "esp_dashboard_selected_well"
    },
    BASELINES: {
      FLOW_NOMINAL: 105.0,  // m3/day design baseline
      TEMP_NOMINAL: 78.0,   // deg C baseline
      CURR_NOMINAL: 38.0,   // A baseline
      VIB_NOMINAL: 2.1      // mm/s baseline
    },
    THRESHOLDS: {
      FLOW_LOW_ALARM: 60.0, // m3/day (triggers low flow)
      TEMP_WARN: 90.0,      // deg C
      TEMP_OVERHEAT: 120.0, // deg C (triggers overheat trip)
      CURRENT_ALARM: 75.0,  // A
      VIBRATION_ALARM: 12.0 // mm/s
    }
  };

  // Central Application State
  const state = {
    mode: "fixture",
    systemState: "fresh",
    activeView: localStorage.getItem(CONFIG.STORAGE_KEYS.ACTIVE_VIEW) || "fleet",
    activeFilter: "all",
    selectedWellId: localStorage.getItem(CONFIG.STORAGE_KEYS.SELECTED_WELL) || "ESP-102",
    lastSuccessTime: null,
    inFlightRequest: false,
    pollTimer: null,
    secondsUntilNextPoll: CONFIG.POLL_INTERVAL_SECONDS,
    isMuted: localStorage.getItem(CONFIG.STORAGE_KEYS.AUDIO_MUTED) === "true",
    lastLatencyMs: 0,
    pumpsData: [],
    kpisData: null,
    healthData: null,
    history: {
      "ESP-101": { flow: [], temp: [] },
      "ESP-102": { flow: [], temp: [] },
      "ESP-103": { flow: [], temp: [] }
    }
  };

  // Web Audio Alert Synthesizer (Offline, zero audio assets required)
  class SoundManager {
    constructor() {
      this.ctx = null;
    }

    init() {
      if (!this.ctx && (window.AudioContext || window.webkitAudioContext)) {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        this.ctx = new AudioCtx();
      }
    }

    playAlert(type = "warning") {
      if (state.isMuted) return;
      try {
        this.init();
        if (!this.ctx) return;
        if (this.ctx.state === "suspended") {
          this.ctx.resume();
        }

        const now = this.ctx.currentTime;
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();

        osc.type = "sine";
        gain.connect(this.ctx.destination);
        osc.connect(gain);

        if (type === "critical") {
          // Dual warning tone: 784Hz -> 523Hz
          osc.frequency.setValueAtTime(784, now);
          osc.frequency.setValueAtTime(523, now + 0.15);
          gain.gain.setValueAtTime(0.18, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
          osc.start(now);
          osc.stop(now + 0.45);
        } else {
          // Soft notification tone: 520Hz -> 659Hz
          osc.frequency.setValueAtTime(520, now);
          osc.frequency.setValueAtTime(659, now + 0.12);
          gain.gain.setValueAtTime(0.12, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
          osc.start(now);
          osc.stop(now + 0.35);
        }
      } catch (err) {
        console.warn("Audio chime unavailable:", err);
      }
    }
  }

  const sound = new SoundManager();

  // API Client with Single-In-Flight Guard (G10 specification)
  class ApiClient {
    constructor() {
      this.controller = null;
    }

    async fetchPumps() {
      if (state.inFlightRequest) {
        return null;
      }

      state.inFlightRequest = true;
      this.controller = new AbortController();
      const startTime = performance.now();

      try {
        const res = await fetch(CONFIG.API_ENDPOINTS.PUMPS, {
          signal: this.controller.signal,
          headers: { "Accept": "application/json" }
        });

        state.lastLatencyMs = Math.round(performance.now() - startTime);

        if (res.status === 503) {
          return { error: "dependency_unavailable", status: 503 };
        }
        if (!res.ok) {
          return { error: "http_error", status: res.status };
        }

        const data = await res.json();
        return { success: true, data };
      } catch (err) {
        if (err.name === "AbortError") return null;
        return { error: "network_failure", message: err.message };
      } finally {
        state.inFlightRequest = false;
        this.controller = null;
      }
    }

    async fetchKpis() {
      try {
        const res = await fetch(CONFIG.API_ENDPOINTS.KPIS, { headers: { "Accept": "application/json" } });
        if (!res.ok) return null;
        return await res.json();
      } catch (err) {
        return null;
      }
    }

    async fetchHealth() {
      try {
        const res = await fetch(CONFIG.API_ENDPOINTS.HEALTH, { headers: { "Accept": "application/json" } });
        if (!res.ok) return null;
        return await res.json();
      } catch (err) {
        return null;
      }
    }
  }

  const api = new ApiClient();

  // Pure SVG Sparkline & Dual-Trend Curve Generator
  class SvgChartGenerator {
    static renderSparkline(points, minVal, maxVal, color = "#06b6d4") {
      if (!points || points.length < 2) {
        return `<svg viewBox="0 0 200 40" class="sparkline-svg-container"><line x1="0" y1="20" x2="200" y2="20" stroke="#334155" stroke-dasharray="4" /></svg>`;
      }

      const w = 200;
      const h = 40;
      const pad = 4;
      const range = (maxVal - minVal) || 1;

      const coords = points.map((val, idx) => {
        const x = pad + (idx / (points.length - 1)) * (w - 2 * pad);
        const norm = (val - minVal) / range;
        const y = h - pad - norm * (h - 2 * pad);
        return [x, y];
      });

      // Generate smooth cubic bezier SVG path
      let d = `M ${coords[0][0].toFixed(1)} ${coords[0][1].toFixed(1)}`;
      for (let i = 0; i < coords.length - 1; i++) {
        const curr = coords[i];
        const next = coords[i + 1];
        const cpX = (curr[0] + next[0]) / 2;
        d += ` C ${cpX.toFixed(1)} ${curr[1].toFixed(1)}, ${cpX.toFixed(1)} ${next[1].toFixed(1)}, ${next[0].toFixed(1)} ${next[1].toFixed(1)}`;
      }

      // Area fill
      const areaD = `${d} L ${coords[coords.length - 1][0]} ${h} L ${coords[0][0]} ${h} Z`;

      return `
        <svg viewBox="0 0 ${w} ${h}" style="width: 100%; height: 100%; display: block; overflow: visible;">
          <defs>
            <linearGradient id="grad-${color.replace('#','')}" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="${color}" stop-opacity="0.3"/>
              <stop offset="100%" stop-color="${color}" stop-opacity="0.0"/>
            </linearGradient>
          </defs>
          <path d="${areaD}" fill="url(#grad-${color.replace('#','')})" />
          <path d="${d}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      `;
    }

    static renderDualTrend(flowPoints, tempPoints) {
      const w = 600;
      const h = 140;
      const padX = 20;
      const padY = 15;

      if (!flowPoints || flowPoints.length < 2) {
        return `<svg viewBox="0 0 ${w} ${h}" class="dual-trend-svg"><text x="300" y="70" fill="#64748b" text-anchor="middle" font-family="monospace">Collecting trend observations...</text></svg>`;
      }

      const minFlow = Math.min(...flowPoints, 30);
      const maxFlow = Math.max(...flowPoints, 120);
      const minTemp = Math.min(...tempPoints, 60);
      const maxTemp = Math.max(...tempPoints, 130);

      const flowCoords = flowPoints.map((v, i) => {
        const x = padX + (i / (flowPoints.length - 1)) * (w - 2 * padX);
        const y = h - padY - ((v - minFlow) / (maxFlow - minFlow || 1)) * (h - 2 * padY);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      });

      const tempCoords = tempPoints.map((v, i) => {
        const x = padX + (i / (tempPoints.length - 1)) * (w - 2 * padX);
        const y = h - padY - ((v - minTemp) / (maxTemp - minTemp || 1)) * (h - 2 * padY);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      });

      return `
        <svg viewBox="0 0 ${w} ${h}" style="width: 100%; height: 100%; display: block;">
          <!-- Grid Lines -->
          <line x1="${padX}" y1="${padY}" x2="${w - padX}" y2="${padY}" stroke="#1e293b" stroke-dasharray="4"/>
          <line x1="${padX}" y1="${h/2}" x2="${w - padX}" y2="${h/2}" stroke="#1e293b" stroke-dasharray="4"/>
          <line x1="${padX}" y1="${h - padY}" x2="${w - padX}" y2="${h - padY}" stroke="#1e293b"/>

          <!-- Flow Curve (Cyan) -->
          <path d="M ${flowCoords.join(' L ')}" fill="none" stroke="#06b6d4" stroke-width="2.5" stroke-linecap="round"/>

          <!-- Temp Curve (Amber) -->
          <path d="M ${tempCoords.join(' L ')}" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-dasharray="4 2"/>
        </svg>
      `;
    }
  }

  // DOM Renderer (Selective In-Place Updates)
  class DOMRenderer {
    constructor() {
      this.initElements();
      this.bindTabNavigation();
      this.bindFilterControls();
      this.bindWellboreSelector();
      this.bindSnapshotExport();
    }

    initElements() {
      this.els = {
        clock: document.getElementById("telemetry-clock"),
        systemPill: document.getElementById("system-status-pill"),
        systemStatusText: document.getElementById("system-status-text"),
        staleBanner: document.getElementById("stale-banner"),
        staleMessage: document.getElementById("stale-message"),
        anomalyBanner: document.getElementById("anomaly-banner"),
        anomalyMessage: document.getElementById("anomaly-message"),
        fleetActiveCount: document.getElementById("fleet-active-count"),
        fleetTotalFlow: document.getElementById("fleet-total-flow"),
        fleetMeanTemp: document.getElementById("fleet-mean-temp"),
        batchQualityBadge: document.getElementById("batch-quality-badge"),
        curatedRunSubtext: document.getElementById("curated-run-subtext"),
        pumpsContainer: document.getElementById("pumps-grid-container"),
        pollRingCircle: document.getElementById("poll-ring-circle"),
        pollCountdownText: document.getElementById("poll-countdown-text"),
        btnRefresh: document.getElementById("btn-refresh"),
        btnAudioMute: document.getElementById("btn-audio-mute"),
        soundWaveBars: document.getElementById("sound-wave-bars"),
        audioBtnLabel: document.getElementById("audio-btn-label"),
        // Inspector elements
        inspectorWellTitle: document.getElementById("inspector-well-title"),
        inspectorScenarioTitle: document.getElementById("inspector-scenario-title"),
        inspectorStatusBadge: document.getElementById("inspector-status-badge"),
        inspectorSeverityBadge: document.getElementById("inspector-severity-badge"),
        inspectorFlowVal: document.getElementById("inspector-flow-val"),
        inspectorFlowBar: document.getElementById("inspector-flow-bar"),
        inspectorTempVal: document.getElementById("inspector-temp-val"),
        inspectorTempBar: document.getElementById("inspector-temp-bar"),
        inspectorCurrVal: document.getElementById("inspector-curr-val"),
        inspectorCurrBar: document.getElementById("inspector-curr-bar"),
        inspectorVibVal: document.getElementById("inspector-vib-val"),
        inspectorVibBar: document.getElementById("inspector-vib-bar"),
        schematicFlowVal: document.getElementById("schematic-flow-val"),
        schematicTempVal: document.getElementById("schematic-temp-val"),
        schematicVibVal: document.getElementById("schematic-vib-val"),
        schematicPumpSection: document.getElementById("schematic-pump-section"),
        schematicMotorSection: document.getElementById("schematic-motor-section"),
        inspectorTrendChart: document.getElementById("inspector-trend-chart"),
        // Lake elements
        pipelinePubId: document.getElementById("pipeline-pub-id"),
        batchPubTimestamp: document.getElementById("batch-pub-timestamp"),
        badgeSilverCount: document.getElementById("badge-silver-count"),
        badgeGoldCount: document.getElementById("badge-gold-count"),
        lakeTableBody: document.getElementById("lake-table-body"),
        athenaSqlSnippet: document.getElementById("athena-sql-snippet"),
        // Health elements
        healthPumpHits: document.getElementById("health-pump-hits"),
        healthPumpRatio: document.getElementById("health-pump-ratio"),
        healthPubHits: document.getElementById("health-pub-hits"),
        healthPubRatio: document.getElementById("health-pub-ratio"),
        healthLatencyVal: document.getElementById("health-latency-val")
      };
    }

    bindTabNavigation() {
      const tabs = document.querySelectorAll(".nav-tab-btn");
      tabs.forEach(tab => {
        tab.addEventListener("click", () => {
          const targetView = tab.dataset.view;
          this.switchView(targetView);
        });
      });
    }

    switchView(viewName) {
      state.activeView = viewName;
      localStorage.setItem(CONFIG.STORAGE_KEYS.ACTIVE_VIEW, viewName);

      document.querySelectorAll(".nav-tab-btn").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.view === viewName);
      });

      document.querySelectorAll(".view-panel").forEach(panel => {
        panel.classList.toggle("active", panel.id === `view-${viewName}`);
      });

      if (viewName === "inspector") {
        this.renderInspectorView();
      }
    }

    bindFilterControls() {
      const filterBtns = document.querySelectorAll(".filter-pill-btn");
      filterBtns.forEach(btn => {
        btn.addEventListener("click", () => {
          filterBtns.forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
          state.activeFilter = btn.dataset.filter;
          this.applyFilter();
        });
      });
    }

    applyFilter() {
      const cards = document.querySelectorAll(".esp-card");
      cards.forEach(card => {
        const severity = card.dataset.severity || "normal";
        if (state.activeFilter === "all") {
          card.style.display = "flex";
        } else if (state.activeFilter === "normal") {
          card.style.display = severity === "normal" ? "flex" : "none";
        } else if (state.activeFilter === "alerts") {
          card.style.display = severity !== "normal" ? "flex" : "none";
        }
      });
    }

    bindWellboreSelector() {
      const select = document.getElementById("schematic-well-select");
      if (select) {
        select.value = state.selectedWellId;
        select.addEventListener("change", (e) => {
          state.selectedWellId = e.target.value;
          localStorage.setItem(CONFIG.STORAGE_KEYS.SELECTED_WELL, state.selectedWellId);
          this.renderInspectorView();
        });
      }
    }

    bindSnapshotExport() {
      const btn = document.getElementById("btn-export-snapshot");
      if (btn) {
        btn.addEventListener("click", () => {
          const snapshot = {
            exported_at: new Date().toISOString(),
            system_state: state.systemState,
            pumps: state.pumpsData,
            kpis: state.kpisData,
            health: state.healthData
          };
          const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `esp-surveillance-snapshot-${Date.now()}.json`;
          a.click();
          URL.revokeObjectURL(url);
        });
      }
    }

    updateClock() {
      const now = new Date();
      if (this.els.clock) {
        this.els.clock.textContent = `${now.toISOString().replace("T", " ").substring(0, 19)} UTC`;
      }
    }

    updateCountdown(secondsLeft) {
      if (!this.els.pollRingCircle || !this.els.pollCountdownText) return;
      this.els.pollCountdownText.textContent = `${secondsLeft}s`;
      const radius = 7;
      const circumference = 2 * Math.PI * radius;
      const offset = circumference - (secondsLeft / CONFIG.POLL_INTERVAL_SECONDS) * circumference;
      this.els.pollRingCircle.style.strokeDasharray = `${circumference} ${circumference}`;
      this.els.pollRingCircle.style.strokeDashoffset = offset;
    }

    setSystemState(status, message = null) {
      state.systemState = status;
      if (!this.els.systemPill || !this.els.systemStatusText) return;

      this.els.systemPill.className = `system-status-pill ${status}`;
      if (status === "fresh") {
        this.els.systemStatusText.textContent = "Telemetry Live";
        if (this.els.staleBanner) this.els.staleBanner.style.display = "none";
      } else if (status === "stale") {
        this.els.systemStatusText.textContent = "Telemetry Stale";
        if (this.els.staleBanner) {
          this.els.staleBanner.className = "alert-callout stale";
          this.els.staleBanner.style.display = "flex";
          this.els.staleMessage.textContent = message || "Live stream disconnected. Preserving last observations.";
        }
      } else if (status === "unavailable") {
        this.els.systemStatusText.textContent = "Service Unavailable";
        if (this.els.staleBanner) {
          this.els.staleBanner.className = "alert-callout unavailable";
          this.els.staleBanner.style.display = "flex";
          this.els.staleMessage.textContent = message || "Dependency unavailable (>45s). Contact ops.";
        }
      }
    }

    renderFleetKpis(pumps) {
      if (!pumps || pumps.length === 0) return;

      const runningCount = pumps.filter(p => p.status === "RUNNING").length;
      if (this.els.fleetActiveCount) {
        this.els.fleetActiveCount.textContent = `${runningCount} / ${pumps.length}`;
      }

      const totalFlow = pumps.reduce((acc, p) => acc + (p.flow_rate || 0), 0);
      if (this.els.fleetTotalFlow) {
        this.els.fleetTotalFlow.textContent = `${totalFlow.toFixed(1)} m³/d`;
      }

      const validTemps = pumps.filter(p => p.motor_temperature != null).map(p => p.motor_temperature);
      const meanTemp = validTemps.length > 0 ? (validTemps.reduce((a, b) => a + b, 0) / validTemps.length) : 0;
      if (this.els.fleetMeanTemp) {
        this.els.fleetMeanTemp.textContent = `${meanTemp.toFixed(1)} °C`;
      }
    }

    renderPumpsGrid(pumps, dataAgeSeconds) {
      if (!this.els.pumpsContainer || !pumps) return;

      pumps.forEach(pump => {
        // Record rolling history
        if (!state.history[pump.esp_id]) {
          state.history[pump.esp_id] = { flow: [], temp: [] };
        }
        const hist = state.history[pump.esp_id];
        if (pump.flow_rate != null) {
          hist.flow.push(pump.flow_rate);
          if (hist.flow.length > CONFIG.MAX_SPARKLINE_POINTS) hist.flow.shift();
        }
        if (pump.motor_temperature != null) {
          hist.temp.push(pump.motor_temperature);
          if (hist.temp.length > CONFIG.MAX_SPARKLINE_POINTS) hist.temp.shift();
        }

        let card = document.getElementById(`esp-card-${pump.esp_id}`);
        if (!card) {
          card = this.createEspCard(pump);
          this.els.pumpsContainer.appendChild(card);
        }

        this.updateEspCard(card, pump, dataAgeSeconds, hist);
      });

      this.applyFilter();
    }

    createEspCard(pump) {
      const card = document.createElement("div");
      card.id = `esp-card-${pump.esp_id}`;
      card.className = "esp-card";
      card.dataset.pump = pump.esp_id;

      card.innerHTML = `
        <div class="esp-card-header">
          <div class="esp-card-identity">
            <div class="well-symbol">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="12 2 2 22 22 22 12 2"></polygon>
                <line x1="12" y1="6" x2="12" y2="18"></line>
              </svg>
            </div>
            <div class="well-name-group">
              <h3 class="well-name-title">${pump.esp_id}</h3>
              <span class="well-scenario-label" id="scenario-${pump.esp_id}">Scenario: ${pump.scenario || "normal"}</span>
            </div>
          </div>
          <div class="esp-card-badges">
            <span class="state-badge ${pump.status}" id="status-badge-${pump.esp_id}">${pump.status}</span>
            <span class="severity-tag ${pump.severity}" id="severity-tag-${pump.esp_id}">${pump.severity}</span>
          </div>
        </div>

        <div class="card-anomaly-callout" id="anomaly-callout-${pump.esp_id}" style="display: none;">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <span id="anomaly-text-${pump.esp_id}"></span>
        </div>

        <div class="esp-gauges-grid">
          <!-- Flow Rate Dial -->
          <div class="dial-gauge-card">
            <div class="dial-gauge-header">
              <span class="dial-gauge-title">Liquid Flow</span>
              <span class="dial-gauge-unit">m³/d</span>
            </div>
            <div class="dial-gauge-reading">
              <span class="dial-gauge-val" id="val-flow-${pump.esp_id}">--</span>
              <span class="dial-delta-pill normal" id="delta-flow-${pump.esp_id}">0.0%</span>
            </div>
            <div class="dial-meter-track">
              <div class="dial-meter-bar nominal" id="bar-flow-${pump.esp_id}" style="width: 0%;"></div>
            </div>
          </div>

          <!-- Motor Temperature Dial -->
          <div class="dial-gauge-card">
            <div class="dial-gauge-header">
              <span class="dial-gauge-title">Motor Temp</span>
              <span class="dial-gauge-unit">°C</span>
            </div>
            <div class="dial-gauge-reading">
              <span class="dial-gauge-val" id="val-temp-${pump.esp_id}">--</span>
              <span class="dial-delta-pill normal" id="delta-temp-${pump.esp_id}">Norm</span>
            </div>
            <div class="dial-meter-track">
              <div class="dial-meter-bar nominal" id="bar-temp-${pump.esp_id}" style="width: 0%;"></div>
            </div>
          </div>

          <!-- Motor Phase Current Dial -->
          <div class="dial-gauge-card">
            <div class="dial-gauge-header">
              <span class="dial-gauge-title">Current</span>
              <span class="dial-gauge-unit">A</span>
            </div>
            <div class="dial-gauge-reading">
              <span class="dial-gauge-val" id="val-curr-${pump.esp_id}">--</span>
              <span class="dial-delta-pill normal" id="delta-curr-${pump.esp_id}">Norm</span>
            </div>
            <div class="dial-meter-track">
              <div class="dial-meter-bar nominal" id="bar-curr-${pump.esp_id}" style="width: 0%;"></div>
            </div>
          </div>

          <!-- Vibration Amplitude Dial -->
          <div class="dial-gauge-card">
            <div class="dial-gauge-header">
              <span class="dial-gauge-title">Vibration</span>
              <span class="dial-gauge-unit">mm/s</span>
            </div>
            <div class="dial-gauge-reading">
              <span class="dial-gauge-val" id="val-vib-${pump.esp_id}">--</span>
              <span class="dial-delta-pill normal" id="delta-vib-${pump.esp_id}">Norm</span>
            </div>
            <div class="dial-meter-track">
              <div class="dial-meter-bar nominal" id="bar-vib-${pump.esp_id}" style="width: 0%;"></div>
            </div>
          </div>
        </div>

        <div class="esp-sparkline-box">
          <div class="sparkline-top">
            <span>Flow Rolling Trend</span>
            <span id="sparkline-range-${pump.esp_id}">--</span>
          </div>
          <div class="sparkline-svg-container" id="sparkline-svg-${pump.esp_id}"></div>
        </div>

        <div class="esp-card-footer">
          <div class="observation-stamp">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            <span id="age-${pump.esp_id}">Observed: --</span>
          </div>
          <button class="btn-well-inspect" data-pump="${pump.esp_id}">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
            Inspect Wellbore
          </button>
        </div>
      `;

      card.querySelector(".btn-well-inspect").addEventListener("click", () => {
        state.selectedWellId = pump.esp_id;
        const sel = document.getElementById("schematic-well-select");
        if (sel) sel.value = pump.esp_id;
        this.switchView("inspector");
      });

      return card;
    }

    updateEspCard(card, pump, dataAgeSeconds, hist) {
      card.className = `esp-card severity-${pump.severity || "normal"}`;
      card.dataset.severity = pump.severity || "normal";

      // Status & Severity Badges
      const statusBadge = document.getElementById(`status-badge-${pump.esp_id}`);
      if (statusBadge) {
        statusBadge.className = `state-badge ${pump.status}`;
        statusBadge.textContent = pump.status;
      }

      const severityTag = document.getElementById(`severity-tag-${pump.esp_id}`);
      if (severityTag) {
        severityTag.className = `severity-tag ${pump.severity}`;
        severityTag.textContent = pump.severity;
      }

      // Anomaly Callout
      const callout = document.getElementById(`anomaly-callout-${pump.esp_id}`);
      const calloutText = document.getElementById(`anomaly-text-${pump.esp_id}`);
      if (callout && calloutText) {
        if (pump.finding) {
          callout.style.display = "flex";
          callout.className = `card-anomaly-callout ${pump.severity === "critical" ? "critical" : ""}`;
          calloutText.textContent = pump.finding;
        } else {
          callout.style.display = "none";
        }
      }

      // Flow Gauge & Delta vs 105 m3/d baseline
      const valFlow = document.getElementById(`val-flow-${pump.esp_id}`);
      const barFlow = document.getElementById(`bar-flow-${pump.esp_id}`);
      const deltaFlow = document.getElementById(`delta-flow-${pump.esp_id}`);
      if (valFlow && barFlow && deltaFlow) {
        const flow = pump.flow_rate != null ? pump.flow_rate : 0;
        valFlow.textContent = flow.toFixed(1);
        const pct = Math.min(100, Math.max(0, (flow / 140) * 100));
        barFlow.style.width = `${pct}%`;

        const deltaPct = ((flow - CONFIG.BASELINES.FLOW_NOMINAL) / CONFIG.BASELINES.FLOW_NOMINAL) * 100;
        deltaFlow.textContent = `${deltaPct >= 0 ? "+" : ""}${deltaPct.toFixed(0)}%`;

        if (flow < CONFIG.THRESHOLDS.FLOW_LOW_ALARM) {
          barFlow.className = "dial-meter-bar warning";
          deltaFlow.className = "dial-delta-pill warning";
        } else {
          barFlow.className = "dial-meter-bar nominal";
          deltaFlow.className = "dial-delta-pill normal";
        }
      }

      // Temp Gauge & Delta vs 78 C baseline
      const valTemp = document.getElementById(`val-temp-${pump.esp_id}`);
      const barTemp = document.getElementById(`bar-temp-${pump.esp_id}`);
      const deltaTemp = document.getElementById(`delta-temp-${pump.esp_id}`);
      if (valTemp && barTemp && deltaTemp) {
        const temp = pump.motor_temperature != null ? pump.motor_temperature : 0;
        valTemp.textContent = temp.toFixed(1);
        const pct = Math.min(100, Math.max(0, (temp / 140) * 100));
        barTemp.style.width = `${pct}%`;

        const deltaDeg = temp - CONFIG.BASELINES.TEMP_NOMINAL;
        deltaTemp.textContent = `${deltaDeg >= 0 ? "+" : ""}${deltaDeg.toFixed(0)}°C`;

        if (temp >= CONFIG.THRESHOLDS.TEMP_OVERHEAT) {
          barTemp.className = "dial-meter-bar critical";
          deltaTemp.className = "dial-delta-pill critical";
        } else if (temp >= CONFIG.THRESHOLDS.TEMP_WARN) {
          barTemp.className = "dial-meter-bar warning";
          deltaTemp.className = "dial-delta-pill warning";
        } else {
          barTemp.className = "dial-meter-bar nominal";
          deltaTemp.className = "dial-delta-pill normal";
        }
      }

      // Current
      const valCurr = document.getElementById(`val-curr-${pump.esp_id}`);
      const barCurr = document.getElementById(`bar-curr-${pump.esp_id}`);
      if (valCurr && barCurr) {
        const curr = pump.motor_current != null ? pump.motor_current : 0;
        valCurr.textContent = curr.toFixed(1);
        const pct = Math.min(100, Math.max(0, (curr / 90) * 100));
        barCurr.style.width = `${pct}%`;
        barCurr.className = `dial-meter-bar ${curr > CONFIG.THRESHOLDS.CURRENT_ALARM ? "critical" : "nominal"}`;
      }

      // Vibration
      const valVib = document.getElementById(`val-vib-${pump.esp_id}`);
      const barVib = document.getElementById(`bar-vib-${pump.esp_id}`);
      if (valVib && barVib) {
        const vib = pump.vibration != null ? pump.vibration : 0;
        valVib.textContent = vib.toFixed(2);
        const pct = Math.min(100, Math.max(0, (vib / 15) * 100));
        barVib.style.width = `${pct}%`;
        barVib.className = `dial-meter-bar ${vib > CONFIG.THRESHOLDS.VIBRATION_ALARM ? "critical" : "nominal"}`;
      }

      // Sparkline SVG
      const sparkContainer = document.getElementById(`sparkline-svg-${pump.esp_id}`);
      const rangeEl = document.getElementById(`sparkline-range-${pump.esp_id}`);
      if (sparkContainer && hist.flow.length > 0) {
        const minF = Math.floor(Math.min(...hist.flow));
        const maxF = Math.ceil(Math.max(...hist.flow));
        if (rangeEl) rangeEl.textContent = `${minF} - ${maxF} m³/d`;
        sparkContainer.innerHTML = SvgChartGenerator.renderSparkline(hist.flow, minF, maxF, "#06b6d4");
      }

      // Age Text
      const ageEl = document.getElementById(`age-${pump.esp_id}`);
      if (ageEl) {
        ageEl.textContent = `Observed: ${dataAgeSeconds != null ? dataAgeSeconds : 0}s ago`;
      }
    }

    renderInspectorView() {
      const well = state.pumpsData.find(p => p.esp_id === state.selectedWellId);
      if (!well) return;

      if (this.els.inspectorWellTitle) this.els.inspectorWellTitle.textContent = `Well ${well.esp_id} Downhole Diagnostics`;
      if (this.els.inspectorScenarioTitle) this.els.inspectorScenarioTitle.textContent = `Operating Scenario: ${well.scenario || "normal"}`;

      if (this.els.inspectorStatusBadge) {
        this.els.inspectorStatusBadge.className = `state-badge ${well.status}`;
        this.els.inspectorStatusBadge.textContent = well.status;
      }
      if (this.els.inspectorSeverityBadge) {
        this.els.inspectorSeverityBadge.className = `severity-tag ${well.severity}`;
        this.els.inspectorSeverityBadge.textContent = well.severity;
      }

      // Values & Gauges
      if (this.els.inspectorFlowVal) this.els.inspectorFlowVal.textContent = well.flow_rate != null ? well.flow_rate.toFixed(1) : "--";
      if (this.els.inspectorFlowBar) {
        const pct = Math.min(100, Math.max(0, ((well.flow_rate || 0) / 140) * 100));
        this.els.inspectorFlowBar.style.width = `${pct}%`;
        this.els.inspectorFlowBar.className = `dial-meter-bar ${(well.flow_rate || 0) < CONFIG.THRESHOLDS.FLOW_LOW_ALARM ? "warning" : "nominal"}`;
      }

      if (this.els.inspectorTempVal) this.els.inspectorTempVal.textContent = well.motor_temperature != null ? well.motor_temperature.toFixed(1) : "--";
      if (this.els.inspectorTempBar) {
        const pct = Math.min(100, Math.max(0, ((well.motor_temperature || 0) / 140) * 100));
        this.els.inspectorTempBar.style.width = `${pct}%`;
        const isTrip = (well.motor_temperature || 0) >= CONFIG.THRESHOLDS.TEMP_OVERHEAT;
        const isWarn = (well.motor_temperature || 0) >= CONFIG.THRESHOLDS.TEMP_WARN;
        this.els.inspectorTempBar.className = `dial-meter-bar ${isTrip ? "critical" : isWarn ? "warning" : "nominal"}`;
      }

      if (this.els.inspectorCurrVal) this.els.inspectorCurrVal.textContent = well.motor_current != null ? well.motor_current.toFixed(1) : "--";
      if (this.els.inspectorVibVal) this.els.inspectorVibVal.textContent = well.vibration != null ? well.vibration.toFixed(2) : "--";

      // Schematic Labels
      if (this.els.schematicFlowVal) this.els.schematicFlowVal.textContent = `${well.flow_rate != null ? well.flow_rate.toFixed(1) : "--"} m³/d`;
      if (this.els.schematicTempVal) this.els.schematicTempVal.textContent = `${well.motor_temperature != null ? well.motor_temperature.toFixed(1) : "--"} °C`;
      if (this.els.schematicVibVal) this.els.schematicVibVal.textContent = `${well.vibration != null ? well.vibration.toFixed(2) : "--"} mm/s`;

      // Visual Anomaly Highlight on Schematic
      if (this.els.schematicPumpSection) {
        const isFlowAbnormal = (well.flow_rate || 0) < CONFIG.THRESHOLDS.FLOW_LOW_ALARM;
        this.els.schematicPumpSection.querySelector("rect").setAttribute("stroke", isFlowAbnormal ? "#f59e0b" : "#06b6d4");
      }
      if (this.els.schematicMotorSection) {
        const isTempAbnormal = (well.motor_temperature || 0) > CONFIG.THRESHOLDS.TEMP_WARN;
        this.els.schematicMotorSection.querySelector("rect").setAttribute("stroke", isTempAbnormal ? "#ef4444" : "#f59e0b");
      }

      // Dual-Trend Chart
      const hist = state.history[well.esp_id];
      if (this.els.inspectorTrendChart && hist) {
        this.els.inspectorTrendChart.innerHTML = SvgChartGenerator.renderDualTrend(hist.flow, hist.temp);
      }
    }

    renderCuratedLake(publication) {
      if (!publication) return;

      if (this.els.curatedRunSubtext) this.els.curatedRunSubtext.textContent = `Run: ${publication.published_run_id || "--"}`;
      if (this.els.pipelinePubId) this.els.pipelinePubId.textContent = publication.published_run_id || "current.json";
      if (this.els.batchPubTimestamp) {
        this.els.batchPubTimestamp.textContent = `Published at: ${publication.published_at ? publication.published_at.replace("T", " ").substring(0, 19) : "--"} UTC`;
      }

      const counts = publication.counts || {};
      if (this.els.badgeSilverCount) this.els.badgeSilverCount.textContent = `Silver: ${counts.silver_rows ?? "--"} rows`;
      if (this.els.badgeGoldCount) this.els.badgeGoldCount.textContent = `Gold: ${counts.gold_rows ?? "--"} rows`;

      if (this.els.lakeTableBody && publication.kpis && publication.kpis.length > 0) {
        this.els.lakeTableBody.innerHTML = publication.kpis.map(row => `
          <tr>
            <td><strong>${row.esp_id}</strong></td>
            <td>${row.avg_liquid_rate_m3_day != null ? Number(row.avg_liquid_rate_m3_day).toFixed(1) : "--"}</td>
            <td>${row.avg_oil_rate_m3_day != null ? Number(row.avg_oil_rate_m3_day).toFixed(1) : "--"}</td>
            <td>${row.avg_motor_temperature_c != null ? Number(row.avg_motor_temperature_c).toFixed(1) : "--"}</td>
            <td>${row.peak_vibration_mm_s != null ? Number(row.peak_vibration_mm_s).toFixed(2) : "--"}</td>
            <td>${row.samples != null ? row.samples : "--"}</td>
          </tr>
        `).join("");
      }

      if (this.els.athenaSqlSnippet && publication.published_run_id) {
        this.els.athenaSqlSnippet.textContent = `SELECT esp_id, event_date, COUNT(*) AS samples,\n       AVG(flow_rate) AS avg_liquid_rate_m3_day,\n       AVG(flow_rate * (1 - water_cut)) AS avg_oil_rate_m3_day,\n       AVG(motor_temperature) AS avg_motor_temperature_c,\n       MAX(vibration) AS peak_vibration_mm_s\nFROM silver\nWHERE publication_run_id = '${publication.published_run_id}'\nGROUP BY esp_id, event_date;`;
      }
    }

    renderHealthStats(health) {
      if (!health) return;

      const pc = health.pump_cache || {};
      const kc = health.publication_cache || {};

      const pumpHits = pc.hits || 0;
      const pumpTotal = pumpHits + (pc.misses || 0);
      const pumpRatio = pumpTotal > 0 ? Math.round((pumpHits / pumpTotal) * 100) : 0;

      const pubHits = kc.hits || 0;
      const pubTotal = pubHits + (kc.misses || 0);
      const pubRatio = pubTotal > 0 ? Math.round((pubHits / pubTotal) * 100) : 0;

      if (this.els.healthPumpHits) this.els.healthPumpHits.textContent = pumpHits;
      if (this.els.healthPumpRatio) this.els.healthPumpRatio.textContent = `${pumpRatio}% ratio`;

      if (this.els.healthPubHits) this.els.healthPubHits.textContent = pubHits;
      if (this.els.healthPubRatio) this.els.healthPubRatio.textContent = `${pubRatio}% ratio`;

      if (this.els.healthLatencyVal) this.els.healthLatencyVal.textContent = `${state.lastLatencyMs} ms`;
    }

    renderAnomalyBanner(activeAnomalies) {
      if (!this.els.anomalyBanner || !this.els.anomalyMessage) return;

      if (activeAnomalies.length > 0) {
        const text = activeAnomalies.map(a => `${a.esp_id}: ${a.finding} (${a.severity.toUpperCase()})`).join(" | ");
        this.els.anomalyMessage.innerHTML = `<strong>Operational Alarm:</strong> ${text}`;
        this.els.anomalyBanner.style.display = "flex";
      } else {
        this.els.anomalyBanner.style.display = "none";
      }
    }
  }

  const renderer = new DOMRenderer();

  // Polling Orchestrator
  async function pollTelemetry(isManual = false) {
    if (state.inFlightRequest) return;

    if (isManual && renderer.els.btnRefresh) {
      renderer.els.btnRefresh.classList.add("spinning");
    }

    const result = await api.fetchPumps();

    if (isManual && renderer.els.btnRefresh) {
      renderer.els.btnRefresh.classList.remove("spinning");
    }

    if (!result) return;

    if (result.success) {
      const envelope = result.data;
      state.lastSuccessTime = Date.now();
      state.pumpsData = envelope.data || [];
      const dataAge = envelope.data_age_seconds;

      renderer.setSystemState(envelope.state || "fresh");
      renderer.renderFleetKpis(state.pumpsData);
      renderer.renderPumpsGrid(state.pumpsData, dataAge);

      if (state.activeView === "inspector") {
        renderer.renderInspectorView();
      }

      // Check anomalies
      const activeAnomalies = state.pumpsData.filter(p => p.severity === "warning" || p.severity === "critical");
      renderer.renderAnomalyBanner(activeAnomalies);

      if (activeAnomalies.some(a => a.severity === "critical")) {
        sound.playAlert("critical");
      } else if (activeAnomalies.length > 0) {
        sound.playAlert("warning");
      }
    } else {
      const elapsed = state.lastSuccessTime ? (Date.now() - state.lastSuccessTime) / 1000 : 999;
      if (elapsed > CONFIG.UNAVAILABLE_THRESHOLD_SECONDS || result.status === 503) {
        renderer.setSystemState("unavailable", "Backend dependency unavailable (>45s). Preserving last observation.");
      } else {
        renderer.setSystemState("stale", `Connection interrupted. Last successful fetch was ${Math.round(elapsed)}s ago.`);
      }
    }

    // Refresh KPI summary & Health periodically
    if (!state.kpisData) {
      await refreshCuratedLake();
    }
  }

  async function refreshCuratedLake() {
    const kpiResult = await api.fetchKpis();
    if (kpiResult && kpiResult.data) {
      state.kpisData = kpiResult.data;
      renderer.renderCuratedLake(state.kpisData);
    }
  }

  async function refreshHealth() {
    const healthResult = await api.fetchHealth();
    if (healthResult) {
      state.healthData = healthResult;
      renderer.renderHealthStats(healthResult);
    }
  }

  // Audio Mute Toggle Setup
  function setupAudioToggle() {
    const btn = renderer.els.btnAudioMute;
    if (!btn) return;

    function updateAudioUi() {
      if (state.isMuted) {
        renderer.els.soundWaveBars.className = "sound-wave-bars muted";
        renderer.els.audioBtnLabel.textContent = "Audio Muted";
        btn.style.opacity = "0.7";
      } else {
        renderer.els.soundWaveBars.className = "sound-wave-bars active";
        renderer.els.audioBtnLabel.textContent = "Audio On";
        btn.style.opacity = "1";
      }
    }

    btn.addEventListener("click", () => {
      state.isMuted = !state.isMuted;
      localStorage.setItem(CONFIG.STORAGE_KEYS.AUDIO_MUTED, state.isMuted ? "true" : "false");
      updateAudioUi();
      if (!state.isMuted) {
        sound.playAlert("warning");
      }
    });

    updateAudioUi();
  }

  // Modals & Rehearsal Guide Setup
  function setupModals() {
    const guideModal = document.getElementById("guide-modal");
    const openGuideBtn = document.getElementById("btn-demo-guide");
    const closeGuideBtn = document.getElementById("close-guide-modal");

    if (openGuideBtn && guideModal) {
      openGuideBtn.addEventListener("click", () => guideModal.classList.add("open"));
    }
    if (closeGuideBtn && guideModal) {
      closeGuideBtn.addEventListener("click", () => guideModal.classList.remove("open"));
    }

    // Close on backdrop click
    document.querySelectorAll(".modal-overlay").forEach(backdrop => {
      backdrop.addEventListener("click", (e) => {
        if (e.target === backdrop) backdrop.classList.remove("open");
      });
    });

    // Close on Escape key
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        document.querySelectorAll(".modal-overlay.open").forEach(b => b.classList.remove("open"));
      }
    });
  }

  // Polling Timer
  function startTimers() {
    setInterval(() => {
      renderer.updateClock();

      state.secondsUntilNextPoll -= 1;
      if (state.secondsUntilNextPoll <= 0) {
        state.secondsUntilNextPoll = CONFIG.POLL_INTERVAL_SECONDS;
        pollTelemetry();
        refreshHealth();
      }
      renderer.updateCountdown(state.secondsUntilNextPoll);
    }, 1000);
  }

  // Application Entry Point
  async function init() {
    renderer.updateClock();
    setupAudioToggle();
    setupModals();

    if (renderer.els.btnRefresh) {
      renderer.els.btnRefresh.addEventListener("click", () => {
        state.secondsUntilNextPoll = CONFIG.POLL_INTERVAL_SECONDS;
        pollTelemetry(true);
        refreshHealth();
      });
    }

    // Switch to persisted view if applicable
    renderer.switchView(state.activeView);

    // Initial data fetch
    await refreshHealth();
    await pollTelemetry();
    await refreshCuratedLake();

    startTimers();
    console.log("ESP Surveillance Mission Control initialized.");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
