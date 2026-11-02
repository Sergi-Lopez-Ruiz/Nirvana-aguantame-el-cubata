/* Nirvana + Plausible. No cookies, no personal identifiers, no extra pageviews. */
(() => {
  'use strict';
  const widget = document.querySelector('.nirvana-widget');
  if (!widget) return;

  // Mark one funnel milestone per page load, even after pressing reset.
  const seen = new Set();
  const language = widget.dataset.lang || document.documentElement.lang || 'unknown';
  const fire = (event, once = true) => {
    if (once && seen.has(event)) return;
    if (once) seen.add(event);
    if (typeof window.plausible === 'function') {
      window.plausible(event, {props: {language}});
    }
  };

  // Exact public widget class names: .n-node, .n-pink, .n-gold, .n-reset.
  // Capture completed interactions without modifying the widget's implementation.
  widget.addEventListener('pointerup', (event) => {
    if (event.target.closest?.('.n-node')) fire('Brain Started');
  });
  widget.addEventListener('keydown', (event) => {
    if ((event.key === 'Enter' || event.key === ' ') && event.target.closest?.('.n-node')) {
      fire('Brain Started');
    }
  });
  widget.addEventListener('click', (event) => {
    if (event.target.closest?.('.n-reset, #n-reset')) fire('Brain Reset', false);
  });

  // The original widget applies these classes at interactions 90 and 120.
  const readPhase = () => {
    if (widget.classList.contains('n-pink')) fire('Brain Pink');
    if (widget.classList.contains('n-gold')) {
      // A jump or restoration straight to gold also implies pink was reached.
      fire('Brain Pink');
      fire('Brain Gold');
    }
  };
  new MutationObserver(readPhase).observe(widget, {attributes: true, attributeFilter: ['class']});
  readPhase();
})();
