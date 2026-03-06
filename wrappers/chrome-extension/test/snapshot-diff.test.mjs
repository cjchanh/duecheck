import assert from "node:assert/strict";
import { test } from "node:test";

import { assignmentBucket, assignmentKey, diffAssignmentSnapshots } from "../src/snapshot-diff.mjs";

function assignment(overrides = {}) {
  return {
    id: 1,
    courseId: 101,
    courseName: "English",
    name: "Essay",
    dueAt: "2026-03-10T12:00:00Z",
    ...overrides,
  };
}

test("test_assignment_key_prefers_course_and_assignment_identity", () => {
  assert.equal(assignmentKey(assignment()), "101::1");
});

test("test_assignment_bucket_classifies_due_windows", () => {
  const now = new Date("2026-03-06T12:00:00Z");
  assert.equal(assignmentBucket(assignment({ dueAt: "2026-03-06T13:00:00Z" }), now), "due_48h");
  assert.equal(assignmentBucket(assignment({ dueAt: "2026-03-09T12:00:00Z" }), now), "due_7d");
  assert.equal(assignmentBucket(assignment({ dueAt: "2026-03-20T12:00:00Z" }), now), "later");
  assert.equal(assignmentBucket(assignment({ dueAt: "2026-03-05T12:00:00Z" }), now), "overdue");
});

test("test_diff_detects_new_assignment", () => {
  const diff = diffAssignmentSnapshots([], [assignment()], {
    now: new Date("2026-03-06T12:00:00Z"),
  });

  assert.equal(diff.counts.new, 1);
  assert.equal(diff.changes[0].changeType, "new");
});

test("test_diff_detects_escalation_when_due_bucket_worsens", () => {
  const diff = diffAssignmentSnapshots(
    [assignment({ dueAt: "2026-03-15T12:00:00Z" })],
    [assignment({ dueAt: "2026-03-07T12:00:00Z" })],
    { now: new Date("2026-03-06T12:00:00Z") },
  );

  assert.equal(diff.counts.escalated, 1);
  assert.equal(diff.changes[0].changeType, "escalated");
  assert.equal(diff.changes[0].deadlineChange, "deadline_moved_earlier");
});

test("test_diff_detects_deadline_move_without_bucket_change", () => {
  const diff = diffAssignmentSnapshots(
    [assignment({ dueAt: "2026-03-11T12:00:00Z" })],
    [assignment({ dueAt: "2026-03-10T12:00:00Z" })],
    { now: new Date("2026-03-06T12:00:00Z") },
  );

  assert.equal(diff.counts.deadline_moved_earlier, 1);
  assert.equal(diff.changes[0].changeType, "deadline_moved_earlier");
});

test("test_diff_detects_cleared_assignment", () => {
  const diff = diffAssignmentSnapshots([assignment()], [], {
    now: new Date("2026-03-06T12:00:00Z"),
  });

  assert.equal(diff.counts.cleared, 1);
  assert.equal(diff.changes[0].changeType, "cleared");
});

test("test_diff_ignores_unchanged_assignments", () => {
  const diff = diffAssignmentSnapshots([assignment()], [assignment()], {
    now: new Date("2026-03-06T12:00:00Z"),
  });

  assert.deepEqual(diff.counts, {
    new: 0,
    escalated: 0,
    deadline_moved_earlier: 0,
    cleared: 0,
    de_escalated: 0,
    deadline_moved_later: 0,
  });
  assert.deepEqual(diff.changes, []);
});
