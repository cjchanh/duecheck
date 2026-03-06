import assert from "node:assert/strict";
import { test } from "node:test";

import { SYNC_ALARM_NAME, createBackgroundController } from "../src/background.mjs";

function createChromeHarness(initialState = {}) {
  const storageState = {
    settings: null,
    activeCourseCount: 0,
    assignments: [],
    changes: [],
    changeCounts: null,
    syncError: null,
    lastAttemptAt: null,
    lastSuccessAt: null,
    ...initialState,
  };
  const alarms = new Map();

  return {
    storageState,
    chromeApi: {
      storage: {
        local: {
          async get(keys) {
            return Object.fromEntries(keys.map((key) => [key, storageState[key]]));
          },
          async set(values) {
            Object.assign(storageState, values);
          },
        },
      },
      alarms: {
        async get(name) {
          return alarms.get(name) ?? null;
        },
        async create(name, payload) {
          alarms.set(name, { name, ...payload });
        },
      },
      runtime: {},
    },
    alarms,
  };
}

test("test_install_creates_alarm_and_syncs", async () => {
  const harness = createChromeHarness({
    settings: { apiBaseUrl: "https://canvas.example.edu", accessToken: "token" },
  });
  let syncCalls = 0;
  const controller = createBackgroundController({
    chromeApi: harness.chromeApi,
    fetchSnapshot: async () => {
      syncCalls += 1;
      return {
        activeCourseCount: 1,
        assignments: [{ id: 1, courseId: 101, courseName: "English", name: "Essay", dueAt: null }],
      };
    },
    now: () => new Date("2026-03-06T10:00:00Z"),
  });

  const result = await controller.handleInstall();

  assert.equal(syncCalls, 1);
  assert.equal(harness.alarms.has(SYNC_ALARM_NAME), true);
  assert.equal(result.ok, true);
});

test("test_alarm_triggers_sync", async () => {
  const harness = createChromeHarness({
    settings: { apiBaseUrl: "https://canvas.example.edu", accessToken: "token" },
  });
  let syncCalls = 0;
  const controller = createBackgroundController({
    chromeApi: harness.chromeApi,
    fetchSnapshot: async () => {
      syncCalls += 1;
      return { activeCourseCount: 0, assignments: [] };
    },
  });

  await controller.handleAlarm({ name: SYNC_ALARM_NAME });
  assert.equal(syncCalls, 1);
});

test("test_sync_now_message_triggers_sync", async () => {
  const harness = createChromeHarness({
    settings: { apiBaseUrl: "https://canvas.example.edu", accessToken: "token" },
  });
  let syncCalls = 0;
  const controller = createBackgroundController({
    chromeApi: harness.chromeApi,
    fetchSnapshot: async () => {
      syncCalls += 1;
      return { activeCourseCount: 0, assignments: [] };
    },
  });

  await controller.handleMessage({ type: "duecheck-sync-now" });
  assert.equal(syncCalls, 1);
});

test("test_startup_ensures_alarm_exists", async () => {
  const harness = createChromeHarness();
  const controller = createBackgroundController({
    chromeApi: harness.chromeApi,
  });

  await controller.handleStartup();

  assert.equal(harness.alarms.has(SYNC_ALARM_NAME), true);
});

test("test_success_writes_assignments_clears_error", async () => {
  const harness = createChromeHarness({
    settings: { apiBaseUrl: "https://canvas.example.edu", accessToken: "token" },
    syncError: "old error",
  });
  const controller = createBackgroundController({
    chromeApi: harness.chromeApi,
    fetchSnapshot: async () => ({
      activeCourseCount: 2,
      assignments: [{ id: 1, courseId: 101, courseName: "English", name: "Essay", dueAt: null }],
    }),
    now: () => new Date("2026-03-06T10:00:00Z"),
  });

  await controller.runSync();

  assert.equal(harness.storageState.activeCourseCount, 2);
  assert.equal(harness.storageState.assignments.length, 1);
  assert.equal(harness.storageState.changes.length, 1);
  assert.equal(harness.storageState.changeCounts.new, 1);
  assert.equal(harness.storageState.syncError, null);
  assert.equal(harness.storageState.lastSuccessAt, "2026-03-06T10:00:00.000Z");
});

test("test_failure_preserves_assignments_writes_error", async () => {
  const existingAssignments = [{ id: 9, courseName: "History", name: "Reading", dueAt: null }];
  const harness = createChromeHarness({
    settings: { apiBaseUrl: "https://canvas.example.edu", accessToken: "token" },
    activeCourseCount: 1,
    assignments: existingAssignments,
    changes: [{ changeType: "new", courseName: "History", name: "Reading" }],
    changeCounts: { new: 1 },
    lastSuccessAt: "2026-03-05T10:00:00.000Z",
  });
  const controller = createBackgroundController({
    chromeApi: harness.chromeApi,
    fetchSnapshot: async () => {
      throw new Error("Canvas API request failed: 500");
    },
    now: () => new Date("2026-03-06T10:00:00Z"),
  });

  const result = await controller.runSync();

  assert.equal(result.ok, false);
  assert.equal(harness.storageState.activeCourseCount, 1);
  assert.deepEqual(harness.storageState.assignments, existingAssignments);
  assert.deepEqual(harness.storageState.changes, [{ changeType: "new", courseName: "History", name: "Reading" }]);
  assert.deepEqual(harness.storageState.changeCounts, { new: 1 });
  assert.equal(harness.storageState.syncError, "Canvas API request failed: 500");
  assert.equal(harness.storageState.lastSuccessAt, "2026-03-05T10:00:00.000Z");
  assert.equal(harness.storageState.lastAttemptAt, "2026-03-06T10:00:00.000Z");
});

test("threat_missing_credentials_does_not_fetch", async () => {
  const harness = createChromeHarness();
  let syncCalls = 0;
  const controller = createBackgroundController({
    chromeApi: harness.chromeApi,
    fetchSnapshot: async () => {
      syncCalls += 1;
      return { activeCourseCount: 0, assignments: [] };
    },
    now: () => new Date("2026-03-06T10:00:00Z"),
  });

  const result = await controller.runSync();

  assert.equal(result.ok, false);
  assert.equal(syncCalls, 0);
  assert.equal(harness.storageState.syncError, "No credentials configured");
});
