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

test("live popup view model exposes active course counts and changes", () => {
  const model = buildPopupViewModel(
    {
      activeCourseCount: 4,
      assignments: [
        { id: 1, courseId: 101, courseName: "English", name: "Essay 1", dueAt: "2026-03-07T12:00:00Z" },
        { id: 2, courseId: 102, courseName: "History", name: "Quiz 2", dueAt: "2026-03-10T12:00:00Z" },
      ],
      changes: [
        {
          changeType: "new",
          fromBucket: "absent",
          toBucket: "due_48h",
          courseName: "English",
          name: "Essay 1",
          toDueAt: "2026-03-07T12:00:00Z",
        },
      ],
      changeCounts: {
        new: 1,
        escalated: 0,
        deadline_moved_earlier: 0,
      },
    },
    { now: new Date("2026-03-06T12:00:00Z") },
  );

  const cards = Object.fromEntries(model.cards.map((card) => [card.label, card.value]));
  const groups = Object.fromEntries(model.changeGroups.map((group) => [group.changeType, group.items.length]));

  assert.equal(cards["Active Courses"], "4");
  assert.equal(cards["Courses With Upcoming Work"], "2");
  assert.equal(cards.New, "1");
  assert.equal(groups.new, 1);
});
