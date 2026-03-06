const CHANGE_TYPES = [
  "new",
  "escalated",
  "deadline_moved_earlier",
  "cleared",
  "de_escalated",
  "deadline_moved_later",
];

const CHANGE_PRIORITY = Object.fromEntries(CHANGE_TYPES.map((changeType, index) => [changeType, index]));
const BUCKET_PRIORITY = {
  later: 0,
  due_7d: 1,
  due_48h: 2,
  overdue: 3,
};

function parseDueAt(dueAt) {
  if (!dueAt) {
    return null;
  }
  const parsed = new Date(dueAt);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function assignmentKey(assignment) {
  const courseRef = assignment?.courseId ?? assignment?.courseName ?? "course";
  const assignmentRef = assignment?.id ?? assignment?.name ?? assignment?.htmlUrl ?? "assignment";
  return `${courseRef}::${assignmentRef}`;
}

export function assignmentBucket(assignment, now = new Date()) {
  const dueDate = parseDueAt(assignment?.dueAt);
  if (!dueDate) {
    return "later";
  }

  const delta = dueDate.getTime() - now.getTime();
  if (delta < 0) {
    return "overdue";
  }
  if (delta <= 48 * 60 * 60 * 1000) {
    return "due_48h";
  }
  if (delta <= 7 * 24 * 60 * 60 * 1000) {
    return "due_7d";
  }
  return "later";
}

function buildChange({ changeType, previous, current, previousBucket, currentBucket, deadlineChange }) {
  const source = current ?? previous ?? {};
  return {
    key: assignmentKey(source),
    id: source.id ?? null,
    courseId: source.courseId ?? null,
    courseName: source.courseName ?? "Unknown course",
    name: source.name ?? "Unnamed assignment",
    changeType,
    fromBucket: previousBucket ?? "absent",
    toBucket: currentBucket ?? "absent",
    fromDueAt: previous?.dueAt ?? null,
    toDueAt: current?.dueAt ?? null,
    deadlineChange: deadlineChange ?? "",
  };
}

function compareChanges(left, right) {
  const changeDelta = (CHANGE_PRIORITY[left.changeType] ?? 99) - (CHANGE_PRIORITY[right.changeType] ?? 99);
  if (changeDelta !== 0) {
    return changeDelta;
  }

  return `${left.toDueAt ?? left.fromDueAt ?? ""}|${left.courseName}|${left.name}`.localeCompare(
    `${right.toDueAt ?? right.fromDueAt ?? ""}|${right.courseName}|${right.name}`,
  );
}

export function diffAssignmentSnapshots(previousAssignments, currentAssignments, { now = new Date() } = {}) {
  const previous = new Map((previousAssignments ?? []).map((assignment) => [assignmentKey(assignment), assignment]));
  const current = new Map((currentAssignments ?? []).map((assignment) => [assignmentKey(assignment), assignment]));

  const changes = [];
  const counts = Object.fromEntries(CHANGE_TYPES.map((changeType) => [changeType, 0]));

  for (const [key, assignment] of current.entries()) {
    const previousAssignment = previous.get(key);
    const currentBucket = assignmentBucket(assignment, now);

    if (!previousAssignment) {
      changes.push(
        buildChange({
          changeType: "new",
          previous: null,
          current: assignment,
          previousBucket: "absent",
          currentBucket,
        }),
      );
      counts.new += 1;
      continue;
    }

    const previousBucket = assignmentBucket(previousAssignment, now);
    const previousDue = parseDueAt(previousAssignment.dueAt);
    const currentDue = parseDueAt(assignment.dueAt);
    const deadlineChange =
      previousDue && currentDue
        ? currentDue.getTime() < previousDue.getTime()
          ? "deadline_moved_earlier"
          : currentDue.getTime() > previousDue.getTime()
            ? "deadline_moved_later"
            : ""
        : "";

    const previousPriority = BUCKET_PRIORITY[previousBucket] ?? 0;
    const currentPriority = BUCKET_PRIORITY[currentBucket] ?? 0;

    if (currentPriority > previousPriority) {
      changes.push(
        buildChange({
          changeType: "escalated",
          previous: previousAssignment,
          current: assignment,
          previousBucket,
          currentBucket,
          deadlineChange,
        }),
      );
      counts.escalated += 1;
      continue;
    }

    if (currentPriority < previousPriority) {
      changes.push(
        buildChange({
          changeType: "de_escalated",
          previous: previousAssignment,
          current: assignment,
          previousBucket,
          currentBucket,
          deadlineChange,
        }),
      );
      counts.de_escalated += 1;
      continue;
    }

    if (deadlineChange === "deadline_moved_earlier") {
      changes.push(
        buildChange({
          changeType: "deadline_moved_earlier",
          previous: previousAssignment,
          current: assignment,
          previousBucket,
          currentBucket,
          deadlineChange,
        }),
      );
      counts.deadline_moved_earlier += 1;
      continue;
    }

    if (deadlineChange === "deadline_moved_later") {
      changes.push(
        buildChange({
          changeType: "deadline_moved_later",
          previous: previousAssignment,
          current: assignment,
          previousBucket,
          currentBucket,
          deadlineChange,
        }),
      );
      counts.deadline_moved_later += 1;
    }
  }

  for (const [key, assignment] of previous.entries()) {
    if (current.has(key)) {
      continue;
    }
    changes.push(
      buildChange({
        changeType: "cleared",
        previous: assignment,
        current: null,
        previousBucket: assignmentBucket(assignment, now),
        currentBucket: "absent",
      }),
    );
    counts.cleared += 1;
  }

  return {
    changes: changes.sort(compareChanges),
    counts,
  };
}
