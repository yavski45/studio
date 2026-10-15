const translateAuthText = text => typeof gettext === 'function' ? gettext(text) : text;
document.addEventListener('htmx:afterSwap', event => {
  if (event.detail.target?.id !== 'auth-card') return;
  document.querySelector('#auth-card [aria-invalid="true"]')?.focus();
});
const showNetworkError = event => {
  const panel = event.detail.elt?.closest('#auth-card, #profile-card');
  if (!panel) return;
  const notice = panel.querySelector('#auth-network-error, #profile-network-error');
  if (notice) {
    notice.textContent = event.type === 'htmx:sendError'
      ? translateAuthText('Le serveur est injoignable. Vérifiez votre connexion et réessayez.')
      : translateAuthText('La demande n’a pas abouti. Le serveur a rencontré une erreur. Réessayez dans un instant.');
    notice.hidden = false;
  }
};
document.addEventListener('htmx:responseError', showNetworkError);
document.addEventListener('htmx:sendError', showNetworkError);
