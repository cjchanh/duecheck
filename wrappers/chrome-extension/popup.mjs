import { getBundle, seedDemoBundle } from "./lib/storage.mjs";
import { buildPopupViewModel } from "./lib/view-model.mjs";

function renderCards(cards) {
  return cards
    .map(
      (card) => `
        <article class="card tone-${card.tone}">
          <div class="card-label">${card.label}</div>
          <div class="card-value">${card.value}</div>
        </article>
      `,
    )
    .join("");
}

function renderToday(todaySections) {
  return `<div class="stack">${todaySections
    .map(
      (section) => `
        <div class="today-block">
          <div class="today-head">
            <h3>${section.title}</h3>
            <span class="meta">${section.items.length}</span>
          </div>
          <p class="today-copy">${section.description}</p>
          ${
            section.items.length
              ? `<ul class="today-list">${section.items
                  .map(
                    (item) => `
                      <li class="today-item">
                        <div class="item-top">
                          <strong>${item.name}</strong>
                          <span class="meta">${item.due}</span>
                        </div>
                        <div class="item-meta">${item.course} · ${item.status}</div>
                      </li>
                    `,
                  )
                  .join("")}</ul>`
              : '<p class="empty">Nothing here.</p>'
          }
        </div>
      `,
    )
    .join("")}</div>`;
}

function renderChanges(changeGroups) {
  return `<div class="stack">${changeGroups
    .map(
      (group) => `
        <div class="change-group">
          <h3>${group.title}</h3>
          ${
            group.items.length
              ? `<ul class="change-list">${group.items
                  .map(
                    (item) => `
                      <li class="change-item">
                        <div class="item-top">
                          <strong>${item.name}</strong>
                          <span class="meta">${item.due}</span>
                        </div>
                        <div class="item-meta">${item.course}</div>
                        <div class="item-meta">${item.transition}${
                          item.deadlineChange ? ` · ${item.deadlineChange}` : ""
                        }</div>
                      </li>
                    `,
                  )
                  .join("")}</ul>`
              : '<p class="empty">None.</p>'
          }
        </div>
      `,
    )
    .join("")}</div>`;
}

function renderCourseRisk(courseRisks) {
  if (!courseRisks.length) {
    return '<p class="empty">No course data.</p>';
  }
  return `<ul class="pill-list">${courseRisks
    .map(
      (item) => `
        <li class="pill tone-${item.tone}">
          <span>${item.course}</span>
          <strong>${item.level}</strong>
        </li>
      `,
    )
    .join("")}</ul>`;
}

async function render() {
  const { bundle, mode } = await getBundle();
  const view = buildPopupViewModel(bundle ?? {}, { mode });
  document.getElementById("mode-line").textContent = view.modeLine;
  document.getElementById("cards").innerHTML = renderCards(view.cards);
  document.getElementById("today").innerHTML = renderToday(view.todaySections);
  document.getElementById("changes").innerHTML = renderChanges(view.changeGroups);
  document.getElementById("course-risk").innerHTML = renderCourseRisk(view.courseRisks);
}

document.getElementById("reload-demo").addEventListener("click", async () => {
  await seedDemoBundle();
  await render();
});

void render();
