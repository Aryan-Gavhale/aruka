/* ==========================================================================
   Aruka public site behaviour. No framework, no build step.

   Two rules hold everywhere in this file:

   1. Nothing here is required. Every animation starts from a state that is
      already readable, and the .no-js class is removed on the first line so the
      CSS fallbacks apply if this file fails to parse.
   2. Motion is asked for, not assumed. `motionOK` is checked once and watched
      for changes, and every effect that moves anything is behind it. Turning the
      system setting on or off takes effect without a reload.
   ========================================================================== */
(() => {
  'use strict';

  document.documentElement.classList.remove('no-js');

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // Two things can turn motion off: the visitor's system setting, and the theme
  // switch in the panel, which renders html.no-anim. Both are honoured here so no
  // effect below has to check twice.
  const animAllowed = !document.documentElement.classList.contains('no-anim');
  const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  let motionOK = animAllowed && !motionQuery.matches;
  const onMotionChange = [];
  motionQuery.addEventListener('change', () => {
    motionOK = animAllowed && !motionQuery.matches;
    onMotionChange.forEach((fn) => fn(motionOK));
  });

  const csrf = () => ($('input[name=csrf_token]') || {}).value || '';
  const rupees = (n) => '\u20b9' + Math.round(Number(n) || 0).toLocaleString('en-IN');

  /* ── header: condense once the page has moved ───────────────────────────── */
  const hdr = $('.hdr');
  if (hdr) {
    const sync = () => hdr.classList.toggle('is-stuck', window.scrollY > 12);
    sync();
    addEventListener('scroll', sync, { passive: true });
  }

  /* ── mobile drawer ──────────────────────────────────────────────────────── */
  const burger = $('.burger');
  const drawer = $('.drawer');
  if (burger && drawer) {
    const setOpen = (open) => {
      drawer.classList.toggle('is-open', open);
      burger.setAttribute('aria-expanded', String(open));
      document.body.style.overflow = open ? 'hidden' : '';
      if (open) $('a', drawer)?.focus();
    };
    burger.addEventListener('click', () => setOpen(!drawer.classList.contains('is-open')));
    $$('a', drawer).forEach((a) => a.addEventListener('click', () => setOpen(false)));
    addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && drawer.classList.contains('is-open')) {
        setOpen(false);
        burger.focus();
      }
    });
  }

  /* ── reveals ────────────────────────────────────────────────────────────────
     One observer for the whole page. Elements that are already on screen when
     the page loads are revealed without a stagger, so the first paint is not a
     wave of things arriving - only what scrolls in afterwards animates.
     ───────────────────────────────────────────────────────────────────────── */
  const reveals = $$('.r');

  const revealAll = () => reveals.forEach((el) => el.classList.add('r-on'));

  if (!reveals.length) {
    // nothing to do
  } else if (!motionOK || !('IntersectionObserver' in window)) {
    revealAll();
  } else {
    // Measure SVG path lengths first, so the draw-in has a real dash length
    // rather than the 1000px guess in the stylesheet.
    $$('.draw').forEach((svg) => {
      $$('path, line, circle, rect', svg).forEach((shape) => {
        if (typeof shape.getTotalLength !== 'function') return;
        try {
          const len = Math.ceil(shape.getTotalLength());
          if (len) shape.style.setProperty('--len', len);
        } catch { /* a shape with no geometry yet; the default is fine */ }
      });
    });

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('r-on');
        observer.unobserve(entry.target);
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });

    reveals.forEach((el) => {
      // Stagger siblings that share a parent, which is what makes a grid of
      // cards land one after another rather than all at once.
      if (!el.style.getPropertyValue('--d') && el.parentElement) {
        const kin = Array.from(el.parentElement.children).filter((c) => c.classList.contains('r'));
        const at = kin.indexOf(el);
        if (kin.length > 1 && at > 0) el.style.setProperty('--d', Math.min(at * 70, 420) + 'ms');
      }
      observer.observe(el);
    });

    onMotionChange.push((ok) => { if (!ok) revealAll(); });
  }

  /* ── headline words, split for the rise-in ──────────────────────────────── */
  $$('[data-split]').forEach((el) => {
    if (el.dataset.split === 'done') return;
    const words = el.textContent.trim().split(/\s+/);
    el.textContent = '';
    words.forEach((word, index) => {
      const wrap = document.createElement('span');
      wrap.className = 'w';
      const inner = document.createElement('i');
      inner.textContent = word;
      inner.style.setProperty('--d', index * 55 + 'ms');
      wrap.appendChild(inner);
      el.appendChild(wrap);
      if (index < words.length - 1) el.appendChild(document.createTextNode(' '));
    });
    el.dataset.split = 'done';
  });

  /* ── rotating headline word ─────────────────────────────────────────────── */
  const rot = $('.rot');
  if (rot) {
    const items = $$('.rot__i', rot);
    if (items.length > 1) {
      // The tallest and widest item sets the box, so the line above never reflows.
      let at = 0;
      items[0].classList.add('is-on');
      const tick = () => {
        if (!motionOK) return;
        const current = items[at];
        at = (at + 1) % items.length;
        const next = items[at];
        current.classList.remove('is-on');
        current.classList.add('is-out');
        next.classList.remove('is-out');
        next.classList.add('is-on');
        window.setTimeout(() => current.classList.remove('is-out'), 600);
      };
      let timer = window.setInterval(tick, 2600);
      onMotionChange.push((ok) => {
        if (!ok) {
          window.clearInterval(timer);
          items.forEach((i, index) => i.classList.toggle('is-on', index === 0));
        } else {
          timer = window.setInterval(tick, 2600);
        }
      });
    }
  }

  /* ── counters ───────────────────────────────────────────────────────────── */
  const counters = $$('[data-count]');
  if (counters.length && 'IntersectionObserver' in window) {
    const format = (value, decimals) =>
      Number(value).toLocaleString('en-IN', {
        minimumFractionDigits: decimals, maximumFractionDigits: decimals,
      });

    const run = (el) => {
      const raw = String(el.dataset.count || '');
      const target = Number(raw) || 0;
      // A stat stored as 40.0 is the number forty, not forty to one decimal place.
      // The column is a REAL, so every whole number arrives with a .0 on it and the
      // headline figures were rendering as "40.0+" and "92.0%".
      const decimals = (raw.split('.')[1] || '').replace(/0+$/, '').length;
      if (!motionOK) { el.textContent = format(target, decimals); return; }

      const started = performance.now();
      const duration = 1500;
      const step = (now) => {
        const t = Math.min((now - started) / duration, 1);
        // ease-out cubic: fast to begin with, so the number reads early
        const eased = 1 - Math.pow(1 - t, 3);
        el.textContent = format(target * eased, decimals);
        if (t < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    };

    const countObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        run(entry.target);
        countObserver.unobserve(entry.target);
      });
    }, { threshold: 0.5 });
    counters.forEach((el) => countObserver.observe(el));
  } else {
    counters.forEach((el) => { el.textContent = el.dataset.count; });
  }

  /* ── parallax and the reading progress bar ──────────────────────────────── */
  const layers = $$('[data-para]');
  const bar = $('.bar');
  if (layers.length || bar) {
    let queued = false;
    const paint = () => {
      queued = false;
      const y = window.scrollY;
      if (bar) {
        const height = document.documentElement.scrollHeight - innerHeight;
        bar.style.width = (height > 0 ? Math.min(y / height, 1) * 100 : 0) + '%';
      }
      if (!motionOK) return;
      layers.forEach((el) => {
        const rate = Number(el.dataset.para) || 0.15;
        const box = el.getBoundingClientRect();
        // Only move what is on screen, measured from the element's own centre so
        // the offset is zero when it is centred rather than at the top.
        if (box.bottom < -200 || box.top > innerHeight + 200) return;
        const centre = box.top + box.height / 2 - innerHeight / 2;
        el.style.transform = `translate3d(0, ${(-centre * rate).toFixed(1)}px, 0)`;
      });
    };
    const onScroll = () => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(paint);
    };
    paint();
    addEventListener('scroll', onScroll, { passive: true });
    addEventListener('resize', onScroll);
    onMotionChange.push((ok) => {
      if (!ok) layers.forEach((el) => { el.style.transform = ''; });
    });
  }

  /* ── the process sequence tracks the scroll ───────────────────────────────
     Whichever step is nearest the middle of the viewport is the live one, and the
     rule beside it fills. It reads as walking through the process rather than as
     four paragraphs that happen to be numbered.

     The portal renders .steps too, for launch milestones, and is deliberately
     still - a client checking what is left to do is not being told a story.
     ───────────────────────────────────────────────────────────────────────── */
  const stepGroups = document.documentElement.classList.contains('portal') ? [] : $$('.steps');
  if (stepGroups.length) {
    let queued = false;
    const mark = () => {
      queued = false;
      if (!motionOK) return;
      const middle = innerHeight * 0.46;
      stepGroups.forEach((group) => {
        const items = $$('.steps__i', group);
        let live = null;
        let closest = Infinity;
        items.forEach((item) => {
          const box = item.getBoundingClientRect();
          const gap = Math.abs(box.top + box.height / 2 - middle);
          if (gap < closest) { closest = gap; live = item; }
        });
        // Only claim a step while the group is actually in front of the reader,
        // otherwise the last one stays lit for the rest of the page.
        const near = closest < innerHeight * 0.6;
        items.forEach((item) => item.classList.toggle('is-on', near && item === live));
      });
    };
    const onScroll = () => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(mark);
    };
    mark();
    addEventListener('scroll', onScroll, { passive: true });
    addEventListener('resize', onScroll);
    onMotionChange.push((ok) => {
      if (ok) mark();
      // Still means every rule drawn, not every rule blank: the sequence is
      // information, so it resolves rather than disappearing.
      else $$('.steps__i').forEach((item) => item.classList.remove('is-on'));
    });
  }

  /* ── card tilt and the cursor-following glow ────────────────────────────── */
  // The glow is a CSS gradient positioned from --mx/--my, so it costs nothing
  // when the pointer is elsewhere.
  $$('.card, [data-tilt]').forEach((card) => {
    card.addEventListener('pointermove', (event) => {
      const box = card.getBoundingClientRect();
      const x = event.clientX - box.left;
      const y = event.clientY - box.top;
      card.style.setProperty('--mx', ((x / box.width) * 100).toFixed(1) + '%');
      card.style.setProperty('--my', ((y / box.height) * 100).toFixed(1) + '%');

      if (!motionOK || !card.hasAttribute('data-tilt')) return;
      const tilt = Number(card.dataset.tilt) || 6;
      const rx = ((y / box.height) - 0.5) * -2 * tilt;
      const ry = ((x / box.width) - 0.5) * 2 * tilt;
      card.style.transform = `perspective(900px) rotateX(${rx.toFixed(2)}deg) rotateY(${ry.toFixed(2)}deg)`;
    });
    card.addEventListener('pointerleave', () => {
      if (card.hasAttribute('data-tilt')) card.style.transform = '';
    });
  });

  /* ── magnetic buttons ───────────────────────────────────────────────────── */
  $$('[data-magnet]').forEach((btn) => {
    const pull = Number(btn.dataset.magnet) || 5;
    btn.addEventListener('pointermove', (event) => {
      if (!motionOK) return;
      const box = btn.getBoundingClientRect();
      const dx = (event.clientX - (box.left + box.width / 2)) / (box.width / 2);
      const dy = (event.clientY - (box.top + box.height / 2)) / (box.height / 2);
      btn.style.transform = `translate(${(dx * pull).toFixed(1)}px, ${(dy * pull - 2).toFixed(1)}px)`;
    });
    btn.addEventListener('pointerleave', () => { btn.style.transform = ''; });
  });

  /* ── marquee: duplicate the track so the loop has no seam ───────────────── */
  $$('.marq__t').forEach((track) => {
    const group = $('.marq__g', track);
    if (group && track.children.length === 1) {
      const copy = group.cloneNode(true);
      copy.setAttribute('aria-hidden', 'true');
      track.appendChild(copy);
    }
  });

  /* ── FAQ accordion ──────────────────────────────────────────────────────────
     Height is animated from a measured pixel value rather than max-height, so a
     long answer opens at the same speed as a short one.
     ───────────────────────────────────────────────────────────────────────── */
  $$('.faq__i').forEach((item) => {
    const button = $('.faq__q', item);
    const panel = $('.faq__a', item);
    if (!button || !panel) return;

    const close = () => {
      item.classList.remove('is-open');
      button.setAttribute('aria-expanded', 'false');
      panel.style.height = '0px';
    };
    const open = () => {
      item.classList.add('is-open');
      button.setAttribute('aria-expanded', 'true');
      panel.style.height = panel.firstElementChild.offsetHeight + 'px';
    };

    button.setAttribute('aria-expanded', 'false');
    button.addEventListener('click', () => {
      const isOpen = item.classList.contains('is-open');
      // One at a time within a group, which is what makes a long FAQ scannable.
      const group = item.parentElement;
      if (group) $$('.faq__i.is-open', group).forEach((other) => {
        if (other !== item) {
          other.classList.remove('is-open');
          $('.faq__q', other)?.setAttribute('aria-expanded', 'false');
          const otherPanel = $('.faq__a', other);
          if (otherPanel) otherPanel.style.height = '0px';
        }
      });
      isOpen ? close() : open();
    });

    // Keep an open panel the right height if the text rewraps.
    addEventListener('resize', () => {
      if (item.classList.contains('is-open')) {
        panel.style.height = panel.firstElementChild.offsetHeight + 'px';
      }
    });
  });

  /* ── flashes dismiss themselves ─────────────────────────────────────────── */
  $$('.flash').forEach((flash, index) => {
    $('button', flash)?.addEventListener('click', () => flash.remove());
    window.setTimeout(() => {
      flash.style.transition = 'opacity .4s, transform .4s';
      flash.style.opacity = '0';
      flash.style.transform = 'translateX(24px)';
      window.setTimeout(() => flash.remove(), 420);
    }, 6500 + index * 800);
  });

  /* ── forms: stamp the open time, and stop a double submit ───────────────── */
  $$('form[data-timed]').forEach((form) => {
    const stamp = $('input[name=opened_at]', form);
    // Written by JavaScript rather than rendered, so a cached page cannot carry
    // a stale timestamp that makes a real person look like a bot.
    if (stamp && !stamp.value) stamp.value = (Date.now() / 1000).toFixed(3);
  });

  $$('form[data-once]').forEach((form) => {
    form.addEventListener('submit', () => {
      const button = $('button[type=submit], .btn[type=submit]', form);
      if (!button) return;
      window.setTimeout(() => {
        button.disabled = true;
        button.dataset.was = button.textContent;
        button.textContent = button.dataset.busy || 'Sending\u2026';
      }, 0);
    });
  });

  /* ── the pricing calculator ─────────────────────────────────────────────────
     The form posts and works without any of this. What the script adds is the
     total moving as boxes are ticked, which is the whole point of a calculator.
     ───────────────────────────────────────────────────────────────────────── */
  const calc = $('#calc');
  if (calc) {
    const out = {
      total: $('[data-out=total]'),
      subtotal: $('[data-out=subtotal]'),
      surcharge: $('[data-out=surcharge]'),
      discount: $('[data-out=discount]'),
      tax: $('[data-out=tax]'),
      recurring: $('[data-out=recurring]'),
      days: $('[data-out=days]'),
      lines: $('[data-out=lines]'),
      milestones: $('[data-out=milestones]'),
    };
    const taxRow = $('[data-row=tax]');
    const surchargeRow = $('[data-row=surcharge]');
    const discountRow = $('[data-row=discount]');
    const recurringRow = $('[data-row=recurring]');

    let inFlight = null;
    let pending = false;

    const setRow = (row, on) => { if (row) row.hidden = !on; };

    const paint = (data) => {
      if (out.total) out.total.textContent = rupees(data.total);
      if (out.subtotal) out.subtotal.textContent = rupees(data.subtotal);
      if (out.surcharge) out.surcharge.textContent = '+ ' + rupees(data.surcharge);
      if (out.discount) out.discount.textContent = '\u2212 ' + rupees(data.discount);
      if (out.tax) out.tax.textContent = rupees(data.tax);
      if (out.recurring) out.recurring.textContent = rupees(data.recurring_yearly) + ' a year';
      if (out.days) {
        out.days.textContent = data.delivery_days
          ? 'About ' + data.delivery_days + ' working days'
          : '';
      }
      setRow(surchargeRow, data.surcharge > 0);
      setRow(discountRow, data.discount > 0);
      setRow(taxRow, data.tax > 0);
      setRow(recurringRow, data.recurring_yearly > 0);

      if (out.lines) {
        out.lines.innerHTML = '';
        (data.lines || []).forEach((line) => {
          const li = document.createElement('li');
          const label = document.createElement('span');
          label.textContent = line.qty > 1 ? `${line.label} \u00d7 ${line.qty}` : line.label;
          const amount = document.createElement('span');
          amount.textContent = rupees(line.amount) + (line.is_recurring ? '/yr' : '');
          li.append(label, amount);
          out.lines.appendChild(li);
        });
      }

      if (out.milestones) {
        out.milestones.innerHTML = '';
        (data.milestones || []).forEach((step) => {
          const row = document.createElement('div');
          row.className = 'ms__i';
          const label = document.createElement('span');
          label.textContent = `${step.label} \u00b7 ${step.pct}%`;
          const amount = document.createElement('b');
          amount.textContent = rupees(step.amount);
          row.append(label, amount);
          out.milestones.appendChild(row);
        });
      }
    };

    const reprice = () => {
      if (inFlight) { pending = true; return; }
      const body = new FormData(calc);
      body.set('csrf_token', csrf());
      inFlight = fetch(calc.dataset.estimateUrl, {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrf() },
        body,
      })
        .then((r) => r.json())
        .then((data) => { if (data.ok) paint(data); })
        .catch(() => { /* the total simply stops updating; submitting still works */ })
        .finally(() => {
          inFlight = null;
          if (pending) { pending = false; reprice(); }
        });
    };

    let debounce = null;
    calc.addEventListener('change', () => {
      window.clearTimeout(debounce);
      debounce = window.setTimeout(reprice, 120);
    });
    calc.addEventListener('input', (event) => {
      if (event.target.type !== 'number' && event.target.type !== 'range') return;
      window.clearTimeout(debounce);
      debounce = window.setTimeout(reprice, 320);
    });

    // Show the extra-pages field only when the box that needs it is ticked.
    $$('[data-shows]').forEach((control) => {
      const target = $('#' + control.dataset.shows);
      if (!target) return;
      const sync = () => { target.hidden = !control.checked; };
      control.addEventListener('change', sync);
      sync();
    });

    reprice();
  }

  /* ── confirm a one-way action ───────────────────────────────────────────────
     Only used where a mis-click cannot be undone from the page it happens on -
     declining a proposal, in practice. A plain confirm() rather than a modal,
     because the browser's own dialog is the one nobody can style into invisibility.
     ───────────────────────────────────────────────────────────────────────── */
  $$('[data-confirm]').forEach((el) => {
    el.addEventListener('click', (event) => {
      if (!window.confirm(el.dataset.confirm)) {
        event.preventDefault();
        event.stopPropagation();
      }
    });
  });

  /* ── copy a reference ───────────────────────────────────────────────────── */
  $$('[data-copy]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(btn.dataset.copy);
        const was = btn.textContent;
        btn.textContent = 'Copied';
        window.setTimeout(() => { btn.textContent = was; }, 1600);
      } catch { /* the reference is on screen anyway */ }
    });
  });

  /* ── in-page anchors get their own scroll, so the header does not cover them */
  $$('a[href^="#"]:not([href="#"])').forEach((link) => {
    link.addEventListener('click', (event) => {
      const target = document.getElementById(link.getAttribute('href').slice(1));
      if (!target) return;
      event.preventDefault();
      const top = target.getBoundingClientRect().top + window.scrollY - 90;
      window.scrollTo({ top, behavior: motionOK ? 'smooth' : 'auto' });
      target.setAttribute('tabindex', '-1');
      target.focus({ preventScroll: true });
    });
  });
})();
