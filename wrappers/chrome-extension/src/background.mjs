import { fetchUpcomingAssignments } from "./canvas-client.mjs";

export const SYNC_ALARM_NAME = "duecheck-sync";
const SYNC_PERIOD_MINUTES = 60;

function nowIso(now) {
  return now().toISOString();
}

async function getLocalState(chromeApi) {
  return chromeApi.storage.local.get([
    "settings",
    "assignments",
    "syncError",
    "lastAttemptAt",
    "lastSuccessAt",
  ]);
}

export function createBackgroundController({
  chromeApi = chrome,
  fetchAssignments = fetchUpcomingAssignments,
  now = () => new Date(),
} = {}) {
  async function ensureAlarm() {
    const existing = await chromeApi.alarms.get(SYNC_ALARM_NAME);
    if (existing) {
      return existing;
    }
    await chromeApi.alarms.create(SYNC_ALARM_NAME, { periodInMinutes: SYNC_PERIOD_MINUTES });
    return chromeApi.alarms.get(SYNC_ALARM_NAME);
  }

  async function runSync() {
    const state = await getLocalState(chromeApi);
    const lastAttemptAt = nowIso(now);
    const settings = state.settings ?? {};
    const apiBaseUrl = String(settings.apiBaseUrl ?? "").trim();
    const accessToken = String(settings.accessToken ?? "").trim();

    if (!apiBaseUrl || !accessToken) {
      await chromeApi.storage.local.set({
        syncError: "No credentials configured",
        lastAttemptAt,
      });
      return { ok: false, reason: "missing-credentials" };
    }

    try {
      const assignments = await fetchAssignments(apiBaseUrl, accessToken);
      const lastSuccessAt = nowIso(now);
      await chromeApi.storage.local.set({
        assignments,
        syncError: null,
        lastAttemptAt,
        lastSuccessAt,
      });
      return { ok: true, assignmentsCount: assignments.length, lastSuccessAt };
    } catch (error) {
      await chromeApi.storage.local.set({
        syncError: error instanceof Error ? error.message : String(error),
        lastAttemptAt,
        lastSuccessAt: state.lastSuccessAt ?? null,
      });
      return { ok: false, reason: "sync-failed", error: error instanceof Error ? error.message : String(error) };
    }
  }

  async function handleInstall() {
    await ensureAlarm();
    return runSync();
  }

  async function handleStartup() {
    return ensureAlarm();
  }

  async function handleAlarm(alarm) {
    if (!alarm || alarm.name !== SYNC_ALARM_NAME) {
      return { ok: false, reason: "ignored" };
    }
    return runSync();
  }

  async function handleMessage(message) {
    if (!message || message.type !== "duecheck-sync-now") {
      return { ok: false, reason: "ignored" };
    }
    return runSync();
  }

  return {
    ensureAlarm,
    runSync,
    handleInstall,
    handleStartup,
    handleAlarm,
    handleMessage,
  };
}

export function registerBackground({
  chromeApi = chrome,
  controller = createBackgroundController({ chromeApi }),
} = {}) {
  chromeApi.runtime.onInstalled.addListener(() => {
    void controller.handleInstall();
  });
  chromeApi.runtime.onStartup.addListener(() => {
    void controller.handleStartup();
  });
  chromeApi.alarms.onAlarm.addListener((alarm) => {
    void controller.handleAlarm(alarm);
  });
  chromeApi.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!message || message.type !== "duecheck-sync-now") {
      return false;
    }
    void controller
      .handleMessage(message)
      .then((result) => sendResponse(result))
      .catch((error) =>
        sendResponse({
          ok: false,
          error: error instanceof Error ? error.message : String(error),
        }),
      );
    return true;
  });
  return controller;
}

export function registerLiveBackground() {
  return registerBackground();
}
