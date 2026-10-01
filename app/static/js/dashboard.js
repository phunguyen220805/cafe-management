const menuToggle = document.querySelector("[data-sidebar-toggle]");
const closeControl = document.querySelector("[data-sidebar-close]");

function setSidebarOpen(isOpen) {
  document.body.classList.toggle("sidebar-open", isOpen);
  menuToggle?.setAttribute("aria-expanded", String(isOpen));
  menuToggle?.setAttribute("aria-label", isOpen ? "Đóng điều hướng" : "Mở điều hướng");
}

menuToggle?.addEventListener("click", () => {
  setSidebarOpen(!document.body.classList.contains("sidebar-open"));
});

closeControl?.addEventListener("click", () => setSidebarOpen(false));

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") setSidebarOpen(false);
});