'use strict';
// O link abre o formulário de criação no servidor, inclusive durante uma edição.
document.querySelectorAll('[data-calendar-day]').forEach(day => {
  day.addEventListener('click', event => {
    if (event.target.closest('a, button, input, select, form')) return;
    const link = day.querySelector('.add-day');
    if (link) window.location.assign(link.href);
  });
});

function focusCalendarTarget() {
  const target = window.location.hash === '#assignment-form'
    ? document.getElementById('employee_id')
    : window.location.hash === '#day-detail'
      ? document.getElementById('day-detail')
      : null;
  // A navegação para a âncora pode restaurar o foco após os scripts defer.
  // Aguarda a exibição da página para que o foco escolhido seja preservado.
  if (target) window.requestAnimationFrame(() => target.focus({ preventScroll: true }));
}
window.addEventListener('pageshow', focusCalendarTarget);
window.addEventListener('hashchange', focusCalendarTarget);
