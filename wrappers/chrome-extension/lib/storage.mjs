export async function getBundle() {
  const payload = await chrome.storage.local.get(["duecheck_bundle", "duecheck_mode"]);
  return {
    bundle: payload.duecheck_bundle ?? null,
    mode: payload.duecheck_mode ?? "demo",
  };
}

export async function seedDemoBundle() {
  return chrome.runtime.sendMessage({ type: "seed-demo" });
}
