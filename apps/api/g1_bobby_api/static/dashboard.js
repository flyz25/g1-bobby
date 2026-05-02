(function () {
  const state = {
    nextSeq: 1,
    operatorSocket: null,
    auditSocket: null,
    lastState: null,
    lastRuntime: null,
  };

  const els = {
    tokenInput: document.getElementById("token-input"),
    connectionSummary: document.getElementById("connection-summary"),
    runtimeUpdated: document.getElementById("runtime-updated"),
    stateUpdated: document.getElementById("state-updated"),
    transportUpdated: document.getElementById("transport-updated"),
    commandStatus: document.getElementById("command-status"),
    telemetrySummary: document.getElementById("telemetry-summary"),
    unitreeSummary: document.getElementById("unitree-summary"),
    operatorSocketState: document.getElementById("operator-socket-state"),
    auditSocketState: document.getElementById("audit-socket-state"),
    runtimeMetrics: document.getElementById("runtime-metrics"),
    stateMetrics: document.getElementById("state-metrics"),
    transportMetrics: document.getElementById("transport-metrics"),
    transportBlockers: document.getElementById("transport-blockers"),
    stateJson: document.getElementById("state-json"),
    unitreeJson: document.getElementById("unitree-json"),
    operatorEvents: document.getElementById("operator-events"),
    auditEvents: document.getElementById("audit-events"),
    commandPlanHistory: document.getElementById("command-plan-history"),
    executionPlanHistory: document.getElementById("execution-plan-history"),
    executionResultHistory: document.getElementById("execution-result-history"),
    rejectionHistory: document.getElementById("rejection-history"),
    commandPlanCount: document.getElementById("command-plan-count"),
    executionPlanCount: document.getElementById("execution-plan-count"),
    executionResultCount: document.getElementById("execution-result-count"),
    rejectionCount: document.getElementById("rejection-count"),
    linearX: document.getElementById("linear-x"),
    linearY: document.getElementById("linear-y"),
    angularZ: document.getElementById("angular-z"),
    durationMs: document.getElementById("duration-ms"),
  };

  function nowIso() {
    return new Date().toLocaleTimeString();
  }

  function wsBase(path) {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}${path}`;
  }

  function api(path, init) {
    return fetch(path, init).then(async (response) => {
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `${response.status}`);
      }
      return response;
    });
  }

  function setMetrics(target, pairs) {
    target.replaceChildren();
    pairs.forEach(([label, value]) => {
      const dt = document.createElement("div");
      const labelEl = document.createElement("dt");
      const valueEl = document.createElement("dd");
      labelEl.textContent = label;
      valueEl.textContent = value;
      dt.append(labelEl, valueEl);
      target.append(dt);
    });
  }

  function setJson(target, value) {
    target.textContent = JSON.stringify(value ?? null, null, 2);
  }

  function addEntries(target, rows) {
    target.replaceChildren();
    if (!rows.length) {
      const empty = document.createElement("div");
      empty.className = "history-entry";
      empty.textContent = "empty";
      target.append(empty);
      return;
    }
    rows.forEach((row) => {
      const entry = document.createElement("div");
      entry.className = "history-entry";
      const head = document.createElement("div");
      head.className = "entry-head";
      const left = document.createElement("span");
      const right = document.createElement("span");
      left.textContent = row.left;
      right.textContent = row.right;
      const body = document.createElement("div");
      body.className = "entry-body";
      body.textContent = row.body;
      head.append(left, right);
      entry.append(head, body);
      target.append(entry);
    });
  }

  function addLog(target, label, payload) {
    const entry = document.createElement("div");
    entry.className = "log-entry";
    const head = document.createElement("div");
    head.className = "entry-head";
    const left = document.createElement("span");
    const right = document.createElement("span");
    left.textContent = label;
    right.textContent = nowIso();
    const body = document.createElement("div");
    body.className = "entry-body";
    body.textContent = JSON.stringify(payload);
    head.append(left, right);
    entry.append(head, body);
    target.prepend(entry);
    while (target.children.length > 40) {
      target.removeChild(target.lastChild);
    }
  }

  function summarizeUnitree(snapshot) {
    if (!snapshot) {
      return "not_available";
    }
    return `${snapshot.status} ${snapshot.source || "live"}${snapshot.stale ? " stale" : ""}`;
  }

  async function refreshRuntime() {
    const runtime = await api("/runtime").then((r) => r.json());
    state.lastRuntime = runtime;
    els.runtimeUpdated.textContent = nowIso();
    els.transportUpdated.textContent = nowIso();
    setMetrics(els.runtimeMetrics, [
      ["Adapter", runtime.adapter],
      ["Accepted", String(runtime.accepted_commands)],
      ["Rejected", String(runtime.rejected_commands)],
      ["Operator", runtime.active_operator_connected ? "connected" : "idle"],
      ["State updates", String(runtime.unitree_state.updates)],
      ["Execution results", String(runtime.unitree_execution_result.results)],
    ]);

    const capability = runtime.unitree_transport_capability;
    if (capability) {
      setMetrics(els.transportMetrics, [
        ["Transport", capability.transport],
        ["Configured", String(capability.configured)],
        ["Env ready", String(capability.environment_ready)],
        ["Execution", String(capability.execution_enabled)],
        ["Binding", String(capability.binding_implemented)],
        ["Ready", String(capability.ready)],
      ]);
      els.transportBlockers.replaceChildren();
      const blockers = capability.blockers || [];
      if (!blockers.length) {
        const chip = document.createElement("div");
        chip.className = "chip";
        chip.textContent = "ready";
        els.transportBlockers.append(chip);
      } else {
        blockers.forEach((item) => {
          const chip = document.createElement("div");
          chip.className = "chip";
          chip.textContent = item;
          els.transportBlockers.append(chip);
        });
      }
    } else {
      setMetrics(els.transportMetrics, [["Transport", "mock"], ["Ready", "n/a"]]);
      els.transportBlockers.replaceChildren();
    }
  }

  async function refreshState() {
    const payload = await api("/state").then((r) => r.json());
    state.lastState = payload;
    els.stateUpdated.textContent = nowIso();
    els.telemetrySummary.textContent = payload.state.mode;
    els.unitreeSummary.textContent = summarizeUnitree(payload.unitree_state);
    setMetrics(els.stateMetrics, [
      ["Connected", String(payload.state.connected)],
      ["Mode", payload.state.mode],
      ["E-stop", String(payload.state.estop_engaged)],
      ["Pose", payload.state.pose_label || "-"],
      ["Battery", String(payload.state.battery_percent)],
      ["Last state", new Date(payload.state.last_state_at * 1000).toLocaleTimeString()],
    ]);
    setJson(els.stateJson, payload.state);
    setJson(els.unitreeJson, payload.unitree_state);
  }

  async function refreshHistory() {
    const [commandPlans, executionPlans, executionResults, rejections] = await Promise.all([
      api("/unitree/command-plans").then((r) => r.json()),
      api("/unitree/execution-plans").then((r) => r.json()),
      api("/unitree/execution-results").then((r) => r.json()),
      api("/operator/rejections").then((r) => r.json()),
    ]);

    els.commandPlanCount.textContent = String(commandPlans.length);
    els.executionPlanCount.textContent = String(executionPlans.length);
    els.executionResultCount.textContent = String(executionResults.length);
    els.rejectionCount.textContent = String(rejections.length);

    addEntries(
      els.commandPlanHistory,
      commandPlans
        .slice()
        .reverse()
        .map((item) => ({
          left: `#${item.event_id} ${item.plan.type}`,
          right: item.plan.action,
          body: JSON.stringify(item.plan.payload),
        }))
    );
    addEntries(
      els.executionPlanHistory,
      executionPlans
        .slice()
        .reverse()
        .map((item) => ({
          left: `#${item.event_id} ${item.execution_plan.command_type}`,
          right: `${item.execution_plan.transport} ${item.execution_plan.target}`,
          body: JSON.stringify(item.execution_plan.payload),
        }))
    );
    addEntries(
      els.executionResultHistory,
      executionResults
        .slice()
        .reverse()
        .map((item) => ({
          left: `#${item.event_id} ${item.execution_result.command_type}`,
          right: `${item.execution_result.status} ${item.execution_result.transport}`,
          body: `${item.execution_result.target} ${item.execution_result.detail}`,
        }))
    );
    addEntries(
      els.rejectionHistory,
      rejections
        .slice()
        .reverse()
        .map((item) => ({
          left: `#${item.event_id} ${item.command_type || "n/a"}`,
          right: item.rejection.code,
          body: item.rejection.reason,
        }))
    );
  }

  async function refreshAll() {
    try {
      await Promise.all([refreshRuntime(), refreshState(), refreshHistory()]);
      els.connectionSummary.textContent = "synced";
    } catch (error) {
      els.connectionSummary.textContent = `sync error`;
      addLog(els.operatorEvents, "refresh-error", { message: String(error) });
    }
  }

  function sendCommand(command) {
    if (!state.operatorSocket || state.operatorSocket.readyState !== WebSocket.OPEN) {
      els.commandStatus.textContent = "operator socket closed";
      return;
    }
    command.seq = state.nextSeq++;
    command.timestamp = Date.now() / 1000;
    state.operatorSocket.send(JSON.stringify(command));
    els.commandStatus.textContent = `${command.type} sent`;
  }

  async function postEstop(path) {
    const init = { method: "POST", headers: {} };
    if (path === "/reset-estop") {
      init.headers["X-Operator-Token"] = els.tokenInput.value;
    }
    try {
      const response = await api(path, init).then((r) => r.json());
      addLog(els.operatorEvents, path, response);
      await refreshAll();
    } catch (error) {
      addLog(els.operatorEvents, "http-error", { path, message: String(error) });
    }
  }

  function handleOperatorEvent(payload) {
    addLog(els.operatorEvents, payload.type, payload);
    if (payload.type === "state") {
      state.lastState = payload;
      setJson(els.stateJson, payload.state);
      setJson(els.unitreeJson, payload.unitree_state);
      els.telemetrySummary.textContent = payload.state.mode;
      els.unitreeSummary.textContent = summarizeUnitree(payload.unitree_state);
    }
    if (payload.type === "ack" || payload.type === "reject") {
      els.commandStatus.textContent = `${payload.type} #${payload.seq ?? "-"}`;
      refreshAll();
    }
  }

  function handleAuditEvent(payload) {
    addLog(els.auditEvents, payload.type, payload);
    refreshHistory();
  }

  function connectSocket(kind) {
    const isAudit = kind === "audit";
    const target = isAudit ? els.auditSocketState : els.operatorSocketState;
    const path = isAudit ? "/ws/operator/audit" : "/ws/operator";
    const socket = new WebSocket(`${wsBase(path)}?token=${encodeURIComponent(els.tokenInput.value)}`);

    target.textContent = "connecting";
    socket.onopen = function () {
      target.textContent = "open";
      els.connectionSummary.textContent = "live";
    };
    socket.onclose = function () {
      target.textContent = "closed";
    };
    socket.onerror = function () {
      target.textContent = "error";
    };
    socket.onmessage = function (event) {
      const payload = JSON.parse(event.data);
      if (isAudit) {
        handleAuditEvent(payload);
      } else {
        handleOperatorEvent(payload);
      }
    };

    if (isAudit) {
      if (state.auditSocket) {
        state.auditSocket.close();
      }
      state.auditSocket = socket;
    } else {
      if (state.operatorSocket) {
        state.operatorSocket.close();
      }
      state.operatorSocket = socket;
    }
  }

  function disconnectSocket(kind) {
    if (kind === "audit" && state.auditSocket) {
      state.auditSocket.close();
      state.auditSocket = null;
      els.auditSocketState.textContent = "closed";
    }
    if (kind === "operator" && state.operatorSocket) {
      state.operatorSocket.close();
      state.operatorSocket = null;
      els.operatorSocketState.textContent = "closed";
    }
  }

  document.getElementById("refresh-all").addEventListener("click", refreshAll);
  document.getElementById("connect-operator").addEventListener("click", function () {
    connectSocket("operator");
  });
  document.getElementById("disconnect-operator").addEventListener("click", function () {
    disconnectSocket("operator");
  });
  document.getElementById("connect-audit").addEventListener("click", function () {
    connectSocket("audit");
  });
  document.getElementById("disconnect-audit").addEventListener("click", function () {
    disconnectSocket("audit");
  });
  document.getElementById("send-heartbeat").addEventListener("click", function () {
    sendCommand({ type: "heartbeat", payload: { client_id: "dashboard" } });
  });
  document.querySelectorAll(".mode-button").forEach((button) => {
    button.addEventListener("click", function () {
      sendCommand({ type: "set_mode", payload: { mode: button.dataset.mode } });
    });
  });
  document.getElementById("send-move").addEventListener("click", function () {
    sendCommand({
      type: "move_velocity",
      payload: {
        linear_x: Number(els.linearX.value),
        linear_y: Number(els.linearY.value),
        angular_z: Number(els.angularZ.value),
        duration_ms: Number(els.durationMs.value),
      },
    });
  });
  document.getElementById("send-stop").addEventListener("click", function () {
    sendCommand({ type: "stop", payload: { reason: "dashboard_stop" } });
  });
  document.getElementById("send-estop").addEventListener("click", function () {
    postEstop("/estop");
  });
  document.getElementById("send-reset-estop").addEventListener("click", function () {
    postEstop("/reset-estop");
  });

  refreshAll();
})();
