'use strict';
// O servidor continua sendo responsável pela pesquisa e validação.
document.getElementById('q')?.addEventListener('search', event => {
  if (!event.currentTarget.value) event.currentTarget.form.requestSubmit();
});
