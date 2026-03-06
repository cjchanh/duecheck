function requireToken(accessToken) {
  const token = String(accessToken ?? "").trim();
  if (!token) {
    throw new Error("Canvas access token is required");
  }
  return token;
}

export function normalizeApiBaseUrl(apiBaseUrl) {
  let parsed;
  try {
    parsed = new URL(String(apiBaseUrl ?? "").trim());
  } catch (error) {
    throw new Error(`Invalid Canvas base URL: ${error instanceof Error ? error.message : String(error)}`);
  }

  parsed.hash = "";
  parsed.search = "";
  parsed.pathname = parsed.pathname.replace(/\/+$/, "") || "";
  return parsed.toString().replace(/\/$/, "");
}

function parseLinkHeader(headerValue) {
  if (!headerValue) {
    return {};
  }

  const links = {};
  for (const segment of headerValue.split(",")) {
    const [urlPart, ...paramParts] = segment.split(";");
    const match = urlPart.match(/<([^>]+)>/);
    if (!match) {
      continue;
    }
    const relPart = paramParts
      .map((part) => part.trim())
      .find((part) => part.startsWith("rel="));
    if (!relPart) {
      continue;
    }
    const rel = relPart.replace(/^rel=/, "").replace(/^"|"$/g, "");
    links[rel] = match[1];
  }
  return links;
}

async function fetchPaginatedJson(url, { fetchImpl, headers }) {
  const rows = [];
  let nextUrl = url;

  while (nextUrl) {
    const response = await fetchImpl(nextUrl, { headers });
    if (!response.ok) {
      throw new Error(`Canvas API request failed: ${response.status} ${nextUrl}`);
    }

    const payload = await response.json();
    if (!Array.isArray(payload)) {
      throw new Error(`Canvas API returned non-array payload: ${nextUrl}`);
    }
    rows.push(...payload);

    const linkHeader = typeof response.headers?.get === "function" ? response.headers.get("link") : null;
    nextUrl = parseLinkHeader(linkHeader).next ?? null;
  }

  return rows;
}

function normalizeAssignment(course, assignment) {
  const rawSubmitted = assignment.has_submitted_submissions;
  const hasSubmittedSubmission = typeof rawSubmitted === "boolean" ? rawSubmitted : null;

  return {
    id: assignment.id ?? null,
    courseId: course.id ?? null,
    courseName: String(course.name ?? course.course_code ?? `Course ${course.id ?? "Unknown"}`),
    name: String(assignment.name ?? "Unnamed assignment"),
    dueAt: assignment.due_at ?? null,
    pointsPossible: assignment.points_possible ?? null,
    htmlUrl: assignment.html_url ?? null,
    workflowState: assignment.workflow_state ?? null,
    hasSubmittedSubmission,
  };
}

export async function fetchUpcomingAssignments(apiBaseUrl, accessToken, { fetchImpl = fetch } = {}) {
  const normalizedBase = normalizeApiBaseUrl(apiBaseUrl);
  const token = requireToken(accessToken);
  const headers = {
    Authorization: `Bearer ${token}`,
  };

  const coursesUrl = new URL("/api/v1/courses", normalizedBase);
  coursesUrl.searchParams.set("enrollment_state", "active");
  const courses = await fetchPaginatedJson(coursesUrl.toString(), { fetchImpl, headers });
  if (!courses.length) {
    return [];
  }

  const assignments = [];
  for (const course of courses) {
    const assignmentsUrl = new URL(`/api/v1/courses/${course.id}/assignments`, normalizedBase);
    assignmentsUrl.searchParams.set("bucket", "upcoming");
    assignmentsUrl.searchParams.set("order_by", "due_at");

    const courseAssignments = await fetchPaginatedJson(assignmentsUrl.toString(), { fetchImpl, headers });
    assignments.push(...courseAssignments.map((assignment) => normalizeAssignment(course, assignment)));
  }

  return assignments.sort((left, right) =>
    `${left.dueAt ?? ""}|${left.courseName}|${left.name}`.localeCompare(
      `${right.dueAt ?? ""}|${right.courseName}|${right.name}`,
    ),
  );
}
