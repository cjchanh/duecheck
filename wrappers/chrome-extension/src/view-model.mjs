const BUNDLE_TODAY_SECTIONS = [
  ["missing", "Overdue", "Canvas already marked these as missing."],
  ["due_48h", "Due In 48 Hours", "Handle these before the dashboard drift hides them."],
  ["due_7d", "Due This Week", "Keep the next wave visible before it turns urgent."],
];

const CHANGE_ORDER = [
  ["new", "New"],
  ["reactivated", "Reactivated"],
  ["became_missing", "Became Missing"],
  ["escalated", "Escalated"],
  ["de_escalated", "De-escalated"],
  ["cleared", "Cleared"],
];

function toneForRisk(level) {
  return {
    HIGH: "danger",
    MEDIUM: "warning",
    LOW: "safe",
  }[level] ?? "neutral";
}

function sortBundleActiveItems(left, right) {
  const statusOrder = { missing: 0, due_48h: 1, due_7d: 2, not_observed: 3 };
  const leftStatus = statusOrder[left.status] ?? 9;
  const rightStatus = statusOrder[right.status] ?? 9;
  if (leftStatus !== rightStatus) {
    return leftStatus - rightStatus;
  }
  return `${left.due_at}|${left.course}|${left.name}`.localeCompare(
    `${right.due_at}|${right.course}|${right.name}`,
  );
}

function formatDue(dueAt) {
  if (!dueAt) {
    return "No due date";
  }
  const date = new Date(dueAt);
  if (Number.isNaN(date.getTime())) {
    return dueAt;
  }
  return (
    new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "UTC",
    }).format(date) + " UTC"
  );
}

function buildBundleViewModel(bundle, { mode = "demo" } = {}) {
  const ledger = Array.isArray(bundle?.ledger) ? bundle.ledger : [];
  const delta = bundle?.delta ?? {};
  const risk = bundle?.risk ?? {};
  const activeItems = ledger.filter((item) => item.status !== "not_observed").sort(sortBundleActiveItems);
  const escalations = Number(delta.counts?.escalated ?? 0) + Number(delta.counts?.became_missing ?? 0);
  return {
    modeLine:
      mode === "demo"
        ? "Demo preview loaded from the real DueCheck artifact bundle."
        : "Stored bundle loaded from extension storage.",
    cards: [
      { label: "Courses", value: String(Object.keys(risk.course_risks ?? {}).length), tone: "neutral" },
      { label: "Active Items", value: String(activeItems.length), tone: "neutral" },
      { label: "New Changes", value: String(delta.counts?.new ?? 0), tone: "safe" },
      { label: "Escalations", value: String(escalations), tone: "warning" },
      { label: "Missing", value: String(risk.missing_count ?? 0), tone: toneForRisk(risk.missing_risk) },
      { label: "Overall Risk", value: String(risk.overall ?? "UNKNOWN"), tone: toneForRisk(risk.overall) },
    ],
    todaySections: BUNDLE_TODAY_SECTIONS.map(([status, title, description]) => ({
      status,
      title,
      description,
      items: activeItems
        .filter((item) => item.status === status)
        .map((item) => ({
          name: item.name,
          course: item.course,
          status: item.status,
          due: formatDue(item.due_at),
        })),
    })),
    changeGroups: CHANGE_ORDER.map(([changeType, title]) => ({
      changeType,
      title,
      items: Array.isArray(delta.changes)
        ? delta.changes
            .filter((item) => item.change_type === changeType)
            .map((item) => ({
              name: item.name,
              course: item.course,
              transition: `${item.from_status} → ${item.to_status}`,
              deadlineChange: item.deadline_change || "",
              due: (item.to_due_at || item.from_due_at || "").slice(0, 10) || "NO-DUE-DATE",
            }))
        : [],
    })),
    courseRisks: Object.entries(risk.course_risks ?? {}).map(([course, level]) => ({
      course,
      level,
      tone: toneForRisk(level),
    })),
  };
}

function sortAssignments(left, right) {
  return `${left.dueAt ?? ""}|${left.courseName}|${left.name}`.localeCompare(
    `${right.dueAt ?? ""}|${right.courseName}|${right.name}`,
  );
}

function summarizeAssignments(assignments, now) {
  const overdue = [];
  const due48 = [];
  const due7 = [];
  const later = [];
  const nowMs = now.getTime();
  const fortyEightHoursMs = 48 * 60 * 60 * 1000;
  const sevenDaysMs = 7 * 24 * 60 * 60 * 1000;

  for (const assignment of assignments.sort(sortAssignments)) {
    const dueDate = assignment.dueAt ? new Date(assignment.dueAt) : null;
    const item = {
      name: assignment.name,
      course: assignment.courseName,
      due: formatDue(assignment.dueAt),
      status: "upcoming",
    };
    if (!dueDate || Number.isNaN(dueDate.getTime())) {
      later.push(item);
      continue;
    }
    const delta = dueDate.getTime() - nowMs;
    if (delta < 0) {
      overdue.push(item);
    } else if (delta <= fortyEightHoursMs) {
      due48.push(item);
    } else if (delta <= sevenDaysMs) {
      due7.push(item);
    } else {
      later.push(item);
    }
  }

  return { overdue, due48, due7, later };
}

function buildLiveViewModel(payload, { now = new Date() } = {}) {
  const assignments = Array.isArray(payload?.assignments) ? [...payload.assignments] : [];
  const grouped = summarizeAssignments(assignments, now);
  const courseCount = new Set(assignments.map((assignment) => assignment.courseId ?? assignment.courseName)).size;

  return {
    modeLine: "Live Canvas preview. Upcoming assignments only in this phase.",
    cards: [
      { label: "Courses", value: String(courseCount), tone: "neutral" },
      { label: "Upcoming", value: String(assignments.length), tone: "neutral" },
      { label: "Due In 48 Hours", value: String(grouped.due48.length), tone: "warning" },
      { label: "Due This Week", value: String(grouped.due7.length), tone: "safe" },
    ],
    todaySections: [
      {
        status: "overdue",
        title: "Overdue",
        description: "Canvas can still surface overdue items here even before parity features land.",
        items: grouped.overdue,
      },
      {
        status: "due_48h",
        title: "Due In 48 Hours",
        description: "The next urgent assignments from your live Canvas data.",
        items: grouped.due48,
      },
      {
        status: "due_7d",
        title: "Due This Week",
        description: "Upcoming work due within the next seven days.",
        items: grouped.due7,
      },
    ],
    laterCount: grouped.later.length,
    changeGroups: [],
    courseRisks: [],
  };
}

export function buildPopupViewModel(payload, options = {}) {
  if (Array.isArray(payload?.ledger) || payload?.delta || payload?.risk) {
    return buildBundleViewModel(payload, options);
  }
  return buildLiveViewModel(payload, options);
}
