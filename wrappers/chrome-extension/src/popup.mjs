import { normalizeApiBaseUrl } from "./canvas-client.mjs";
import { buildPopupViewModel } from "./view-model.mjs";

export const POPUP_STATES = {
  loading: "loading",
  empty: "empty",
  ready: "ready",
  staleWithError: "stale-with-error",
  errorNoData: "error-no-data",
  noCredentials: "no-credentials",
};

function defaultNow() {
  return new Date();
}

function formatRelativeTime(isoTimestamp, now = defaultNow()) {
  if (!isoTimestamp) {
    return "Never";
  }
  const timestamp = new Date(isoTimestamp);
  if (Number.isNaN(timestamp.getTime())) {
    return isoTimestamp;
  }

  const deltaSeconds = Math.round((now.getTime() - timestamp.getTime()) / 1000);
  const absSeconds = Math.abs(deltaSeconds);
  if (absSeconds < 60) {
    return "just now";
  }
  const units = [
    [60 * 60 * 24, "day"],
    [60 * 60, "hour"],
    [60, "minute"],
  ];
  for (const [unitSeconds, label] of units) {
    if (absSeconds >= unitSeconds) {
      const value = Math.round(absSeconds / unitSeconds);
      return `${value} ${label}${value === 1 ? "" : "s"} ago`;
    }
  }
  return isoTimestamp;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderCards(cards) {
  return cards
    .map(
      (card) => `
        <article class="card tone-${card.tone}">
          <div class="card-label">${escapeHtml(card.label)}</div>
          <div class="card-value">${escapeHtml(card.value)}</div>
        </article>
      `,
    )
    .join("");
}

export function renderTodayMarkup(todaySections) {
  return `<div class="stack">${todaySections
    .map(
      (section) => `
        <div class="today-block">
          <div class="today-head">
            <h3>${escapeHtml(section.title)}</h3>
            <span class="meta">${section.items.length}</span>
          </div>
          <p class="today-copy">${escapeHtml(section.description)}</p>
          ${
            section.items.length
              ? `<ul class="today-list">${section.items
                  .map(
                    (item) => `
                      <li class="today-item">
                        <div class="item-top">
                          <strong>${escapeHtml(item.name)}</strong>
                          <span class="meta">${escapeHtml(item.due)}</span>
                        </div>
                        <div class="item-meta">${escapeHtml(item.course)} · ${escapeHtml(item.status)}</div>
                      </li>
                    `,
                  )
                  .join("")}</ul>`
              : '<p class="empty">Nothing here.</p>'
          }
        </div>
      `,
    )
    .join("")}</div>`;
}

export function renderChangesMarkup(changeGroups) {
  const groups = (changeGroups ?? []).filter((group) => group.items.length);
  if (!groups.length) {
    return '<p class="empty">No changes since the last successful sync.</p>';
  }

  return `<div class="stack">${groups
    .map(
      (group) => `
        <div class="change-group">
          <div class="today-head">
            <h3>${escapeHtml(group.title)}</h3>
            <span class="meta">${group.items.length}</span>
          </div>
          <ul class="change-list">${group.items
            .map(
              (item) => `
                <li class="change-item">
                  <div class="item-top">
                    <strong>${escapeHtml(item.name)}</strong>
                    <span class="meta">${escapeHtml(item.due)}</span>
                  </div>
                  <div class="item-meta">${escapeHtml(item.course)} · ${escapeHtml(item.transition)}</div>
                  ${item.deadlineChange ? `<div class="item-meta">${escapeHtml(item.deadlineChange)}</div>` : ""}
                </li>
              `,
            )
            .join("")}</ul>
        </div>
      `,
    )
    .join("")}</div>`;
}

export function derivePopupState({ settings, assignments, syncError, lastSuccessAt }) {
  const hasSettings = Boolean(String(settings?.apiBaseUrl ?? "").trim() && String(settings?.accessToken ?? "").trim());
  const hasAssignments = Array.isArray(assignments) && assignments.length > 0;
  const hasError = Boolean(String(syncError ?? "").trim());
  const hasSuccessfulSync = Boolean(lastSuccessAt);

  if (!hasSettings) {
    return POPUP_STATES.noCredentials;
  }
  if (hasAssignments && hasError) {
    return POPUP_STATES.staleWithError;
  }
  if (hasAssignments) {
    return POPUP_STATES.ready;
  }
  if (hasError) {
    return POPUP_STATES.errorNoData;
  }
  if (hasSuccessfulSync) {
    return POPUP_STATES.empty;
  }
  return POPUP_STATES.loading;
}

function buildBanner(state, syncError) {
  if (state === POPUP_STATES.staleWithError || state === POPUP_STATES.errorNoData) {
    return { tone: "warning", message: String(syncError) };
  }
  if (state === POPUP_STATES.noCredentials) {
    return { tone: "neutral", message: "Enter your Canvas base URL and access token to sync live assignments." };
  }
  if (state === POPUP_STATES.loading) {
    return { tone: "neutral", message: "Credentials are saved. Waiting for the first successful sync." };
  }
  if (state === POPUP_STATES.empty) {
    return { tone: "safe", message: "Last sync completed. No upcoming assignments were returned." };
  }
  return null;
}

export function buildPopupRenderModel(
  {
    settings = null,
    activeCourseCount = 0,
    assignments = [],
    changes = [],
    changeCounts = null,
    syncError = null,
    lastSuccessAt = null,
    lastAttemptAt = null,
  },
  { now = defaultNow(), uiError = null, settingsVisible = false } = {},
) {
  const state = derivePopupState({ settings, assignments, syncError, lastSuccessAt });
  const view = buildPopupViewModel(
    { activeCourseCount, assignments, changes, changeCounts, lastSuccessAt, syncError },
    { mode: "live", now },
  );
  const banner = uiError
    ? { tone: "warning", message: uiError }
    : buildBanner(state, syncError);

  return {
    state,
    modeLine: state === POPUP_STATES.noCredentials ? "Live Canvas sync is not configured yet." : view.modeLine,
    cards: state === POPUP_STATES.noCredentials ? [] : view.cards,
    todaySections: state === POPUP_STATES.noCredentials ? [] : view.todaySections,
    changeGroups: state === POPUP_STATES.noCredentials ? [] : view.changeGroups,
    banner,
    lastSyncLine: lastSuccessAt ? `Last sync: ${formatRelativeTime(lastSuccessAt, now)}` : "Last sync: never",
    lastAttemptLine: lastAttemptAt ? `Last attempt: ${formatRelativeTime(lastAttemptAt, now)}` : "Last attempt: never",
    laterCount: view.laterCount ?? 0,
    showSettings: state === POPUP_STATES.noCredentials || state === POPUP_STATES.errorNoData || settingsVisible,
    showSettingsToggle: state !== POPUP_STATES.noCredentials,
    settingsToggleLabel: settingsVisible ? "Hide Connection" : "Change Connection",
    showSyncButton: state !== POPUP_STATES.noCredentials,
    emptyMessage:
      state === POPUP_STATES.empty
        ? "Canvas returned no upcoming assignments for this account."
        : state === POPUP_STATES.errorNoData
          ? "No cached assignments are available."
          : "",
    settings: {
      apiBaseUrl: String(settings?.apiBaseUrl ?? ""),
      accessToken: "",
    },
  };
}

function setHidden(element, hidden) {
  if (element) {
    element.hidden = hidden;
  }
}

export function renderPopupDocument(documentRef, model) {
  documentRef.getElementById("mode-line").textContent = model.modeLine;
  documentRef.getElementById("cards").innerHTML = renderCards(model.cards);
  documentRef.getElementById("today").innerHTML = renderTodayMarkup(model.todaySections);
  documentRef.getElementById("changes").innerHTML = renderChangesMarkup(model.changeGroups);
  documentRef.getElementById("sync-meta").innerHTML = `
    <p>${escapeHtml(model.lastSyncLine)}</p>
    <p>${escapeHtml(model.lastAttemptLine)}</p>
    ${model.laterCount ? `<p>${escapeHtml(String(model.laterCount))} assignments due later than seven days.</p>` : ""}
    ${model.emptyMessage ? `<p>${escapeHtml(model.emptyMessage)}</p>` : ""}
  `;

  const banner = documentRef.getElementById("status-banner");
  if (model.banner) {
    banner.textContent = model.banner.message;
    banner.dataset.tone = model.banner.tone;
    setHidden(banner, false);
  } else {
    banner.textContent = "";
    banner.dataset.tone = "";
    setHidden(banner, true);
  }

  setHidden(documentRef.getElementById("settings-panel"), !model.showSettings);
  setHidden(documentRef.getElementById("today-panel"), model.showSettings);
  setHidden(documentRef.getElementById("cards-panel"), model.showSettings);
  setHidden(documentRef.getElementById("changes-panel"), model.showSettings);
  setHidden(documentRef.getElementById("sync-panel"), false);
  setHidden(documentRef.getElementById("sync-now"), !model.showSyncButton);
  const toggleButton = documentRef.getElementById("toggle-settings");
  setHidden(toggleButton, !model.showSettingsToggle);
  toggleButton.textContent = model.settingsToggleLabel;

  const apiBaseUrlInput = documentRef.getElementById("api-base-url");
  const accessTokenInput = documentRef.getElementById("access-token");
  apiBaseUrlInput.value = model.settings.apiBaseUrl;
  accessTokenInput.value = "";
}

export function permissionOriginForBaseUrl(apiBaseUrl) {
  const normalized = normalizeApiBaseUrl(apiBaseUrl);
  const url = new URL(normalized);
  if (url.protocol !== "https:") {
    throw new Error("Canvas URL must use https");
  }
  return `${url.origin}/*`;
}

async function syncNow(chromeApi) {
  return chromeApi.runtime.sendMessage({ type: "duecheck-sync-now" });
}

export async function saveSettings({
  chromeApi = chrome,
  apiBaseUrl,
  accessToken,
  logger = console,
} = {}) {
  void logger;
  const normalizedBase = normalizeApiBaseUrl(apiBaseUrl);
  const token = String(accessToken ?? "").trim();
  if (!token) {
    throw new Error("Canvas access token is required");
  }

  const originPattern = permissionOriginForBaseUrl(normalizedBase);
  const granted = await chromeApi.permissions.request({ origins: [originPattern] });
  if (!granted) {
    return {
      ok: false,
      error: "Permission required to connect to your Canvas instance",
    };
  }

  await chromeApi.storage.local.set({
    settings: {
      apiBaseUrl: normalizedBase,
      accessToken: token,
    },
  });
  const syncResult = await syncNow(chromeApi);
  return { ok: true, syncResult };
}

export async function loadPopupData(chromeApi = chrome) {
  return chromeApi.storage.local.get([
    "settings",
    "activeCourseCount",
    "assignments",
    "changes",
    "changeCounts",
    "syncError",
    "lastAttemptAt",
    "lastSuccessAt",
  ]);
}

export async function bootPopup({
  chromeApi = chrome,
  documentRef = document,
  logger = console,
  now = defaultNow,
} = {}) {
  const settingsForm = documentRef.getElementById("settings-form");
  const syncButton = documentRef.getElementById("sync-now");
  const toggleSettingsButton = documentRef.getElementById("toggle-settings");
  const apiBaseUrlInput = documentRef.getElementById("api-base-url");
  const accessTokenInput = documentRef.getElementById("access-token");

  let uiError = null;
  let settingsVisible = false;

  async function render() {
    const data = await loadPopupData(chromeApi);
    const model = buildPopupRenderModel(data, { now: now(), uiError, settingsVisible });
    renderPopupDocument(documentRef, model);
  }

  settingsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    uiError = null;
    try {
      const result = await saveSettings({
        chromeApi,
        apiBaseUrl: apiBaseUrlInput.value,
        accessToken: accessTokenInput.value,
        logger,
      });
      if (!result.ok) {
        uiError = result.error;
      } else {
        settingsVisible = false;
      }
    } catch (error) {
      uiError = error instanceof Error ? error.message : String(error);
    } finally {
      accessTokenInput.value = "";
      await render();
    }
  });

  toggleSettingsButton.addEventListener("click", async () => {
    settingsVisible = !settingsVisible;
    uiError = null;
    await render();
  });

  syncButton.addEventListener("click", async () => {
    uiError = null;
    try {
      await syncNow(chromeApi);
    } catch (error) {
      uiError = error instanceof Error ? error.message : String(error);
    }
    await render();
  });

  await render();
}
