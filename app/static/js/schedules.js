'use strict';
// O link abre o formulário de criação no servidor, inclusive durante uma edição.
if (window.location.hash === '#assignment-form') {
  document.getElementById('employee_id')?.focus({
    preventScroll: true
  });
}
