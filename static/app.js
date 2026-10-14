// Shared API client and helpers per Doc 04 Section 3

// 1. api(method, path, body)
async function api(method, path, body = null) {
  const headers = { "Content-Type": "application/json" };
  const token = localStorage.getItem("token");
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const options = { method, headers };
  if (body) {
    options.body = JSON.stringify(body);
  }

  let res;
  try {
    res = await fetch(`/api${path}`, options);
  } catch (err) {
    throw { status: 0, code: "NETWORK_ERROR", message: "Network connection failed" };
  }

  if (res.status === 401) {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    if (!window.location.pathname.endsWith("index.html") && window.location.pathname !== "/") {
      window.location.href = "index.html";
    }
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const errorDetail = data.detail || {};
    const code = typeof errorDetail === "object" ? errorDetail.code : "ERROR";
    const message = typeof errorDetail === "object" ? errorDetail.message : (errorDetail || "An error occurred");
    throw { status: res.status, code, message };
  }

  return data;
}

// 2. requireRole(expectedRole)
function requireRole(expectedRole) {
  const token = localStorage.getItem("token");
  const userStr = localStorage.getItem("user");
  if (!token || !userStr) {
    window.location.href = "index.html";
    return null;
  }
  const user = JSON.parse(userStr);
  if (user.role !== expectedRole) {
    window.location.href = "index.html";
    return null;
  }
  return user;
}

// 3. fmt(isoString) -> IST formatted date string
function fmt(isoString) {
  if (!isoString) return "";
  const dt = new Date(isoString);
  return dt.toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

// 4. toast(message, kind)
function toast(message, kind = "error") {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    document.body.appendChild(container);
  }

  const el = document.createElement("div");
  el.className = `toast toast-${kind}`;
  el.textContent = message; // Always textContent to prevent XSS
  container.appendChild(el);

  setTimeout(() => {
    el.remove();
  }, 3500);
}

// 5. badge(effective_status)
function badge(status) {
  const span = document.createElement("span");
  const s = (status || "").toLowerCase();
  span.className = `badge badge-${s}`;
  span.textContent = s;
  return span;
}

// 6. logout()
function logout() {
  localStorage.removeItem("token");
  localStorage.removeItem("user");
  window.location.href = "index.html";
}

// 7. startNotifications()
// Bell icon in the header with unread count; polls /api/notifications every 30s
function startNotifications() {
  const bellContainer = document.getElementById("notif-bell-container");
  if (!bellContainer) return;

  const bellBtn = document.getElementById("notif-bell-btn");
  const countBadge = document.getElementById("notif-count-badge");
  const dropdown = document.getElementById("notif-dropdown");
  const listEl = document.getElementById("notif-list");

  async function loadNotifications() {
    try {
      const data = await api("GET", "/notifications");
      if (data.unread_count > 0) {
        countBadge.style.display = "inline-block";
        countBadge.textContent = String(data.unread_count);
      } else {
        countBadge.style.display = "none";
      }

      // Populate list
      listEl.innerHTML = "";
      if (!data.notifications || data.notifications.length === 0) {
        const emptyItem = document.createElement("div");
        emptyItem.className = "notif-item notif-empty";
        emptyItem.textContent = "No notifications";
        listEl.appendChild(emptyItem);
        return;
      }

      data.notifications.forEach((item) => {
        const row = document.createElement("div");
        row.className = `notif-item ${item.read_at ? "read" : "unread"}`;

        const msgSpan = document.createElement("div");
        msgSpan.className = "notif-msg";
        msgSpan.textContent = item.message;

        const timeSpan = document.createElement("div");
        timeSpan.className = "notif-time";
        timeSpan.textContent = fmt(item.created_at);

        row.appendChild(msgSpan);
        row.appendChild(timeSpan);

        if (!item.read_at) {
          row.style.cursor = "pointer";
          row.addEventListener("click", async () => {
            try {
              await api("POST", `/notifications/${item.id}/read`);
              row.className = "notif-item read";
              loadNotifications();
            } catch (err) {
              console.error(err);
            }
          });
        }

        listEl.appendChild(row);
      });
    } catch (err) {
      console.error("Failed to load notifications", err);
    }
  }

  bellBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    const isVisible = dropdown.style.display === "block";
    dropdown.style.display = isVisible ? "none" : "block";
  });

  document.addEventListener("click", () => {
    dropdown.style.display = "none";
  });

  dropdown.addEventListener("click", (e) => {
    e.stopPropagation();
  });

  loadNotifications();
  setInterval(loadNotifications, 30000); // Poll every 30 seconds
}

