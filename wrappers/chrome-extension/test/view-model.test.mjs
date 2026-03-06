import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { buildPopupViewModel } from "../src/view-model.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const sampleBundle = JSON.parse(readFileSync(join(here, "..", "fixtures", "sample-bundle.json"), "utf8"));

test("popup view model exposes today sections from sample bundle", () => {
  const model = buildPopupViewModel(sampleBundle, { mode: "demo" });
  const overdue = model.todaySections.find((section) => section.status === "missing");
  const dueSoon = model.todaySections.find((section) => section.status === "due_48h");
  const dueWeek = model.todaySections.find((section) => section.status === "due_7d");

  assert.equal(overdue.items.length, 1);
  assert.equal(dueSoon.items.length, 2);
  assert.equal(dueWeek.items.length, 2);
});

test("popup view model mirrors risk and escalation cards", () => {
  const model = buildPopupViewModel(sampleBundle, { mode: "demo" });
  const cards = Object.fromEntries(model.cards.map((card) => [card.label, card.value]));

  assert.equal(cards["Overall Risk"], "MEDIUM");
  assert.equal(cards["Missing"], "1");
  assert.equal(cards["Escalations"], "2");
});

test("popup view model groups change feed from the artifact delta", () => {
  const model = buildPopupViewModel(sampleBundle, { mode: "demo" });
  const groups = Object.fromEntries(model.changeGroups.map((group) => [group.changeType, group.items.length]));

  assert.equal(groups.new, 2);
  assert.equal(groups.became_missing, 1);
  assert.equal(groups.escalated, 1);
  assert.equal(groups.de_escalated, 1);
});
