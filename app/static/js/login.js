document.querySelectorAll("[data-password-toggle]").forEach((toggle) => {
  toggle.addEventListener("click", () => {
    const field = document.getElementById(toggle.dataset.target);
    if (!field) return;

    const showPassword = field.type === "password";
    field.type = showPassword ? "text" : "password";
    toggle.classList.toggle("is-visible", showPassword);
    toggle.setAttribute("aria-pressed", String(showPassword));
    toggle.setAttribute(
      "aria-label",
      showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu",
    );
  });
});