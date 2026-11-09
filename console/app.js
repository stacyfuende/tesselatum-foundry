"use strict";

const byId = (id) => document.getElementById(id);
let apiBase = "";
let bearerToken = "";
let connected = false;

const submitButtons = Array.from(
  document.querySelectorAll(".dashboard button[type='submit']")
);
const refreshButtons = [byId("refreshRegistry"), byId("refreshRuns")];

function setMessage(id, message, kind = "") {
  const element = byId(id);
  element.textContent = message;
  element.className = kind ? `message ${kind}` : "message";
}

function setConnectionState(isConnected, message, kind = "") {
  connected = isConnected;
  byId("connectionState").textContent = isConnected ? "Connected" : "Disconnected";
  byId("connectionState").className = isConnected
    ? "state connected"
    : "state disconnected";
  byId("connectButton").disabled = isConnected;
  byId("disconnectButton").disabled = !isConnected;
  [...submitButtons, ...refreshButtons].forEach((button) => {
    button.disabled = !isConnected;
  });
  setMessage("connectionMessage", message, kind);
}

function normalizeApiBase(value) {
  const candidate = value.trim();
  if (
    !candidate.startsWith("/") ||
    candidate.startsWith("//") ||
    candidate.includes("..") ||
    candidate.includes("\\") ||
    candidate.includes("?") ||
    candidate.includes("#")
  ) {
    throw new Error("Use a same-origin path such as /api. External URLs are not allowed.");
  }
  return candidate.replace(/\/+$/, "");
}

