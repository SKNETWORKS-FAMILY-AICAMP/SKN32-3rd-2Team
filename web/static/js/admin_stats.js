const CATEGORY_COLORS = {
  "휴가/휴직": "#2a78d6",
  "근태/근무형태": "#eb6834",
  "급여/보수": "#1baf7a",
  "채용/임용": "#eda100",
  "인사/승진": "#e87ba4",
  "복리후생": "#008300",
  "복무/징계": "#4a3aa7",
  "기타": "#898781",
};

document.addEventListener("DOMContentLoaded", async function () {
  const res = await fetch("/admin/stats/api/summary");
  if (!res.ok) return;

  const data = await res.json();

  renderStatCards(data.user_summary);
  renderCategoryDonut(data.category_ratio);
  renderDailyTrend(data.daily_trend);
  renderFaqTable(data.faq_top10);
});

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function renderStatCards(summary) {
  const container = document.getElementById("stat-cards");

  const cards = [
    { label: "총 질문 수", value: `${summary.total_questions}건` },
    { label: "활성 유저 수", value: `${summary.active_users}명` },
    { label: "유저당 평균 질문 수", value: `${summary.avg_per_user}건` },
    { label: "최다 질문 유저", value: `${escapeHtml(summary.top_user_name)} (${summary.top_user_count}건)` },
  ];

  container.innerHTML = cards.map(c => `
        <div class="stat-card">
            <div class="stat-card-label">${c.label}</div>
            <div class="stat-card-value">${c.value}</div>
        </div>
    `).join("");
}

function renderCategoryDonut(items) {
  const ctx = document.getElementById("category-donut");
  const colors = items.map(i => CATEGORY_COLORS[i.category] || CATEGORY_COLORS["기타"]);

  new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: items.map(i => i.category),
      datasets: [{
        data: items.map(i => i.count),
        backgroundColor: colors,
        borderColor: "#ffffff",
        borderWidth: 2,
      }],
    },
    options: {
      cutout: "62%",
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              const item = items[ctx.dataIndex];
              return `${item.category}: ${item.count}건 (${item.percent}%)`;
            },
          },
        },
      },
    },
  });

  const legend = document.getElementById("category-legend");

  if (!items.length) {
    legend.innerHTML = `<li class="legend-empty">데이터가 없습니다</li>`;
    return;
  }

  legend.innerHTML = items.map((item, idx) => `
        <li>
            <span class="legend-dot" style="background:${colors[idx]}"></span>
            ${escapeHtml(item.category)} <span class="legend-value">${item.percent}%</span>
        </li>
    `).join("");
}

function renderDailyTrend(items) {
  const ctx = document.getElementById("daily-trend-line");

  new Chart(ctx, {
    type: "line",
    data: {
      labels: items.map(i => i.date),
      datasets: [{
        data: items.map(i => i.count),
        borderColor: "#2a78d6",
        backgroundColor: "rgba(42, 120, 214, 0.10)",
        borderWidth: 2,
        pointRadius: 3,
        pointBackgroundColor: "#2a78d6",
        fill: true,
        tension: 0.25,
      }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: "#e2e4ea" } },
      },
    },
  });
}

function renderFaqTable(items) {
  const tbody = document.getElementById("faq-list");

  if (!items.length) {
    tbody.innerHTML = `<tr><td colspan="4" class="empty-cell">아직 문의 데이터가 없습니다.</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map(item => `
        <tr>
            <td>${item.rank}</td>
            <td>${escapeHtml(item.message)}</td>
            <td><span class="badge badge-category">${escapeHtml(item.category)}</span></td>
            <td>${item.count}</td>
        </tr>
    `).join("");
}
