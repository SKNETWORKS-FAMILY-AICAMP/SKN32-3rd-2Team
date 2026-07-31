let currentPage = 1;

document.addEventListener("DOMContentLoaded", function () {
  loadUsers(1);

  document.getElementById("f-search").addEventListener("click", function () {
    loadUsers(1);
  });

  // 행 클릭 -> 수정 모달 (SSR로 렌더된 행 / JS로 다시 그려진 행 모두 이벤트 위임으로 처리)
  document.getElementById("user-list").addEventListener("click", function (e) {
    const tr = e.target.closest("tr");
    if (!tr) return;

    openUserModal("edit", {
      userId: tr.dataset.userId,
      name: tr.dataset.name,
      department: tr.dataset.department,
      isAdmin: tr.dataset.isAdmin === "true",
      isDisabled: tr.dataset.isDisabled === "true",
    });
  });
});

function currentFilters() {
  const isAdmin = document.getElementById("f-is-admin").value;
  const isDisabled = document.getElementById("f-is-disabled").value;

  return {
    name: document.getElementById("f-name").value.trim(),
    department: document.getElementById("f-department").value.trim(),
    is_admin: isAdmin,
    is_disabled: isDisabled,
  };
}

async function loadUsers(page = 1) {
  currentPage = page;
  const filters = currentFilters();
  const params = new URLSearchParams({ page });

  if (filters.name) params.set("name", filters.name);
  if (filters.department) params.set("department", filters.department);
  if (filters.is_admin) params.set("is_admin", filters.is_admin);
  if (filters.is_disabled) params.set("is_disabled", filters.is_disabled);

  const res = await fetch(`/admin/users/api/list?${params.toString()}`);

  if (!res.ok) {
    if (res.status === 403) {
      alert("관리자만 접근할 수 있습니다.");
    }
    return;
  }

  const data = await res.json();
  const tbody = document.querySelector("#user-list");

  tbody.innerHTML = data.items.map(user => `
        <tr data-user-id="${user.id}" data-name="${user.name}" data-department="${user.department}"
            data-is-admin="${user.is_admin}" data-is-disabled="${user.is_disabled}">
            <td>${user.id}</td>
            <td>${user.name}</td>
            <td>${user.department}</td>
            <td><span class="badge ${user.is_disabled ? "badge-off" : "badge-on"}">${user.is_disabled ? "비활성" : "활성"}</span></td>
            <td>${user.is_admin ? "관리자" : "일반"}</td>
            <td>${user.created_at}</td>
        </tr>
    `).join("");

  renderPagination(data);
}

function renderPagination(data) {
  const container = document.querySelector("#pagination");
  let html = "";

  for (let i = 1; i <= data.total_pages; i++) {
    html += `<button class="${i === data.page ? "active" : ""}" onclick="loadUsers(${i})">${i}</button>`;
  }

  container.innerHTML = html;
}