// Minimal lightbox for gallery pages. Without JS, thumbnails still link to the full image.
(function () {
  var items = Array.prototype.slice.call(document.querySelectorAll('.g-item'));
  if (!items.length) return;

  var lb = document.createElement('div');
  lb.className = 'lb';
  lb.setAttribute('role', 'dialog');
  lb.setAttribute('aria-modal', 'true');
  lb.setAttribute('aria-label', 'Photo viewer');
  lb.innerHTML =
    '<button class="lb-close" type="button" aria-label="Close"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg></button>' +
    '<button class="lb-prev" type="button" aria-label="Previous photo"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg></button>' +
    '<figure><img alt=""><figcaption><span class="lb-loc"></span><span class="lb-exif"></span><span class="lb-cap"></span><a class="lb-buy" target="_blank" rel="noopener">Buy Print ↗</a><span class="lb-pos"></span></figcaption></figure>' +
    '<button class="lb-next" type="button" aria-label="Next photo"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M9 5l7 7-7 7"/></svg></button>';
  document.body.appendChild(lb);

  var img = lb.querySelector('img'), cap = lb.querySelector('.lb-cap'),
      locEl = lb.querySelector('.lb-loc'), exifEl = lb.querySelector('.lb-exif'),
      buy = lb.querySelector('.lb-buy'), pos = lb.querySelector('.lb-pos'),
      closeBtn = lb.querySelector('.lb-close');
  var i = 0, lastFocus = null;

  function show(n) {
    i = (n + items.length) % items.length;
    var a = items[i], t = a.querySelector('img');
    img.src = a.href;
    img.alt = t ? t.alt : '';
    cap.textContent = a.dataset.caption || '';
    locEl.textContent = a.dataset.location || '';
    exifEl.textContent = a.dataset.exif || '';
    if (a.dataset.buy) { buy.href = a.dataset.buy; buy.style.display = ''; } else { buy.style.display = 'none'; }
    pos.textContent = (i + 1) + ' / ' + items.length;
    var next = items[(i + 1) % items.length];
    (new Image()).src = next.href; // preload
  }
  function open(n) { lastFocus = document.activeElement; show(n); lb.classList.add('open'); document.body.style.overflow = 'hidden'; closeBtn.focus(); }
  function close() { lb.classList.remove('open'); document.body.style.overflow = ''; img.removeAttribute('src'); if (lastFocus) lastFocus.focus(); }

  items.forEach(function (a, n) {
    a.addEventListener('click', function (e) {
      if (e.metaKey || e.ctrlKey || e.shiftKey) return;
      e.preventDefault(); open(n);
    });
  });
  closeBtn.addEventListener('click', close);
  lb.querySelector('.lb-prev').addEventListener('click', function () { show(i - 1); });
  lb.querySelector('.lb-next').addEventListener('click', function () { show(i + 1); });
  lb.addEventListener('click', function (e) { if (e.target === lb) close(); });
  document.addEventListener('keydown', function (e) {
    if (!lb.classList.contains('open')) return;
    if (e.key === 'Escape') close();
    else if (e.key === 'ArrowLeft') show(i - 1);
    else if (e.key === 'ArrowRight') show(i + 1);
  });
  var x0 = null;
  lb.addEventListener('touchstart', function (e) { x0 = e.touches[0].clientX; }, { passive: true });
  lb.addEventListener('touchend', function (e) {
    if (x0 === null) return;
    var dx = e.changedTouches[0].clientX - x0;
    if (Math.abs(dx) > 50) show(i + (dx < 0 ? 1 : -1));
    x0 = null;
  });
})();