async function apiRequest(path, { method = "GET", body } = {}) {
  if (!connected && !bearerToken) {
    throw new Error("Connect to the Foundry API first.");
  }
  const headers = {
    Accept: "application/json",
    Authorization: `Bearer ${bearerToken}`,
  };
  const options = {
    method,
    headers,
    redirect: "error",
    cache: "no-store",
    credentials: "same-origin",
  };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(`${apiBase}${path}`, options);
  } catch (error) {
    throw new Error("Request failed. Check the same-origin API proxy and connection.");
  }
  const raw = await response.text();
  let payload = raw;
  try {
    payload = raw ? JSON.parse(raw) : null;
  } catch (error) {
    if (response.ok) {
      throw new Error("The API returned a non-JSON response.");
    }
  }
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? payload.detail
        : `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

function parseOptionalObject(id, label) {
  const source = byId(id).value.trim();
  if (!source) return undefined;
  const value = JSON.parse(source);
  if (!value || Array.isArray(value) || typeof value !== "object") {
    throw new Error(`${label} must be a JSON object.`);
  }
  return value;
}

function encodeBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

function renderRegistry(capabilities, implementations) {
  const capabilityList = byId("capabilityList");
  const implementationList = byId("implementationList");
  capabilityList.replaceChildren();
  implementationList.replaceChildren();

  capabilities.forEach((item) => {
    const row = document.createElement("li");
    const title = document.createElement("strong");
    title.textContent = `${item.name} · ${item.version}`;
    const detail = document.createElement("span");
    detail.textContent = item.capability_id;
    row.append(title, detail);
    capabilityList.append(row);
  });

  implementations.forEach((item) => {
    const row = document.createElement("li");
    const title = document.createElement("strong");
    title.textContent = `${item.implementation_id} · ${item.version}`;
    const detail = document.createElement("span");
    detail.textContent = `${item.capability_id}@${item.capability_version} · conformance: ${item.conformance.status}`;
    row.append(title, detail);
    implementationList.append(row);
  });
  if (!capabilities.length) capabilityList.textContent = "No registered capabilities.";
  if (!implementations.length) implementationList.textContent = "No registered implementations.";
}

async function refreshRegistry() {
  const [capabilities, implementations] = await Promise.all([
    apiRequest("/v1/capabilities"),
    apiRequest("/v1/implementations"),
  ]);
  renderRegistry(capabilities, implementations);
}

function renderRunList(records) {
  const list = byId("runList");
  list.replaceChildren();
  if (!records.length) {
    const empty = document.createElement("li");
    empty.className = "muted";
    empty.textContent = "No Runs have been recorded yet.";
    list.append(empty);
    return;
  }
  records.slice().reverse().forEach((record) => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "run-button";
    const title = document.createElement("strong");
    title.textContent = `${record.status} · ${record.run_id}`;
    const detail = document.createElement("span");
    detail.textContent = `${record.capability.capability_id}@${record.capability.version} · ${record.created_at}`;
    button.append(title, detail);
    button.addEventListener("click", () => inspectRun(record.run_id));
    item.append(button);
    list.append(item);
  });
}

async function refreshRuns() {
  const records = await apiRequest("/v1/runs?limit=100");
  renderRunList(records);
}

async function inspectRun(runId) {
  try {
    const record = await apiRequest(`/v1/runs/${encodeURIComponent(runId)}`);
    byId("recordDetail").textContent = JSON.stringify(record, null, 2);
    const links = byId("reportLinks");
    links.replaceChildren();
    (record.validation_report_ids || []).forEach((reportId) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary";
      button.textContent = `Report: ${reportId}`;
      button.addEventListener("click", () => inspectReport(reportId));
      links.append(button);
    });
  } catch (error) {
    byId("recordDetail").textContent = error.message;
  }
}

async function inspectReport(reportId) {
  try {
    const report = await apiRequest(`/v1/reports/${encodeURIComponent(reportId)}`);
    byId("recordDetail").textContent = JSON.stringify(report, null, 2);
  } catch (error) {
    byId("recordDetail").textContent = error.message;
  }
}

byId("connectButton").addEventListener("click", async () => {
  try {
    apiBase = normalizeApiBase(byId("apiBase").value);
    bearerToken = byId("apiToken").value;
    byId("apiToken").value = "";
    if (bearerToken.length < 32) {
      throw new Error("The bearer token must contain at least 32 characters.");
    }
    // Health is public; the authenticated registry request verifies the token.
    const health = await apiRequest("/health");
    if (health.status !== "ok") throw new Error("Control plane health check failed.");
    const [capabilities, implementations] = await Promise.all([
      apiRequest("/v1/capabilities"),
      apiRequest("/v1/implementations"),
    ]);
    renderRegistry(capabilities, implementations);
    setConnectionState(true, "Connected. The bearer token is held in page memory only.", "success");
    await refreshRuns();
  } catch (error) {
    bearerToken = "";
    byId("apiToken").value = "";
    setConnectionState(false, error.message, "error");
  }
});

byId("disconnectButton").addEventListener("click", () => {
  bearerToken = "";
  apiBase = "";
  byId("apiToken").value = "";
  byId("capabilityList").textContent = "Connect to load capabilities.";
  byId("implementationList").textContent = "Connect to load implementations.";
  byId("runList").textContent = "Connect to inspect Run history.";
  byId("recordDetail").textContent = "Select a Run to inspect its provenance and validation references.";
  byId("reportLinks").replaceChildren();
  setConnectionState(false, "Disconnected. The in-memory bearer token was cleared.");
});

byId("refreshRegistry").addEventListener("click", async () => {
  try {
    await refreshRegistry();
    setMessage("connectionMessage", "Registry refreshed.", "success");
  } catch (error) {
    setMessage("connectionMessage", error.message, "error");
  }
});

byId("refreshRuns").addEventListener("click", async () => {
  try {
    await refreshRuns();
  } catch (error) {
    setMessage("connectionMessage", error.message, "error");
  }
});

byId("artifactForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const file = byId("artifactFile").files[0];
    if (!file) throw new Error("Choose a file to upload.");
    if (file.size > 20 * 1024 * 1024) {
      throw new Error("This console limits uploads to 20 MiB to stay below the API JSON/base64 request ceiling.");
    }
    const payload = {
      artifact_id: byId("artifactId").value.trim(),
      version: byId("artifactVersion").value.trim(),
      content_base64: encodeBase64(await file.arrayBuffer()),
      created_by: byId("artifactCreator").value.trim(),
      media_type: byId("artifactMediaType").value.trim(),
      format: byId("artifactFormat").value.trim(),
    };
    for (const [field, element, label] of [
      ["spatial", "artifactSpatial", "Spatial metadata"],
      ["rights", "artifactRights", "Rights metadata"],
      ["metadata", "artifactMetadata", "Additional metadata"],
    ]) {
      const value = parseOptionalObject(element, label);
      if (value !== undefined) payload[field] = value;
    }
    const artifact = await apiRequest("/v1/artifacts", {method: "POST", body: payload});
    setMessage(
      "artifactMessage",
      `Stored ${artifact.artifact_id}@${artifact.version} · SHA-256 ${artifact.checksum.value}`,
      "success",
    );
  } catch (error) {
    setMessage("artifactMessage", error.message, "error");
  }
});

async function registerDefinition(path, textareaId, creatorId, messageId, label) {
  try {
    const definition = JSON.parse(byId(textareaId).value);
    const record = await apiRequest(path, {
      method: "POST",
      body: {created_by: byId(creatorId).value.trim(), definition},
    });
    setMessage(
      messageId,
      `Registered ${record.definition_ref.definition_id}@${record.definition_ref.version}`,
      "success",
    );
    return definition;
  } catch (error) {
    setMessage(messageId, error.message, "error");
    return null;
  }
}

byId("cellForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  await registerDefinition(
    "/v1/cells",
    "cellDefinition",
    "cellCreator",
    "cellMessage",
    "Cell",
  );
});

byId("recipeForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const definition = await registerDefinition(
    "/v1/recipes",
    "recipeDefinition",
    "recipeCreator",
    "recipeMessage",
    "Recipe",
  );
  if (definition) {
    byId("runRecipeId").value = definition.recipe_id;
    byId("runRecipeVersion").value = definition.version;
  }
});

byId("executeForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const recipeId = byId("runRecipeId").value.trim();
    const version = byId("runRecipeVersion").value.trim();
    const result = await apiRequest(
      `/v1/recipes/${encodeURIComponent(recipeId)}/${encodeURIComponent(version)}/runs`,
      {
        method: "POST",
        body: {actor_id: byId("runActor").value.trim()},
      },
    );
    byId("executionResult").textContent = JSON.stringify(result, null, 2);
    setMessage(
      "executeMessage",
      `Recipe execution ${result.status} · ${result.execution_id}`,
      result.status === "succeeded" ? "success" : "error",
    );
    await refreshRuns();
  } catch (error) {
    setMessage("executeMessage", error.message, "error");
  }
});

setConnectionState(false, "Enter the private API token. It is never written to browser storage.");
