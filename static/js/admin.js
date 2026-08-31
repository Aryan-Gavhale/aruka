/* ==========================================================================
   Aruka admin behaviour. No framework, no build step.

   Everything here is an enhancement over markup that already works: the kanban
   card has a stage dropdown on its detail page, the calculator posts the same
   form it previews, the media picker's hidden input accepts a plain id. If this
   file fails to load, the panel is slower to use and nothing is unreachable.
   ========================================================================== */
(() => {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const csrf = () => ($('input[name=csrf_token]') || {}).value || '';
  const rupees = (n) => '\u20b9' + Math.round(Number(n) || 0).toLocaleString('en-IN');
  const digitsOf = (value) => String(value || '').replace(/\D/g, '');

  const jsonHeaders = () => ({ 'Content-Type': 'application/json', 'X-CSRF-Token': csrf() });

  function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value == null ? '' : String(value);
    return div.innerHTML;
  }

  /* ── sidebar on small screens ───────────────────────────────────────────── */
  const side = $('#side'), scrim = $('#scrim'), burger = $('#burger2');
  const sideSync = () => {
    const open = !!side?.classList.contains('is-open');
    if (scrim) scrim.hidden = !open;
    burger?.setAttribute('aria-expanded', String(open));
    burger?.setAttribute('aria-label', open ? 'Close the menu' : 'Menu');
  };
  const closeSide = () => { side?.classList.remove('is-open'); sideSync(); };
  burger?.addEventListener('click', () => { side?.classList.toggle('is-open'); sideSync(); });
  scrim?.addEventListener('click', closeSide);
  sideSync();

  // The sticky sidebar and calculator rail offset themselves from the real
  // header height, which changes when the action buttons wrap onto two rows.
  const topbar = $('.top');
  const measureTop = () => {
    if (topbar) document.documentElement.style.setProperty('--top-h', topbar.offsetHeight + 'px');
  };
  measureTop();
  if (topbar && window.ResizeObserver) new ResizeObserver(measureTop).observe(topbar);
  window.addEventListener('resize', measureTop);

  /* ── flashes ────────────────────────────────────────────────────────────── */
  function dismiss(el) {
    el.style.opacity = '0';
    el.style.transform = 'translateX(14px)';
    setTimeout(() => el.remove(), 240);
  }

  $$('.flash').forEach((el) => {
    el.style.transition = 'opacity .22s, transform .22s';
    $('.flash__x', el)?.addEventListener('click', () => dismiss(el));
    setTimeout(() => dismiss(el), 6000);
  });

  function toast(message, isError) {
    let host = $('#flashes');
    if (!host) {
      host = document.createElement('div');
      host.id = 'flashes';
      host.className = 'flashes';
      document.body.appendChild(host);
    }
    const el = document.createElement('div');
    el.className = 'flash' + (isError ? ' flash--error' : '');
    el.innerHTML = '<span></span><button class="flash__x" type="button" aria-label="Dismiss">&times;</button>';
    el.firstChild.textContent = message;
    el.style.transition = 'opacity .22s, transform .22s';
    host.appendChild(el);
    $('.flash__x', el).addEventListener('click', () => dismiss(el));
    setTimeout(() => dismiss(el), 5000);
  }
  window.arukaToast = toast;

  /* ── confirm before destructive posts ───────────────────────────────────── */
  document.addEventListener('submit', (event) => {
    const question = event.target.dataset?.confirm;
    if (question && !window.confirm(question)) event.preventDefault();
  });
  // A button carries its own question when the form it submits has an innocent
  // action too - "save this line" and "remove this line" share one form.
  $$('a[data-confirm], button[data-confirm]').forEach((el) => {
    el.addEventListener('click', (event) => {
      if (!window.confirm(el.dataset.confirm)) {
        event.preventDefault();
        event.stopPropagation();
      }
    });
  });

  /* ── a filter that submits itself the moment it changes ─────────────────── */
  $$('[data-autofilter]').forEach((el) => {
    el.addEventListener('change', () => el.form?.submit());
  });

  /* ── unsaved-changes guard ──────────────────────────────────────────────── */
  $$('form[data-guard]').forEach((form) => {
    let dirty = false;
    form.addEventListener('input', () => { dirty = true; });
    form.addEventListener('submit', () => { dirty = false; });
    window.addEventListener('beforeunload', (event) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = '';
    });
  });

  /* ── print buttons, so no inline handler is needed under the CSP ────────── */
  $$('[data-print]').forEach((el) => el.addEventListener('click', () => window.print()));

  /* ── colour input paired with its hex field ─────────────────────────────── */
  $$('input[data-colour-for]').forEach((swatch) => {
    const text = document.getElementById(swatch.dataset.colourFor);
    if (!text) return;
    swatch.addEventListener('input', () => { text.value = swatch.value.toUpperCase(); });
    text.addEventListener('input', () => {
      if (/^#[0-9a-f]{6}$/i.test(text.value)) swatch.value = text.value;
    });
  });

  /* ── slug filled from the title until touched by hand ───────────────────── */
  const slugify = (value) => String(value).toLowerCase().trim()
    .replace(/[^a-z0-9\s-]/g, '').replace(/[\s-]+/g, '-').replace(/^-|-$/g, '');
  $$('input[name=slug]').forEach((slug) => {
    const form = slug.closest('form');
    const source = form && (form.querySelector('input[name=name]') || form.querySelector('input[name=title]'));
    if (!source) return;
    if (slug.value) slug.dataset.touched = '1';
    slug.addEventListener('input', () => { slug.dataset.touched = '1'; });
    source.addEventListener('input', () => {
      if (!slug.dataset.touched) slug.value = slugify(source.value);
    });
  });

  /* ── copy to clipboard ──────────────────────────────────────────────────── */
  $$('[data-copy]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const target = btn.dataset.copy;
      const field = target.startsWith('#') ? $(target) : null;
      const value = field ? field.value : target;
      try {
        await navigator.clipboard.writeText(value || '');
        toast('Copied.');
      } catch {
        if (field) { field.select(); toast('Press Ctrl+C to copy.'); }
        else toast('Could not copy. Select the text and copy it by hand.', true);
      }
    });
  });

  /* ── media picker ───────────────────────────────────────────────────────── */
  const modal = $('#picker'), modalBody = $('#picker-body');
  let pickTarget = null, lastFocus = null;

  function loadPicker(query) {
    const url = '/admin/media/picker' + (query ? '?q=' + encodeURIComponent(query) : '');
    return fetch(url, { headers: { 'X-Requested-With': 'fetch' } })
      .then((r) => r.text())
      .then((html) => {
        modalBody.innerHTML = html;
        const search = $('#picker-search', modalBody);
        if (search) { search.value = query || ''; search.focus(); }
        wirePicker();
      })
      .catch(() => {
        modalBody.innerHTML = '<p class="note note--warn">Could not load the media library. '
          + 'Type the image id into the field instead.</p>';
      });
  }

  function openPicker(host) {
    pickTarget = host;
    lastFocus = document.activeElement;
    modal.hidden = false;
    modalBody.innerHTML = '<p class="hint">Loading the library\u2026</p>';
    loadPicker('');
  }

  function closePicker() {
    if (!modal) return;
    modal.hidden = true;
    pickTarget = null;
    lastFocus?.focus();
  }

  function wirePicker() {
    const search = $('#picker-search', modalBody);
    let timer = null;
    search?.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => loadPicker(search.value), 260);
    });

    $$('.pitem', modalBody).forEach((item) => {
      item.addEventListener('click', () => {
        if (!pickTarget) return;
        const input = $('[data-pick-input]', pickTarget);
        const preview = $('[data-pick-preview]', pickTarget);
        const meta = $('[data-pick-meta]', pickTarget);
        input.value = item.dataset.id;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        preview.innerHTML = '<img src="' + escapeHtml(item.dataset.thumb) + '" alt="">';
        if (meta) meta.textContent = '#' + item.dataset.id + ' \u00b7 ' + (item.dataset.alt || 'no alt text');
        closePicker();
      });
    });
  }

  $$('[data-pick]').forEach((host) => {
    $('[data-pick-open]', host)?.addEventListener('click', () => openPicker(host));
    $('[data-pick-clear]', host)?.addEventListener('click', () => {
      const input = $('[data-pick-input]', host);
      input.value = '';
      input.dispatchEvent(new Event('input', { bubbles: true }));
      $('[data-pick-preview]', host).textContent = 'No image';
      const meta = $('[data-pick-meta]', host);
      if (meta) meta.textContent = 'Nothing selected';
    });
  });
  $$('[data-picker-close]').forEach((b) => b.addEventListener('click', closePicker));
  modal?.addEventListener('click', (event) => { if (event.target === modal) closePicker(); });
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (modal && !modal.hidden) closePicker();
    else closeSide();
  });

  /* ── drag reorder for any table with data-reorder ───────────────────────── */
  $$('[data-reorder]').forEach((table) => {
    const url = table.dataset.reorder;
    const body = $('tbody', table) || table;
    const rows = () => $$('[data-id]', body);
    let dragged = null;

    const persist = () => {
      const order = rows().map((r) => r.dataset.id);
      fetch(url, { method: 'POST', headers: jsonHeaders(), body: JSON.stringify({ order, ids: order }) })
        .then((r) => r.json())
        .then((data) => toast(data.ok ? 'Order saved.' : 'Could not save the order.', !data.ok))
        .catch(() => toast('Could not save the order.', true));
    };

    rows().forEach((row) => {
      const handle = $('.drag', row);
      if (!handle) return;
      handle.setAttribute('draggable', 'true');
      handle.setAttribute('tabindex', '0');

      handle.addEventListener('dragstart', (event) => {
        dragged = row;
        row.classList.add('is-dragging');
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', row.dataset.id);
      });
      handle.addEventListener('dragend', () => {
        row.classList.remove('is-dragging');
        rows().forEach((r) => r.classList.remove('is-over'));
        dragged = null;
        persist();
      });
      row.addEventListener('dragover', (event) => {
        if (!dragged || dragged === row) return;
        event.preventDefault();
        row.classList.add('is-over');
        const box = row.getBoundingClientRect();
        const after = (event.clientY - box.top) > box.height / 2;
        row.parentNode.insertBefore(dragged, after ? row.nextSibling : row);
      });
      row.addEventListener('dragleave', () => row.classList.remove('is-over'));

      // Drag-and-drop alone is not reachable from a keyboard.
      handle.addEventListener('keydown', (event) => {
        const list = rows();
        const at = list.indexOf(row);
        if (event.key === 'ArrowUp' && at > 0) {
          event.preventDefault();
          row.parentNode.insertBefore(row, list[at - 1]);
          handle.focus();
          persist();
        } else if (event.key === 'ArrowDown' && at < list.length - 1) {
          event.preventDefault();
          row.parentNode.insertBefore(list[at + 1], row);
          handle.focus();
          persist();
        }
      });
    });
  });

  /* ── kanban: drag a card into another column ─────────────────────────────── */
  // Two boards use this - the lead pipeline, which posts one url for every card,
  // and the project task board, where each card carries its own move url. The
  // difference is only in how the request is addressed, so it lives in `send`.
  $$('[data-board]').forEach((board) => {
    const boardUrl = board.dataset.moveUrl || '';
    let held = null;

    const retally = () => {
      $$('.col', board).forEach((column) => {
        const count = $('.col__n', column);
        if (count) count.textContent = $$('.card', column).length;
        const empty = $('.col__empty', column);
        if (empty) empty.hidden = $$('.card', column).length > 0;
      });
    };

    const send = (card, stage) => {
      if (boardUrl) {
        return fetch(boardUrl, {
          method: 'POST',
          headers: jsonHeaders(),
          body: JSON.stringify({ lead_id: card.dataset.lead, stage }),
        });
      }
      return fetch(card.dataset.moveUrl, {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify({ status: stage }),
      });
    };

    const move = (card, stage, from) => {
      send(card, stage)
        .then((r) => r.json())
        .then((data) => {
          if (!data.ok) throw new Error(data.error || 'refused');
          toast(data.message || 'Moved.');
          retally();
          if (data.progress === undefined) return;
          const fill = $('[data-progress]');
          if (fill) fill.style.width = data.progress + '%';
        })
        .catch(() => {
          // Put the card back rather than leave the screen disagreeing with the database.
          from.appendChild(card);
          retally();
          toast('Could not move that. Nothing was changed.', true);
        });
    };

    $$('.card[draggable]', board).forEach((card) => {
      card.addEventListener('dragstart', (event) => {
        held = card;
        card.classList.add('is-dragging');
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', card.dataset.lead || card.dataset.task || '');
      });
      card.addEventListener('dragend', () => {
        card.classList.remove('is-dragging');
        held = null;
      });
    });

    $$('.col', board).forEach((column) => {
      const drop = $('[data-drop]', column) || column;
      drop.addEventListener('dragover', (event) => {
        if (!held) return;
        event.preventDefault();
        column.classList.add('is-over');
      });
      drop.addEventListener('dragleave', () => column.classList.remove('is-over'));
      drop.addEventListener('drop', (event) => {
        event.preventDefault();
        column.classList.remove('is-over');
        if (!held) return;
        const from = held.parentNode;
        if (from === drop) return;
        drop.appendChild(held);
        move(held, column.dataset.stage, from);
      });
    });
    retally();
  });

  /* ── reveal a vault secret, once, without it living in the page source ───── */
  $$('[data-reveal]').forEach((button) => {
    button.addEventListener('click', () => {
      const target = $(`[data-secret-for="${button.dataset.reveal}"]`);
      if (!target) return;
      if (!target.hidden) {                       // a second press puts it away again
        target.hidden = true;
        target.textContent = '';
        return;
      }
      button.disabled = true;
      fetch(button.dataset.url, { method: 'POST', headers: { 'X-CSRF-Token': csrf() } })
        .then((r) => r.json())
        .then((data) => {
          if (!data.ok) throw new Error(data.error);
          target.hidden = false;
          target.textContent = data.note || data.secret;
          if (data.secret) {
            navigator.clipboard?.writeText(data.secret)
              .then(() => toast('Copied. This was written to the activity log.'))
              .catch(() => toast('Shown. This was written to the activity log.'));
          }
          // Hide it again rather than leave a password on screen behind you.
          window.setTimeout(() => { target.hidden = true; target.textContent = ''; }, 30000);
        })
        .catch((err) => toast(err.message || 'Could not decrypt that.', true))
        .finally(() => { button.disabled = false; });
    });
  });

  /* ── inline on/off toggles in list tables ───────────────────────────────── */
  $$('[data-toggle-url]').forEach((box) => {
    box.addEventListener('change', () => {
      fetch(box.dataset.toggleUrl, { method: 'POST', headers: { 'X-CSRF-Token': csrf() } })
        .then((r) => r.json())
        .then((data) => {
          if (!data.ok) throw new Error();
          box.closest('tr, .card')?.classList.toggle('is-draft', !data.on);
          toast(data.on ? 'Turned on.' : 'Turned off.');
        })
        .catch(() => { box.checked = !box.checked; toast('Could not change that.', true); });
    });
  });

  /* ── launch checklist ticks ─────────────────────────────────────────────── */
  $$('[data-check-url]').forEach((box) => {
    box.addEventListener('change', () => {
      fetch(box.dataset.checkUrl, { method: 'POST', headers: { 'X-CSRF-Token': csrf() } })
        .then((r) => r.json())
        .then((data) => {
          if (!data.ok) throw new Error();
          box.closest('.check')?.classList.toggle('is-done', data.on);
          if (data.progress === undefined) return;
          const fill = $('[data-progress]');
          if (fill) fill.style.width = data.progress + '%';
          const text = $('[data-progress-text]');
          if (text) text.textContent = data.progress + '% complete';
        })
        .catch(() => { box.checked = !box.checked; toast('Could not save that.', true); });
    });
  });

  /* ── media library upload ───────────────────────────────────────────────── */
  const drop = $('#drop');
  if (drop) {
    const input = $('#drop-input');
    const status = $('#drop-status');
    const stop = (event) => { event.preventDefault(); event.stopPropagation(); };

    ['dragenter', 'dragover'].forEach((name) =>
      drop.addEventListener(name, (e) => { stop(e); drop.classList.add('is-over'); }));
    ['dragleave', 'drop'].forEach((name) =>
      drop.addEventListener(name, (e) => { stop(e); drop.classList.remove('is-over'); }));
    drop.addEventListener('drop', (event) => {
      if (event.dataTransfer.files.length) send(event.dataTransfer.files);
    });
    input?.addEventListener('change', () => { if (input.files.length) send(input.files); });

    function send(files) {
      const total = files.length;
      let done = 0, failed = 0;
      const tick = () => {
        if (status) status.textContent = `Uploading ${done + failed} of ${total}\u2026`;
        if (done + failed < total) return;
        if (failed) toast(`${failed} file${failed === 1 ? '' : 's'} could not be uploaded.`, true);
        window.location.reload();
      };
      Array.from(files).forEach((file) => {
        const body = new FormData();
        body.append('files', file);
        body.append('csrf_token', csrf());
        fetch('/admin/media/upload', { method: 'POST', body, headers: { 'X-Requested-With': 'fetch' } })
          .then((r) => r.json())
          .then((data) => { data.ok ? done++ : failed++; tick(); })
          .catch(() => { failed++; tick(); });
      });
      tick();
    }
  }

  /* ── live price calculator ──────────────────────────────────────────────── */
  const calc = $('[data-calc]');
  if (calc) {
    const url = calc.dataset.previewUrl;
    const out = $('[data-calc-out]');
    let timer = null, inflight = null;

    const set = (name, value) => {
      const el = $('[data-calc-' + name + ']', out);
      if (el) el.textContent = value;
    };
    const show = (name, on) => {
      $$('[data-calc-' + name + '-row]', out).forEach((el) => { el.hidden = !on; });
      const value = $('[data-calc-' + name + ']', out);
      if (value) value.hidden = !on;
    };

    const config = () => {
      const form = new FormData(calc);
      const payload = { addons: [] };
      form.forEach((value, key) => {
        if (key === 'csrf_token') return;
        payload[key] = value;
      });
      return payload;
    };

    const paint = (data) => {
      if (!out) return;

      const lines = $('[data-calc-lines]', out);
      if (lines) {
        lines.innerHTML = (data.lines || []).map((line) => {
          const qty = line.qty > 1 ? ' \u00d7 ' + line.qty : '';
          const value = line.recurring
            ? rupees(line.unit_price * line.qty) + '/yr'
            : rupees(line.amount);
          return '<li><span>' + escapeHtml(line.label) + qty
            + (line.recurring ? '<small>from year two</small>' : '')
            + '</span><b>' + value + '</b></li>';
        }).join('') || '<li><span class="muted">Nothing selected yet.</span></li>';
      }

      set('subtotal', rupees(data.subtotal));
      set('surcharge', '+' + rupees(data.surcharge));
      set('discount', '\u2212' + rupees(data.discount));
      set('tax', rupees(data.tax));
      set('tax-rate', data.tax_rate ? '@ ' + data.tax_rate + '%' : '');
      set('total', rupees(data.total));
      set('days', data.delivery_days);
      set('recurring', rupees(data.recurring_yearly));

      show('surcharge', data.surcharge > 0);
      show('discount', data.discount > 0);
      show('tax', data.tax > 0);
      show('recurring', data.recurring_yearly > 0);

      const marginBox = $('[data-calc-margin-box]', out);
      if (marginBox) {
        const known = data.margin !== undefined;
        marginBox.hidden = !known;
        if (known) {
          set('cost', rupees(data.internal_cost));
          set('margin', rupees(data.margin));
          set('margin-pct', data.margin_pct + '%');
        }
      }

      const schedule = $('[data-calc-milestones]', out);
      if (schedule) {
        schedule.innerHTML = (data.milestones || []).map((m) =>
          '<li><span>' + escapeHtml(m.label) + ' \u00b7 ' + m.pct + '%</span><b>'
          + rupees(m.amount) + '</b></li>').join('');
      }
    };

    const recalc = () => {
      if (!url) return;
      inflight?.abort();
      const controller = new AbortController();
      inflight = controller;
      fetch(url, {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify(config()),
        signal: controller.signal,
      })
        .then((r) => r.json())
        .then((data) => { if (data.ok) paint(data); })
        .catch((err) => {
          if (err.name !== 'AbortError') toast('Could not price that. Saving still works.', true);
        });
    };

    // A quantity field only matters once its own row is switched on, and a
    // disabled input is clearer about that than a number nobody is charging for.
    const syncPicks = () => {
      $$('.addon', calc).forEach((addon) => {
        const box = $('input[type=checkbox]', addon);
        const qty = $('input[type=number]', addon);
        addon.classList.toggle('is-on', box ? box.checked : (qty && Number(qty.value) > 0));
      });
    };

    calc.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(recalc, 280); });
    calc.addEventListener('change', () => {
      syncPicks();
      clearTimeout(timer);
      timer = setTimeout(recalc, 60);
    });
    syncPicks();
    recalc();
  }

  /* ── WhatsApp composer: template preview and the live wa.me link ────────── */
  const composer = $('[data-wa-form]');
  if (composer) {
    const url = composer.dataset.previewUrl;
    let values = {};
    try { values = JSON.parse(composer.dataset.values || '{}'); } catch { values = {}; }

    const select = $('[data-wa-template]', composer);
    const body = $('[data-wa-body]', composer);
    const count = $('[data-wa-count]', composer);
    const missing = $('[data-wa-missing]', composer);
    const number = $('[name=to_number]', composer);

    const syncCount = () => { if (count) count.textContent = (body?.value || '').length; };

    const preview = () => {
      const id = select?.value;
      if (!id || !url) return;
      fetch(url, {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify({ template_id: id, values }),
      })
        .then((r) => r.json())
        .then((data) => {
          if (!data.ok) return;
          body.value = data.body;
          delete body.dataset.touched;
          syncCount();
          if (missing) {
            missing.textContent = data.missing?.length
              ? 'Nothing on file for: ' + data.missing.join(', ') + '. Fill those in by hand.'
              : '';
          }
        })
        .catch(() => toast('Could not load that template. Type the message instead.', true));
    };

    select?.addEventListener('change', preview);
    body?.addEventListener('input', () => { body.dataset.touched = '1'; syncCount(); });
    number?.addEventListener('input', syncCount);
    syncCount();
  }

  // Click-to-chat hand-off: the same link, but we know the tab has been opened.
  $$('[data-wa-open]').forEach((link) => {
    link.addEventListener('click', () => {
      const form = $('#handoff-outcome');
      if (form) form.hidden = false;
    });
  });

  /* ── bulk WhatsApp: only show the stage picker for the audience using it ── */
  const audience = $('[data-bulk-audience]');
  if (audience) {
    const stage = $('[data-bulk-stage]');
    const sync = () => { if (stage) stage.hidden = audience.value !== 'lead_stage'; };
    audience.addEventListener('change', sync);
    sync();
  }

  /* ── new ticket: fill the contact from the client, show the promise ──────── */
  const clientPick = $('[data-fill-contact]');
  if (clientPick) {
    const form = clientPick.closest('form');
    const project = $('[name=project_id]', form);

    clientPick.addEventListener('change', () => {
      const option = clientPick.selectedOptions[0];
      if (!option) return;
      [['contact_name', 'name'], ['contact_email', 'email'], ['contact_phone', 'phone']]
        .forEach(([field, key]) => {
          const input = $('[name=' + field + ']', form);
          if (input && !input.value) input.value = option.dataset[key] || '';
        });

      // Offering a project belonging to someone else is a data-entry accident
      // waiting to happen, so the list narrows to the chosen client.
      if (!project) return;
      const chosen = clientPick.value;
      $$('option', project).forEach((opt) => {
        opt.hidden = !!opt.dataset.client && !!chosen && opt.dataset.client !== chosen;
      });
      if ($('option:checked', project)?.hidden) project.value = '';
    });
  }

  const priority = $('[data-sla-pick]');
  if (priority) {
    const note = $('[data-sla-note]');
    const sync = () => {
      if (note) note.textContent = priority.selectedOptions[0]?.dataset.sla || '';
    };
    priority.addEventListener('change', sync);
    sync();
  }

  /* ── quote lines: reveal the per-line editor ────────────────────────────── */
  $$('[data-line-edit]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const row = document.getElementById('line-' + btn.dataset.lineEdit);
      if (!row) return;
      row.hidden = !row.hidden;
      if (!row.hidden) $('input', row)?.focus();
    });
  });

  /* ── payment form: prefill the balance, warn on overpayment ─────────────── */
  const payForm = $('[data-pay]');
  if (payForm) {
    const amount = $('[name=amount]', payForm);
    const balance = Number(payForm.dataset.pay || 0);
    const warn = $('[data-pay-warn]', payForm);
    if (amount && !amount.value && balance > 0) amount.value = Math.round(balance);
    amount?.addEventListener('input', () => {
      if (warn) warn.hidden = Number(amount.value || 0) <= balance + 1;
    });
  }

  /* ── invoice line editor: live line and invoice totals ──────────────────── */
  const linesForm = $('[data-lines]');
  if (linesForm) {
    const recalc = () => {
      let total = 0;
      $$('[data-line]', linesForm).forEach((row) => {
        const qty = Number($('[name$="qty"]', row)?.value || 0);
        const price = Number($('[name$="unit_price"]', row)?.value || 0);
        const discount = Number($('[name$="discount_pct"]', row)?.value || 0);
        const amount = qty * price * (1 - discount / 100);
        const cell = $('[data-line-amount]', row);
        if (cell) cell.textContent = rupees(amount);
        total += amount;
      });
      const out = $('[data-lines-total]');
      if (out) out.textContent = rupees(total);
    };
    linesForm.addEventListener('input', recalc);
    recalc();
  }

  /* ── bars and funnel steps grow once the width is known ─────────────────── */
  requestAnimationFrame(() => {
    $$('[data-w]').forEach((el) => { el.style.width = el.dataset.w; });
  });

  /* ── WhatsApp links built from a number field, where one exists ─────────── */
  $$('[data-wa-link]').forEach((link) => {
    const source = $(link.dataset.waLink);
    if (!source) return;
    const sync = () => {
      const digits = digitsOf(source.value);
      link.href = 'https://wa.me/' + digits;
      link.classList.toggle('is-off', !digits);
    };
    source.addEventListener('input', sync);
    sync();
  });
})();
