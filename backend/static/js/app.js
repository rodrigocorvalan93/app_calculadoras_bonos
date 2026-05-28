// Minimal client-side glue. Phase 1: only htmx + Alpine + a couple of
// helpers for es-AR input. WebSocket handlers land in Phase 4.

(function () {
  // Format an Argentine number while typing: '1234567' → '1.234.567'.
  // Off by default — the backend already accepts both '87,30' and '87.30'.

  // htmx custom event hooks (debug logging behind a flag).
  if (window.localStorage.getItem('yas_debug') === '1') {
    document.body.addEventListener('htmx:afterRequest', function (evt) {
      console.log('[htmx]', evt.detail.requestConfig.verb, evt.detail.requestConfig.path, evt.detail.xhr.status);
    });
  }
})();
