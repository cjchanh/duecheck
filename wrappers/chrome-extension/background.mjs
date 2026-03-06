async function loadSampleBundle() {
  const response = await fetch(chrome.runtime.getURL("fixtures/sample-bundle.json"));
  if (!response.ok) {
    throw new Error(`Failed to load sample bundle: ${response.status}`);
  }
  return response.json();
}

async function seedDemoBundle() {
  const current = await chrome.storage.local.get(["duecheck_bundle", "duecheck_mode"]);
  if (current.duecheck_bundle) {
    return;
  }
  const bundle = await loadSampleBundle();
  await chrome.storage.local.set({
    duecheck_bundle: bundle,
    duecheck_mode: "demo",
  });
}

chrome.runtime.onInstalled.addListener(() => {
  void seedDemoBundle();
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== "seed-demo") {
    return false;
  }
  void loadSampleBundle()
    .then(async (bundle) => {
      await chrome.storage.local.set({
        duecheck_bundle: bundle,
        duecheck_mode: "demo",
      });
      sendResponse({ ok: true });
    })
    .catch((error) => {
      sendResponse({ ok: false, error: String(error) });
    });
  return true;
});
