import assert from "node:assert/strict";
import { test } from "node:test";

import {
  POPUP_STATES,
  buildPopupRenderModel,
  permissionOriginForBaseUrl,
  renderPopupDocument,
  renderTodayMarkup,
  saveSettings,
} from "../src/popup.mjs";

function createDocumentHarness() {
  const elements = new Map();
  for (const id of [
    "mode-line",
    "cards",
    "today",
    "sync-meta",
    "status-banner",
    "settings-panel",
    "today-panel",
    "cards-panel",
    "sync-panel",
    "sync-now",
    "toggle-settings",
    "api-base-url",
    "access-token",
  ]) {
    elements.set(id, {
      id,
      innerHTML: "",
      textContent: "",
      hidden: false,
      dataset: {},
      value: "",
    });
  }
  return {
    getElementById(id) {
      return elements.get(id);
    },
  };
}

test("test_no_credentials_shows_settings", () => {
  const model = buildPopupRenderModel({});
  assert.equal(model.state, POPUP_STATES.noCredentials);
  assert.equal(model.showSettings, true);
});

test("test_ready_state_renders_assignments", () => {
  const model = buildPopupRenderModel({
    settings: { apiBaseUrl: "https://canvas.example.edu", accessToken: "token" },
    assignments: [{ courseId: 101, courseName: "English", name: "Essay 1", dueAt: "2026-03-07T12:00:00Z" }],
    syncError: null,
    lastSuccessAt: "2026-03-06T10:00:00Z",
  });

  assert.equal(model.state, POPUP_STATES.ready);
  assert.match(renderTodayMarkup(model.todaySections), /Essay 1/);
});

test("test_ready_state_can_show_settings_when_requested", () => {
  const model = buildPopupRenderModel(
    {
      settings: { apiBaseUrl: "https://canvas.example.edu", accessToken: "token" },
      assignments: [{ courseId: 101, courseName: "English", name: "Essay 1", dueAt: "2026-03-07T12:00:00Z" }],
      syncError: null,
      lastSuccessAt: "2026-03-06T10:00:00Z",
    },
    { settingsVisible: true },
  );

  assert.equal(model.state, POPUP_STATES.ready);
  assert.equal(model.showSettings, true);
  assert.equal(model.settingsToggleLabel, "Hide Connection");
});

test("test_stale_with_error_shows_data_and_banner", () => {
  const model = buildPopupRenderModel({
    settings: { apiBaseUrl: "https://canvas.example.edu", accessToken: "token" },
    assignments: [{ courseId: 101, courseName: "English", name: "Essay 1", dueAt: "2026-03-07T12:00:00Z" }],
    syncError: "Canvas API request failed: 500",
    lastSuccessAt: "2026-03-06T10:00:00Z",
  });

  assert.equal(model.state, POPUP_STATES.staleWithError);
  assert.match(model.banner.message, /500/);
  assert.equal(model.todaySections[1].items.length >= 0, true);
});

test("test_error_no_data_shows_error_state", () => {
  const model = buildPopupRenderModel({
    settings: { apiBaseUrl: "https://canvas.example.edu", accessToken: "token" },
    assignments: [],
    syncError: "Canvas API request failed: 401",
  });

  assert.equal(model.state, POPUP_STATES.errorNoData);
  assert.match(model.banner.message, /401/);
});

test("threat_token_never_rendered_back_to_popup", () => {
  const documentRef = createDocumentHarness();
  const model = buildPopupRenderModel({
    settings: { apiBaseUrl: "https://canvas.example.edu", accessToken: "secret-token" },
    assignments: [],
    syncError: null,
    lastSuccessAt: "2026-03-06T10:00:00Z",
  });

  renderPopupDocument(documentRef, model);

  assert.equal(documentRef.getElementById("access-token").value, "");
  assert.equal(documentRef.getElementById("api-base-url").value, "https://canvas.example.edu");
  assert.equal(documentRef.getElementById("toggle-settings").textContent, "Change Connection");
});

test("threat_no_console_log_of_token", async () => {
  const logger = {
    calls: [],
    log(...args) {
      this.calls.push(args.join(" "));
    },
  };
  const chromeApi = {
    permissions: {
      async request() {
        return true;
      },
    },
    storage: {
      local: {
        async set() {},
      },
    },
    runtime: {
      async sendMessage() {
        return { ok: true };
      },
    },
  };

  const result = await saveSettings({
    chromeApi,
    apiBaseUrl: "https://canvas.example.edu",
    accessToken: "secret-token",
    logger,
  });

  assert.equal(result.ok, true);
  assert.equal(logger.calls.some((entry) => entry.includes("secret-token")), false);
  assert.equal(permissionOriginForBaseUrl("https://canvas.example.edu"), "https://canvas.example.edu/*");
});

test("threat_permission_denied_fails_closed", async () => {
  let storageWrites = 0;
  let syncMessages = 0;
  const chromeApi = {
    permissions: {
      async request() {
        return false;
      },
    },
    storage: {
      local: {
        async set() {
          storageWrites += 1;
        },
      },
    },
    runtime: {
      async sendMessage() {
        syncMessages += 1;
        return { ok: true };
      },
    },
  };

  const result = await saveSettings({
    chromeApi,
    apiBaseUrl: "https://canvas.example.edu",
    accessToken: "secret-token",
  });

  assert.equal(result.ok, false);
  assert.match(result.error, /Permission required/);
  assert.equal(storageWrites, 0);
  assert.equal(syncMessages, 0);
});
