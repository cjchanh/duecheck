import assert from "node:assert/strict";
import { test } from "node:test";

import { fetchCanvasSnapshot, fetchUpcomingAssignments } from "../src/canvas-client.mjs";

function response(payload, { ok = true, status = 200, link = null } = {}) {
  return {
    ok,
    status,
    async json() {
      return payload;
    },
    headers: {
      get(name) {
        return name.toLowerCase() === "link" ? link : null;
      },
    },
  };
}

test("threat_no_token_throws", async () => {
  let fetchCalls = 0;
  await assert.rejects(
    () =>
      fetchUpcomingAssignments("https://canvas.example.edu", "", {
        fetchImpl: async () => {
          fetchCalls += 1;
          return response([]);
        },
      }),
    /Canvas access token is required/,
  );
  assert.equal(fetchCalls, 0);
});

test("threat_api_error_propagates", async () => {
  await assert.rejects(
    () =>
      fetchUpcomingAssignments("https://canvas.example.edu", "token", {
        fetchImpl: async () => response([], { ok: false, status: 403 }),
      }),
    /403/,
  );
});

test("threat_invalid_base_url_throws", async () => {
  let fetchCalls = 0;
  await assert.rejects(
    () =>
      fetchUpcomingAssignments("not-a-url", "token", {
        fetchImpl: async () => {
          fetchCalls += 1;
          return response([]);
        },
      }),
    /Invalid Canvas base URL/,
  );
  assert.equal(fetchCalls, 0);
});

test("test_parses_assignments_correctly", async () => {
  const calls = [];
  const snapshot = await fetchCanvasSnapshot("https://canvas.example.edu/", "token", {
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      if (url.includes("/courses?")) {
        return response([{ id: 101, name: "English Composition" }]);
      }
      return response([
        {
          id: 555,
          name: "Essay Draft",
          due_at: "2026-03-10T23:59:00Z",
          points_possible: 100,
          html_url: "https://canvas.example.edu/courses/101/assignments/555",
          workflow_state: "published",
          has_submitted_submissions: false,
        },
      ]);
    },
  });

  assert.equal(snapshot.activeCourseCount, 1);
  assert.equal(snapshot.assignments.length, 1);
  assert.deepEqual(snapshot.assignments[0], {
    id: 555,
    courseId: 101,
    courseName: "English Composition",
    name: "Essay Draft",
    dueAt: "2026-03-10T23:59:00Z",
    pointsPossible: 100,
    htmlUrl: "https://canvas.example.edu/courses/101/assignments/555",
    workflowState: "published",
    hasSubmittedSubmission: false,
  });
  assert.equal(calls[0].options.headers.Authorization, "Bearer token");
});

test("test_handles_empty_courses", async () => {
  const snapshot = await fetchCanvasSnapshot("https://canvas.example.edu", "token", {
    fetchImpl: async () => response([]),
  });
  assert.deepEqual(snapshot, {
    activeCourseCount: 0,
    assignments: [],
  });
});

test("test_follows_course_pagination", async () => {
  const urls = [];
  const snapshot = await fetchCanvasSnapshot("https://canvas.example.edu", "token", {
    fetchImpl: async (url) => {
      urls.push(url);
      if (url === "https://canvas.example.edu/api/v1/courses?enrollment_state=active") {
        return response([{ id: 101, name: "English" }], {
          link: '<https://canvas.example.edu/api/v1/courses?page=2>; rel="next"',
        });
      }
      if (url === "https://canvas.example.edu/api/v1/courses?page=2") {
        return response([{ id: 102, name: "History" }]);
      }
      if (url.includes("/courses/101/assignments")) {
        return response([{ id: 1, name: "Essay", due_at: null }]);
      }
      return response([{ id: 2, name: "Quiz", due_at: null }]);
    },
  });

  assert.equal(snapshot.activeCourseCount, 2);
  assert.equal(snapshot.assignments.length, 2);
  assert.equal(urls.includes("https://canvas.example.edu/api/v1/courses?page=2"), true);
});

test("test_follows_assignment_pagination", async () => {
  const urls = [];
  const snapshot = await fetchCanvasSnapshot("https://canvas.example.edu", "token", {
    fetchImpl: async (url) => {
      urls.push(url);
      if (url.includes("/courses?")) {
        return response([{ id: 101, name: "English" }]);
      }
      if (url === "https://canvas.example.edu/api/v1/courses/101/assignments?bucket=upcoming&order_by=due_at") {
        return response([{ id: 1, name: "Essay", due_at: null }], {
          link: '<https://canvas.example.edu/api/v1/courses/101/assignments?page=2>; rel="next"',
        });
      }
      return response([{ id: 2, name: "Quiz", due_at: null }]);
    },
  });

  assert.equal(snapshot.assignments.length, 2);
  assert.equal(urls.includes("https://canvas.example.edu/api/v1/courses/101/assignments?page=2"), true);
});

test("test_fetch_upcoming_assignments_keeps_compatibility_wrapper", async () => {
  const assignments = await fetchUpcomingAssignments("https://canvas.example.edu", "token", {
    fetchImpl: async (url) => {
      if (url.includes("/courses?")) {
        return response([{ id: 101, name: "English" }]);
      }
      return response([{ id: 1, name: "Essay", due_at: null }]);
    },
  });

  assert.equal(assignments.length, 1);
  assert.equal(assignments[0].courseName, "English");
});
