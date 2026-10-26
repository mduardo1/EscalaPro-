'use strict';
const menuToggle = document.querySelector('.menu-toggle');
const overlay = document.querySelector('.sidebar-overlay');

function closeSidebar() {
  document.body.classList.remove('sidebar-open');
  if (overlay) overlay.hidden = true;
  menuToggle?.setAttribute('aria-expanded', 'false');
}
menuToggle?.addEventListener('click', () => {
  const open = document.body.classList.toggle('sidebar-open');
  overlay.hidden = !open;
  menuToggle.setAttribute('aria-expanded', String(open));
});
overlay?.addEventListener('click', closeSidebar);
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') closeSidebar();
});
document.querySelectorAll('.flash-close').forEach(button => button.addEventListener('click', () => button.closest('.flash').remove()));
document.querySelectorAll('form[data-confirm]').forEach(form => {
  form.addEventListener('submit', event => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});
document.querySelectorAll('[data-password-toggle]').forEach(button => {
  const input = document.getElementById(button.getAttribute('aria-controls'));
  if (!input) return;
  button.addEventListener('click', () => {
    const showing = input.type === 'password';
    input.type = showing ? 'text' : 'password';
    button.textContent = showing ? 'Ocultar' : 'Mostrar';
    button.setAttribute('aria-pressed', String(showing));
    button.setAttribute('aria-label', `${showing ? 'Ocultar' : 'Mostrar'} senha: ${button.dataset.fieldLabel}`);
  });
});

document.querySelectorAll('form[data-auth-form]').forEach(form => {
  const submitButton = form.querySelector('button[type="submit"]');
  const status = form.querySelector('.form-status');
  const password = form.querySelector('[name="password"]');
  const confirmation = form.querySelector('[name="confirm_password"]');
  let submitted = false;
  let initialNodes = [];

  function checkConfirmation() {
    if (!confirmation) return;
    confirmation.setCustomValidity(confirmation.value && confirmation.value !== password.value
      ? 'A confirmação da senha não confere.' : '');
    if (confirmation.validity.valid) confirmation.removeAttribute('aria-invalid');
  }
  password?.addEventListener('input', checkConfirmation);
  confirmation?.addEventListener('input', checkConfirmation);
  form.addEventListener('invalid', event => event.target.setAttribute('aria-invalid', 'true'), true);
  form.addEventListener('input', event => {
    if (event.target.validity?.valid) event.target.removeAttribute('aria-invalid');
  });
  form.addEventListener('submit', event => {
    if (event.defaultPrevented) return;
    if (submitted) {
      event.preventDefault();
      return;
    }
    submitted = true;
    initialNodes = [...submitButton.childNodes];
    submitButton.textContent = submitButton.dataset.loadingLabel;
    submitButton.disabled = true;
    submitButton.classList.add('is-loading');
    form.setAttribute('aria-busy', 'true');
    status.textContent = submitButton.dataset.loadingLabel;
  });
  window.addEventListener('pageshow', () => {
    if (!submitted) return;
    submitButton.replaceChildren(...initialNodes);
    submitButton.disabled = false;
    submitButton.classList.remove('is-loading');
    form.removeAttribute('aria-busy');
    status.textContent = '';
    submitted = false;
  });
});
