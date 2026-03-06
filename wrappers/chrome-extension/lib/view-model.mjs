const TODAY_SECTIONS = [
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

function sortActiveItems(left, right) {
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
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(date) + " UTC";
}

export function buildPopupViewModel(bundle, { mode = "demo" } = {}) {
  const ledger = Array.isArray(bundle?.ledger) ? bundle.ledger : [];
  const delta = bundle?.delta ?? {};
  const risk = bundle?.risk ?? {};
  const activeItems = ledger.filter((item) => item.status !== "not_observed").sort(sortActiveItems);
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
    todaySections: TODAY_SECTIONS.map(([status, title, description]) => ({
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
