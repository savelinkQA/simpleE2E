from __future__ import annotations

import json
import os
import platform
import subprocess
from typing import Any


def enable_ui_recording(context) -> None:
    """
    Включает запись пользовательских действий в браузере.
    Работает только в headed режиме (HEADLESS=0).
    События пишутся в context._record_steps (если включён RECORD=1).
    """
    page = getattr(context, "page", None)
    if page is None:
        raise RuntimeError("Нет context.page. Сначала откройте приложение/страницу.")
    try:
        page.bring_to_front()
    except Exception:
        pass

    if context.__dict__.get("_ui_recorder_enabled", False):
        return

    context.__dict__["_ui_recorder_enabled"] = True

    from helpers.step_recording import (
        append_recorded_step_line,
        append_ui_step_line,
        mark_ui_step_deleted,
    )

    def _on_event(source, payload: Any) -> None:
        try:
            data = json.loads(payload) if isinstance(payload, str) else payload
        except Exception:
            return

        if not isinstance(data, dict):
            return

        ev_type   = str(data.get("type") or "").strip()
        file_name = str(data.get("file_name") or "").strip()
        step_id   = str(data.get("step_id") or "").strip()
        step_text = str(data.get("step_text") or "").strip()

        if ev_type == "ui_step":
            append_ui_step_line(context, step_id=step_id, step_text=step_text)

        elif ev_type == "ui_delete_step":
            mark_ui_step_deleted(context, step_id)

        elif ev_type == "baseline_screenshot":
            fn = (file_name or "baseline.png").replace("\\", "/").lstrip("/")
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            screens_dir = os.path.join(project_root, "features", "screens")
            expected_path = os.path.join(screens_dir, fn)

            # Нельзя вызывать page.screenshot() из expose_binding callback.
            # Ставим задачу в очередь; главный поток заберёт, покажет Save As,
            # сделает скрин и запишет шаг только при успешном сохранении.
            context.__dict__["_pending_screenshot"] = {
                "path": expected_path,
                "step_id": step_id,
                "step_text": step_text,
                "fn": fn,
            }

        elif ev_type == "recording_stop":
            context.__dict__["_ui_recorder_enabled"] = False

        elif ev_type == "recording_start":
            context.__dict__["_ui_recorder_enabled"] = True

    try:
        page.expose_binding("___ui_record", lambda source, payload: _on_event(source, payload))
    except Exception:
        pass

    page.add_init_script(_INSTALLER_JS)
    try:
        page.evaluate(_INSTALLER_JS)
    except Exception:
        pass

    try:
        steps = context.__dict__.get("_scenario_steps_index") or []
        feature_name = context.__dict__.get("_record_feature_name") or ""
        scenario_name = context.__dict__.get("_record_scenario_name") or ""
        page.evaluate(
            "(a) => { try { window.___uiRecLoadSteps && window.___uiRecLoadSteps(a.s, a.f, a.sc); } catch(e){} }",
            {"s": steps, "f": feature_name, "sc": scenario_name},
        )
    except Exception:
        pass


def _hide_our_elements(page) -> None:
    try:
        page.evaluate(
            "() => { try { "
            "['___uiRec_panel','___uiRec_menu','___uiRec_modal'].forEach("
            "id => { const el = document.getElementById(id); if(el) el.style.setProperty('visibility','hidden','important'); }"
            "); } catch(e){} }"
        )
    except Exception:
        pass


def _show_our_elements(page) -> None:
    try:
        page.evaluate(
            "() => { try { "
            "['___uiRec_panel','___uiRec_menu','___uiRec_modal'].forEach("
            "id => { const el = document.getElementById(id); if(el) el.style.removeProperty('visibility'); }"
            "); } catch(e){} }"
        )
    except Exception:
        pass


def _open_folder(path: str) -> None:
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    system = platform.system()
    if system == "Darwin":
        subprocess.Popen(["open", folder])
    elif system == "Windows":
        subprocess.Popen(["explorer", folder])
    else:
        subprocess.Popen(["xdg-open", folder])


def process_screenshot_queue(context) -> None:
    """
    Вызывать из главного потока Behave (step_pause / Я жду ручных действий).
    Забирает _pending_screenshot из context, показывает native Save As dialog,
    делает скриншот и открывает папку в Finder/Explorer.
    Шаг записывается только при успешном сохранении.
    """
    pending = context.__dict__.pop("_pending_screenshot", None)
    if not pending:
        return
    if isinstance(pending, str):
        pending = {"path": pending, "step_id": "", "step_text": "", "fn": os.path.basename(pending)}
    suggested_path = pending.get("path", "")
    step_id = pending.get("step_id", "")
    step_text = pending.get("step_text", "")
    fn = pending.get("fn", os.path.basename(suggested_path))

    page = getattr(context, "page", None)
    if page is None:
        return

    path = _ask_save_path(suggested_path)
    if not path:
        if step_id:
            try:
                page.evaluate(
                    """(sid) => {
                        try {
                            window.___uiRecTimeline = (window.___uiRecTimeline || []).filter(x => x.id !== sid);
                            var r = document.querySelector('[data-rec-row="' + sid + '"]');
                            if (r) r.remove();
                            var b = document.getElementById('___uiRec_badge');
                            if (b) b.textContent = String((window.___uiRecTimeline || []).length);
                        } catch(e) {}
                    }""",
                    step_id,
                )
            except Exception:
                pass
        return

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    screens_dir = os.path.join(project_root, "features", "screens")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    _hide_our_elements(page)
    try:
        page.screenshot(path=path)
    except Exception:
        _show_our_elements(page)
        return
    _show_our_elements(page)

    from helpers.step_recording import append_ui_step_line, append_recorded_step_line

    path_real = os.path.realpath(path)
    screens_real = os.path.realpath(screens_dir)
    if path_real.startswith(screens_real + os.sep) or path_real == screens_real:
        step_fn = os.path.relpath(path, screens_dir)
    else:
        step_fn = fn
    step_line = f'Then Сравнить со скрином "{_escape(step_fn)}"'

    if step_id and step_text:
        append_ui_step_line(context, step_id=step_id, step_text=step_line)
    else:
        append_recorded_step_line(context, step_line)

    try:
        page.evaluate(
            """(a) => { try {
                if (window.___uiRecTimeline && a[0] && a[1]) {
                    window.___uiRecTimeline.push({id:a[0],text:a[1]});
                    var sec = document.getElementById('___uiRec_recordedSec');
                    if (sec) {
                        var lbl = sec.querySelector('[data-rec-lbl]');
                        if (!lbl) {
                            lbl = document.createElement('div');
                            lbl.setAttribute('data-rec-lbl','1');
                            lbl.textContent = 'Записанные шаги';
                            lbl.style.cssText = 'padding:8px 14px 4px;font-size:11px;opacity:0.45;letter-spacing:0.6px;text-transform:uppercase;font-weight:600;';
                            sec.appendChild(lbl);
                        }
                        var parts = a[1].trim().split(' ');
                        var kw = parts[0] || 'Then';
                        var nm = parts.slice(1).join(' ');
                        var row = document.createElement('div');
                        row.style.cssText = 'display:flex;gap:10px;align-items:flex-start;padding:7px 14px;';
                        row.setAttribute('data-rec-row', a[0]);
                        var dot = document.createElement('div');
                        dot.style.cssText = 'margin-top:4px;width:9px;height:9px;border-radius:999px;background:rgba(58,134,255,0.45);border:1px solid rgba(58,134,255,0.65);flex:0 0 auto;';
                        var chip = document.createElement('span');
                        chip.textContent = (kw || 'THEN').toUpperCase().slice(0,5);
                        chip.style.cssText = 'display:inline-block;padding:2px 8px;border-radius:999px;border:1px solid rgba(0,255,160,0.30);background:rgba(0,255,160,0.13);color:rgba(200,255,235,0.95);font:11px/1.4 system-ui,sans-serif;flex:0 0 auto;';
                        var txt = document.createElement('div');
                        txt.textContent = nm;
                        txt.style.cssText = 'flex:1;font-size:12px;line-height:1.45;white-space:pre-wrap;word-break:break-word;opacity:0.90;font-family:ui-monospace,monospace;';
                        row.appendChild(dot); row.appendChild(chip); row.appendChild(txt);
                        sec.appendChild(row);
                        var body = document.getElementById('___uiRec_body');
                        if (body) body.scrollTop = body.scrollHeight;
                    }
                    var b = document.getElementById('___uiRec_badge');
                    if (b) b.textContent = String(window.___uiRecTimeline.length);
                }
            } catch(e){} }""",
            [step_id, step_line],
        )
    except Exception:
        pass

    try:
        path_real = os.path.realpath(path)
        screens_real = os.path.realpath(screens_dir)
        if not path_real.startswith(screens_real + os.sep) and path_real != screens_real:
            rel = os.path.relpath(suggested_path, screens_dir)
            dest = os.path.join(screens_dir, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            import shutil

            shutil.copy2(path, dest)
    except Exception:
        pass



def _ask_save_path(suggested_path: str) -> str | None:
    """
    Показывает native Save As dialog (Finder на macOS).
    Возвращает путь или None при отмене.
    """
    default_name = os.path.basename(suggested_path)
    if not default_name.lower().endswith(".png"):
        default_name = (default_name or "baseline") + ".png"

    if platform.system() == "Darwin":
        safe_name = default_name.replace('\\', '\\\\').replace('"', '\\"')
        script = f'''try
set theFile to choose file name with prompt "Сохранить эталонный скриншот" default name "{safe_name}"
return POSIX path of theFile
on error number -128
return ""
end try'''
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=120,
            )
            path = (result.stdout or "").strip()
            return path if path else None
        except Exception:
            pass

    # Fallback: tkinter
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return suggested_path

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    initial_dir = os.path.dirname(suggested_path)
    path = filedialog.asksaveasfilename(
        initialdir=initial_dir,
        initialfile=default_name,
        defaultextension=".png",
        filetypes=[("PNG images", "*.png"), ("All files", "*.*")],
        title="Сохранить эталонный скриншот",
    )
    try:
        root.destroy()
    except Exception:
        pass
    return path if path else None


def _escape(s: str) -> str:
    val = (s or "").replace("\r", " ").replace("\n", " ").replace("\t", " ")
    val = " ".join(val.split())
    return val.replace("\\", "\\\\").replace('"', '\\"')


_INSTALLER_JS = r"""
(() => {
  if (window.___uiRecInstalled) return;
  window.___uiRecInstalled = true;
  window.___uiRecActive = true;
  const PANEL_KEY  = '___uiRec.v3';
  const SS_TL      = '___uiRec.tl';    // timeline (sessionStorage)
  const SS_SC      = '___uiRec.sc';    // scenario steps (sessionStorage)
  const SS_META    = '___uiRec.meta';  // feature/scenario names
  const SS_URL     = '___uiRec.url';   // last known URL (navigation detection)

  function loadPersistedState() {
    try {
      var tl   = JSON.parse(sessionStorage.getItem(SS_TL)   || '[]');
      var sc   = JSON.parse(sessionStorage.getItem(SS_SC)   || '[]');
      var meta = JSON.parse(sessionStorage.getItem(SS_META) || '{}');
      window.___uiRecTimeline      = Array.isArray(tl) ? tl : [];
      window.___uiRecScenarioSteps = Array.isArray(sc) ? sc : [];
      window.___uiRecFeature  = meta.f  || '';
      window.___uiRecScenario = meta.sc || '';
    } catch(e) {
      window.___uiRecTimeline      = [];
      window.___uiRecScenarioSteps = [];
      window.___uiRecFeature  = '';
      window.___uiRecScenario = '';
    }
  }

  function saveTL() {
    try { sessionStorage.setItem(SS_TL, JSON.stringify(window.___uiRecTimeline)); } catch(e){}
  }

  function saveSC() {
    try {
      sessionStorage.setItem(SS_SC, JSON.stringify(
        window.___uiRecScenarioSteps.map(function(s) {
          return { idx: s.idx, keyword: s.keyword, name: s.name, done: !!s.done };
        })
      ));
      sessionStorage.setItem(SS_META, JSON.stringify({
        f:  window.___uiRecFeature,
        sc: window.___uiRecScenario
      }));
    } catch(e){}
  }

  // Загружаем сохранённое состояние сразу при старте
  loadPersistedState();

  /* ── детектирование полной навигации ─────────────────────────── */
  // Если URL изменился по сравнению с сохранённым — значит пришли с другой страницы
  var _storedUrl  = sessionStorage.getItem(SS_URL) || '';
  var _currentUrl = location.href;
  var _pendingNavStep = null;
  if (_storedUrl && _storedUrl !== _currentUrl) {
    _pendingNavStep = { sid: newId(), st: 'When Я перехожу на страницу "' + esc(_currentUrl) + '"' };
  }
  sessionStorage.setItem(SS_URL, _currentUrl);

  /* ── утилиты ─────────────────────────────────────────────────── */

  function newId() {
    try {
      if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
      if (window.crypto && window.crypto.getRandomValues) {
        var a = window.crypto.getRandomValues(new Uint8Array(16));
        a[6] = (a[6] & 15) | 64; a[8] = (a[8] & 63) | 128;
        return [a.slice(0,4),a.slice(4,6),a.slice(6,8),a.slice(8,10),a.slice(10,16)]
          .map(function(x){return Array.from(x).map(function(b){return ('0'+b.toString(16)).slice(-2);}).join('');}).join('-');
      }
    } catch(e){}
    return 'id_' + Date.now().toString(36);
  }

  function send(payload) {
    try { if (window.___ui_record) window.___ui_record(JSON.stringify(payload)); } catch(e){}
  }

  function esc(v) {
    // Нормализуем пробелы и экранируем для Gherkin
    var s = String(v || '').replace(/[\r\n\t]+/g, ' ').replace(/\s+/g, ' ').trim();
    var bs = String.fromCharCode(92);
    var dq = String.fromCharCode(34);
    return s.split(bs).join(bs + bs).split(dq).join(bs + dq);
  }

  function cssEsc(v) {
    try { return CSS.escape(v); } catch(e) { return String(v); }
  }

  function getBestSel(el) {
    if (!el) return '';
    var p = el.closest && el.closest('[data-test-id]');
    if (p) {
      var v = p.getAttribute('data-test-id');
      if (v) return '[data-test-id=' + JSON.stringify(v) + ']';
    }
    if (el.id) return '#' + cssEsc(el.id);
    var tag = (el.tagName || '').toLowerCase();
    if (!tag) return '';
    var cls = typeof el.className === 'string'
      ? el.className.trim().split(/\s+/).slice(0, 3).map(cssEsc) : [];
    return tag + (cls.length ? '.' + cls.join('.') : '');
  }

  function getName(el) {
    if (!el) return '';
    var srcs = [
      el.getAttribute && el.getAttribute('aria-label'),
      el.getAttribute && el.getAttribute('placeholder'),
      el.innerText || el.textContent || ''
    ];
    for (var i = 0; i < srcs.length; i++) {
      var v = (srcs[i] || '').replace(/\s+/g, ' ').trim().slice(0, 60);
      if (v) return v;
    }
    return '';
  }

  function isOurs(el) {
    if (!el || !el.closest) return false;
    return !!(el.closest('#___uiRec_panel') || el.closest('#___uiRec_menu') || el.closest('#___uiRec_modal'));
  }

  /* ── цвета шагов ─────────────────────────────────────────────── */

  var KW = {
    given: { bg: 'rgba(0,200,255,0.13)',  bc: 'rgba(0,200,255,0.30)',  c: 'rgba(200,240,255,0.95)' },
    when:  { bg: 'rgba(255,200,0,0.13)',  bc: 'rgba(255,200,0,0.30)',  c: 'rgba(255,245,200,0.95)' },
    then:  { bg: 'rgba(0,255,160,0.13)',  bc: 'rgba(0,255,160,0.30)',  c: 'rgba(200,255,235,0.95)' },
    and:   { bg: 'rgba(255,255,255,0.06)', bc: 'rgba(255,255,255,0.18)', c: 'rgba(255,255,255,0.78)' }
  };

  function kwKey(kw) {
    var k = (kw || '').toLowerCase();
    if (k === 'given') return 'given';
    if (k === 'when')  return 'when';
    if (k === 'then')  return 'then';
    return 'and';
  }

  function makeChip(kw) {
    var k = kwKey(kw), s = KW[k];
    var el = document.createElement('span');
    el.textContent = (kw || 'AND').toUpperCase().slice(0, 5);
    el.style.cssText =
      'display:inline-block;padding:2px 8px;border-radius:999px;' +
      'border:1px solid ' + s.bc + ';background:' + s.bg + ';color:' + s.c + ';' +
      'font:11px/1.4 system-ui,sans-serif;letter-spacing:0.4px;white-space:nowrap;flex:0 0 auto;';
    return el;
  }

  function makeStepRow(keyword, name, type, stepId) {
    var row = document.createElement('div');
    row.style.cssText = 'display:flex;gap:10px;align-items:flex-start;padding:7px 14px;';

    var dot = document.createElement('div');
    dot.setAttribute('data-role', 'dot');
    dot.style.cssText =
      'margin-top:4px;width:9px;height:9px;border-radius:999px;' +
      'background:rgba(255,255,255,0.18);border:1px solid rgba(255,255,255,0.20);flex:0 0 auto;';

    var txt = document.createElement('div');
    txt.textContent = name;
    txt.style.cssText =
      'flex:1;font-size:12px;line-height:1.45;white-space:pre-wrap;word-break:break-word;opacity:0.90;' +
      'font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;';

    row.appendChild(dot);
    row.appendChild(makeChip(keyword));
    row.appendChild(txt);

    if (type === 'recorded' && stepId) {
      // Синяя точка для записанных шагов
      dot.style.background = 'rgba(58,134,255,0.45)';
      dot.style.border = '1px solid rgba(58,134,255,0.65)';

      var del = document.createElement('button');
      del.type = 'button';
      del.textContent = '✕';
      del.style.cssText =
        'width:24px;height:24px;border-radius:8px;border:1px solid rgba(255,255,255,0.13);' +
        'background:rgba(255,255,255,0.04);color:rgba(255,255,255,0.50);cursor:pointer;font-size:12px;flex:0 0 auto;';
      del.onmouseenter = function() { del.style.background = 'rgba(255,70,70,0.18)'; del.style.color = '#fff'; };
      del.onmouseleave = function() { del.style.background = 'rgba(255,255,255,0.04)'; del.style.color = 'rgba(255,255,255,0.50)'; };
      del.addEventListener('click', function(e) {
        e.preventDefault(); e.stopPropagation();
        window.___uiRecTimeline = (window.___uiRecTimeline || []).filter(function(x) { return x.id !== stepId; });
        send({ type: 'ui_delete_step', step_id: stepId });
        saveTL();  // ← персистим удаление
        row.remove();
        updateBadge();
      });
      row.appendChild(del);
    }

    return row;
  }

  function updateBadge() {
    var b = document.getElementById('___uiRec_badge');
    if (b) b.textContent = String((window.___uiRecTimeline || []).length);
  }

  function timelineAppend(stepId, stepText) {
    try {
      if (!stepId || !stepText) return;
      var parts = stepText.trim().split(' ');
      var kw = parts[0] || 'When';
      var nm = parts.slice(1).join(' ');

      window.___uiRecTimeline.push({ id: stepId, text: stepText });
      if (window.___uiRecTimeline.length > 200) window.___uiRecTimeline.shift();
      saveTL();  // ← персистим

      var sec = document.getElementById('___uiRec_recordedSec');
      if (sec) {
        if (!sec.querySelector('[data-rec-lbl]') && !sec.querySelector('[data-rec-row]')) {
          var lbl = document.createElement('div');
          lbl.setAttribute('data-rec-lbl', '1');
          lbl.textContent = 'Записанные шаги';
          lbl.style.cssText = 'padding:8px 14px 4px;font-size:11px;opacity:0.45;letter-spacing:0.6px;text-transform:uppercase;font-weight:600;';
          sec.appendChild(lbl);
        }
        var row = makeStepRow(kw, nm, 'recorded', stepId);
        row.setAttribute('data-rec-row', stepId);
        sec.appendChild(row);
        var body = document.getElementById('___uiRec_body');
        if (body) body.scrollTop = body.scrollHeight;
      }
      updateBadge();
    } catch(e) {}
  }

  /* ── панель ───────────────────────────────────────────────────── */

  function buildPanel() {
    if (document.getElementById('___uiRec_panel')) return;

    var panel = document.createElement('div');
    panel.id = '___uiRec_panel';
    panel.style.cssText = [
      'position:fixed', 'right:18px', 'bottom:18px',
      'width:580px', 'height:360px',
      'min-width:300px', 'min-height:160px',
      'max-width:calc(100vw - 20px)', 'max-height:calc(100vh - 20px)',
      'background:linear-gradient(160deg, rgba(16,18,24,0.72), rgba(8,10,14,0.50))',
      'backdrop-filter:blur(20px) saturate(160%)',
      '-webkit-backdrop-filter:blur(20px) saturate(160%)',
      'border:1px solid rgba(255,255,255,0.11)',
      'border-radius:18px',
      'overflow:hidden',
      'z-index:2147483647',
      'box-shadow:0 20px 55px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.07)',
      'color:#fff',
      'resize:both',
      'font-family:system-ui,-apple-system,Segoe UI,sans-serif',
      'display:flex',
      'flex-direction:column'
    ].join(';');

    // Блокируем всплытие событий из панели наружу
    ['click', 'mousedown', 'pointerdown', 'contextmenu', 'keydown'].forEach(function(ev) {
      panel.addEventListener(ev, function(e) { e.stopPropagation(); }, false);
    });

    /* ── шапка ── */
    var hdr = document.createElement('div');
    hdr.style.cssText =
      'display:flex;align-items:center;justify-content:space-between;' +
      'padding:12px 14px;border-bottom:1px solid rgba(255,255,255,0.09);' +
      'background:rgba(255,255,255,0.04);cursor:move;user-select:none;flex-shrink:0;';

    if (!document.getElementById('___uiRec_style')) {
      var st = document.createElement('style');
      st.id = '___uiRec_style';
      st.textContent = '@keyframes ___uiRecBlink{0%,100%{opacity:1}50%{opacity:0.25}}';
      (document.head || document.documentElement).appendChild(st);
    }

    var hl = document.createElement('div');
    hl.style.cssText = 'display:flex;gap:10px;align-items:center;';

    var recDot = document.createElement('div');
    recDot.style.cssText =
      'width:9px;height:9px;border-radius:999px;background:rgba(255,70,70,0.85);' +
      'box-shadow:0 0 0 3px rgba(255,70,70,0.18);animation:___uiRecBlink 1.4s ease-in-out infinite;flex:0 0 auto;';

    var titleEl = document.createElement('span');
    titleEl.textContent = 'Recording';
    titleEl.style.cssText = 'font-size:13px;font-weight:700;opacity:0.88;letter-spacing:0.3px;';

    var badge = document.createElement('span');
    badge.id = '___uiRec_badge';
    badge.textContent = '0';
    badge.style.cssText =
      'font-size:11px;font-weight:700;background:rgba(255,255,255,0.09);' +
      'border:1px solid rgba(255,255,255,0.14);padding:1px 9px;border-radius:999px;';

    hl.appendChild(recDot);
    hl.appendChild(titleEl);
    hl.appendChild(badge);

    /* ── утилита копирования (clipboard fallback) ── */
    function _copyFallback(text) {
      try {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.style.cssText = 'position:fixed;top:-9999px;left:-9999px;opacity:0;pointer-events:none;';
        document.body.appendChild(ta);
        ta.focus(); ta.select();
        document.execCommand('copy');
        ta.remove();
      } catch(e) {}
    }

    var hr = document.createElement('div');
    hr.style.cssText = 'display:flex;gap:8px;align-items:center;';

    /* ── кнопка-переключатель «Записывать URL» ── */
    // Используем кнопку вместо label+checkbox: label генерирует второй синтетический
    // click прямо на input, который проходит через capture-фазу раньше, чем панель
    // успевает остановить его, и приложение скрывает панель.
    var SS_TRACK_URLS = '___uiRec.trackUrls';
    window.___uiRecTrackUrls = (sessionStorage.getItem(SS_TRACK_URLS) === 'true');

    var urlToggleBtn = document.createElement('button');
    urlToggleBtn.type = 'button';
    urlToggleBtn.title = 'Записывать переходы по URL (вкл/выкл)';

    function _updateUrlBtn() {
      var on = !!window.___uiRecTrackUrls;
      urlToggleBtn.textContent = 'URL';
      urlToggleBtn.style.cssText =
        'padding:5px 10px;border-radius:10px;border:1px solid ' +
        (on ? 'rgba(58,134,255,0.65)' : 'rgba(255,255,255,0.16)') + ';' +
        'background:' + (on ? 'rgba(58,134,255,0.25)' : 'rgba(255,255,255,0.05)') + ';' +
        'color:#fff;cursor:pointer;font-size:11px;font-family:inherit;' +
        'opacity:' + (on ? '1' : '0.55') + ';white-space:nowrap;';
    }
    _updateUrlBtn();

    urlToggleBtn.addEventListener('click', function(e) {
      e.preventDefault(); e.stopPropagation();
      window.___uiRecTrackUrls = !window.___uiRecTrackUrls;
      try { sessionStorage.setItem(SS_TRACK_URLS, String(window.___uiRecTrackUrls)); } catch(ee) {}
      _updateUrlBtn();
    });

    hr.appendChild(urlToggleBtn);

    function hBtn(label, onClick) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = label;
      b.style.cssText =
        'padding:6px 12px;border-radius:10px;border:1px solid rgba(255,255,255,0.16);' +
        'background:rgba(255,255,255,0.06);color:#fff;cursor:pointer;font-size:12px;font-family:inherit;';
      b.onmouseenter = function() { b.style.background = 'rgba(255,255,255,0.13)'; };
      b.onmouseleave = function() { b.style.background = 'rgba(255,255,255,0.06)'; };
      b.addEventListener('click', function(e) { e.preventDefault(); e.stopPropagation(); onClick(); });
      return b;
    }

    function _uuid() {
      try {
        if (crypto.randomUUID) return crypto.randomUUID();
        if (crypto.getRandomValues) {
          var a = crypto.getRandomValues(new Uint8Array(16));
          return Array.from(a).map(function(b){return ('0'+b.toString(16)).slice(-2);}).join('');
        }
      } catch(e){}
      return '0'.repeat(32);
    }
    function _meta() {
      var d = new Date();
      var y = d.getUTCFullYear(), m = ('0'+(d.getUTCMonth()+1)).slice(-2), day = ('0'+d.getUTCDate()).slice(-2);
      return ['# savetest_status: new','# savetest_author: auto','# savetest_created_at: ' + y + '-' + m + '-' + day,'@suite:' + _uuid(),'','Feature: ' + (window.___uiRecFeature || 'Recorded feature'),'','  @tms:' + _uuid(),'  @severity:high','  @tag:ui','  Scenario: ' + (window.___uiRecScenario || 'Recorded scenario'),''];
    }
    hr.appendChild(hBtn('Copy', function() {
      var feat = window.___uiRecFeature || 'Recorded feature';
      var scen = window.___uiRecScenario || 'Recorded scenario';
      var sc  = (window.___uiRecScenarioSteps || []).map(function(s) { return '    ' + s.keyword + ' ' + s.name; });
      var rec = (window.___uiRecTimeline || []).map(function(x) { return '    ' + x.text.replace(/\s+#\s+ui:id_[a-f0-9]+\s*$/i,''); });
      var meta = _meta();
      var textAll = meta.concat(sc).concat(rec).concat(['']).join('\n');
      var textRec = rec.concat(['']).join('\n');
      var pop = document.createElement('div');
      pop.style.cssText = 'position:absolute;right:0;top:100%;margin-top:4px;background:rgba(16,18,24,0.95);border:1px solid rgba(255,255,255,0.12);border-radius:10px;padding:4px;min-width:160px;z-index:999999;box-shadow:0 8px 24px rgba(0,0,0,0.4);';
      var closeHandler = function(e) {
        if (!pop.contains(e.target) && !hr.contains(e.target)) { pop.remove(); document.removeEventListener('click', closeHandler, true); }
      };
      function copyAndClose(t) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(t).catch(function() { _copyFallback(t); });
        } else { _copyFallback(t); }
        pop.remove();
        document.removeEventListener('click', closeHandler, true);
      }
      var b1 = document.createElement('button');
      b1.textContent = 'Всё';
      b1.style.cssText = 'display:block;width:100%;padding:8px 12px;border:none;background:transparent;color:#fff;cursor:pointer;font-size:12px;text-align:left;border-radius:8px;';
      b1.onmouseenter = function() { b1.style.background = 'rgba(255,255,255,0.1)'; };
      b1.onmouseleave = function() { b1.style.background = 'transparent'; };
      b1.onclick = function(e) { e.stopPropagation(); copyAndClose(textAll); };
      var b2 = document.createElement('button');
      b2.textContent = 'Только записанные';
      b2.style.cssText = b1.style.cssText;
      b2.onmouseenter = function() { b2.style.background = 'rgba(255,255,255,0.1)'; };
      b2.onmouseleave = function() { b2.style.background = 'transparent'; };
      b2.onclick = function(e) { e.stopPropagation(); copyAndClose(textRec); };
      pop.appendChild(b1); pop.appendChild(b2);
      hr.style.position = 'relative';
      hr.appendChild(pop);
      document.addEventListener('click', closeHandler, true);
    }));

    hdr.appendChild(hl);
    hdr.appendChild(hr);

    /* ── тело ── */
    var body = document.createElement('div');
    body.id = '___uiRec_body';
    body.style.cssText = 'flex:1;overflow-y:auto;overflow-x:hidden;padding:4px 0;';

    var scenSec = document.createElement('div');
    scenSec.id = '___uiRec_scenSec';

    var divider = document.createElement('div');
    divider.style.cssText = 'height:1px;background:rgba(255,255,255,0.08);margin:4px 14px;';

    var recSec = document.createElement('div');
    recSec.id = '___uiRec_recordedSec';

    body.appendChild(scenSec);
    body.appendChild(divider);
    body.appendChild(recSec);

    panel.appendChild(hdr);
    panel.appendChild(body);
    document.documentElement.appendChild(panel);

    /* ── Восстановление состояния из sessionStorage ── */

    // Сценарные шаги
    if (window.___uiRecScenarioSteps && window.___uiRecScenarioSteps.length > 0) {
      var scLbl = document.createElement('div');
      scLbl.textContent = 'Сценарий';
      scLbl.style.cssText = 'padding:8px 14px 4px;font-size:11px;opacity:0.45;letter-spacing:0.6px;text-transform:uppercase;font-weight:600;';
      scenSec.appendChild(scLbl);
      window.___uiRecScenarioSteps.forEach(function(s) {
        var row = makeStepRow(s.keyword, s.name, 'scenario', null);
        row.setAttribute('data-sc-idx', String(s.idx));
        if (s.done) {
          var dot = row.querySelector('[data-role="dot"]');
          if (dot) {
            dot.style.background = 'rgba(0,255,160,0.55)';
            dot.style.border = '1px solid rgba(0,255,160,0.75)';
            dot.style.boxShadow = '0 0 0 3px rgba(0,255,160,0.12)';
          }
          row.style.opacity = '0.5';
        }
        scenSec.appendChild(row);
      });
    }

    // Записанные шаги
    if (window.___uiRecTimeline && window.___uiRecTimeline.length > 0) {
      var recLbl = document.createElement('div');
      recLbl.setAttribute('data-rec-lbl', '1');
      recLbl.textContent = 'Записанные шаги';
      recLbl.style.cssText = 'padding:8px 14px 4px;font-size:11px;opacity:0.45;letter-spacing:0.6px;text-transform:uppercase;font-weight:600;';
      recSec.appendChild(recLbl);
      window.___uiRecTimeline.forEach(function(item) {
        var parts = item.text.trim().split(' ');
        var kw = parts[0] || 'When';
        var nm = parts.slice(1).join(' ');
        var row = makeStepRow(kw, nm, 'recorded', item.id);
        row.setAttribute('data-rec-row', item.id);
        recSec.appendChild(row);
      });
      updateBadge();
      setTimeout(function() { body.scrollTop = body.scrollHeight; }, 0);
    }

    /* ── API для Python ── */

    window.___uiRecLoadSteps = function(steps, featureName, scenarioName) {
      try {
        window.___uiRecFeature = featureName || '';
        window.___uiRecScenario = scenarioName || '';
        var arr = Array.isArray(steps) ? steps : [];
        window.___uiRecScenarioSteps = arr.map(function(s) {
          return { idx: Number(s.idx), keyword: String(s.keyword || '').trim(), name: String(s.name || '').trim(), done: false };
        });
        saveSC();  // ← персистим сценарные шаги
        var sec = document.getElementById('___uiRec_scenSec');
        if (!sec) return;
        sec.innerHTML = '';
        var lbl = document.createElement('div');
        lbl.textContent = 'Сценарий';
        lbl.style.cssText = 'padding:8px 14px 4px;font-size:11px;opacity:0.45;letter-spacing:0.6px;text-transform:uppercase;font-weight:600;';
        sec.appendChild(lbl);
        arr.forEach(function(s) {
          var row = makeStepRow(String(s.keyword || '').trim(), String(s.name || '').trim(), 'scenario', null);
          row.setAttribute('data-sc-idx', String(s.idx));
          sec.appendChild(row);
        });
      } catch(e) {}
    };

    window.___uiRecorderLoadScenarioSteps = window.___uiRecLoadSteps;

    window.___uiRecorderMarkScenarioStepDone = function(idx) {
      try {
        var i = Number(idx);
        // Обновляем флаг done в памяти
        var s = (window.___uiRecScenarioSteps || []).find(function(x) { return x.idx === i; });
        if (s) { s.done = true; saveSC(); }
        var row = document.querySelector('[data-sc-idx="' + i + '"]');
        if (!row) return;
        var dot = row.querySelector('[data-role="dot"]');
        if (dot) {
          dot.style.background = 'rgba(0,255,160,0.55)';
          dot.style.border = '1px solid rgba(0,255,160,0.75)';
          dot.style.boxShadow = '0 0 0 3px rgba(0,255,160,0.12)';
        }
        row.style.opacity = '0.5';
      } catch(e) {}
    };

    /* ── drag ── */
    var drag = null;

    hdr.addEventListener('pointerdown', function(e) {
      if (e.target.closest && e.target.closest('button')) return;
      e.preventDefault();
      var r = panel.getBoundingClientRect();
      drag = { ox: e.clientX - r.left, oy: e.clientY - r.top };
      panel.style.right = 'auto';
      panel.style.bottom = 'auto';
    });

    // Используем document для pointermove/up, чтобы drag работал при любом движении
    document.addEventListener('pointermove', function(e) {
      if (!drag) return;
      var pw = panel.offsetWidth, ph = panel.offsetHeight;
      var l = Math.max(0, Math.min(e.clientX - drag.ox, window.innerWidth - pw));
      var t = Math.max(0, Math.min(e.clientY - drag.oy, window.innerHeight - ph));
      panel.style.left = l + 'px';
      panel.style.top = t + 'px';
    }, false);

    document.addEventListener('pointerup', function() {
      if (!drag) return;
      drag = null;
      saveState();
    }, false);

    /* ── персистентность позиции/размера ── */
    function loadSt() {
      try { return JSON.parse(localStorage.getItem(PANEL_KEY) || 'null'); } catch(e) { return null; }
    }
    function saveState() {
      try {
        var r = panel.getBoundingClientRect();
        localStorage.setItem(PANEL_KEY, JSON.stringify({ l: r.left, t: r.top, w: r.width, h: r.height }));
      } catch(e) {}
    }
    var saved = loadSt();
    if (saved && typeof saved.l === 'number') {
      panel.style.right = 'auto';
      panel.style.bottom = 'auto';
      panel.style.left = Math.max(0, Math.min(saved.l, window.innerWidth - 80)) + 'px';
      panel.style.top  = Math.max(0, Math.min(saved.t, window.innerHeight - 60)) + 'px';
      if (saved.w) panel.style.width  = Math.max(300, Math.min(saved.w, window.innerWidth - 20)) + 'px';
      if (saved.h) panel.style.height = Math.max(160, Math.min(saved.h, window.innerHeight - 20)) + 'px';
    }
    try {
      new ResizeObserver(function() {
        clearTimeout(panel._saveTO);
        panel._saveTO = setTimeout(saveState, 300);
      }).observe(panel);
    } catch(e) {}
  }

  /* ── контекстное меню ─────────────────────────────────────────── */

  function removeMenu() {
    var m = document.getElementById('___uiRec_menu');
    if (m) m.remove();
  }

  function buildMenu(x, y, target) {
    removeMenu();
    var sel = getBestSel(target);
    var nm  = getName(target);

    var menu = document.createElement('div');
    menu.id = '___uiRec_menu';
    menu.style.cssText = [
      'position:fixed',
      'left:' + Math.min(x, window.innerWidth - 290) + 'px',
      'top:' + Math.min(y, window.innerHeight - 280) + 'px',
      'width:278px',
      'background:linear-gradient(160deg,rgba(16,18,24,0.85),rgba(8,10,14,0.65))',
      'backdrop-filter:blur(20px) saturate(160%)',
      '-webkit-backdrop-filter:blur(20px) saturate(160%)',
      'border:1px solid rgba(255,255,255,0.11)',
      'border-radius:14px',
      'padding:8px',
      'z-index:2147483647',
      'box-shadow:0 16px 44px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.07)',
      'color:#fff',
      'font-family:system-ui,-apple-system,Segoe UI,sans-serif'
    ].join(';');

    // Блокируем всплытие
    ['click', 'mousedown', 'pointerdown'].forEach(function(ev) {
      menu.addEventListener(ev, function(e) { e.stopPropagation(); }, false);
    });

    var lbl = document.createElement('div');
    lbl.textContent = 'Autotest tools';
    lbl.style.cssText =
      'font-size:11px;opacity:0.40;padding:4px 8px 8px;letter-spacing:0.6px;' +
      'text-transform:uppercase;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08);margin-bottom:4px;';
    menu.appendChild(lbl);

    function mBtn(_, text, onClick) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = text;
      b.style.cssText =
        'width:100%;padding:9px 12px;' +
        'border-radius:10px;border:none;background:transparent;color:#fff;' +
        'cursor:pointer;font-size:13px;font-family:inherit;text-align:left;';
      b.onmouseenter = function() { b.style.background = 'rgba(255,255,255,0.08)'; };
      b.onmouseleave = function() { b.style.background = 'transparent'; };
      b.addEventListener('click', function(e) {
        e.preventDefault(); e.stopPropagation();
        try { onClick(); } finally { removeMenu(); }
      });
      return b;
    }

    // 1. Элемент видим
    menu.appendChild(mBtn('', 'Элемент видим', function() {
      var sid = newId(), st = 'Then Вижу "' + esc(nm) + '"/"' + esc(sel) + '"';
      send({ type: 'ui_step', step_id: sid, step_text: st });
      timelineAppend(sid, st);
    }));

    // 2. Элемент НЕ видим
    menu.appendChild(mBtn('', 'Элемент НЕ видим', function() {
      var sid = newId(), st = 'Then НЕ Вижу "' + esc(nm) + '"/"' + esc(sel) + '"';
      send({ type: 'ui_step', step_id: sid, step_text: st });
      timelineAppend(sid, st);
    }));

    // 3. Текст содержит (с выбором типа) — подставляем текст элемента
    menu.appendChild(mBtn('', 'Текст содержит…', function() {
      openModal({
        title: 'Проверка текста',
        fields: [{ id: 'txt', label: 'Ожидаемый текст:', placeholder: 'Введите текст', def: nm }],
        extras: [{
          id: 'mode', type: 'radio', label: 'Тип сравнения:',
          options: [
            { value: 'contains', label: 'Содержит' },
            { value: 'exact',    label: 'Точное совпадение' }
          ],
          def: 'contains'
        }],
        onOk: function(v) {
          var sid = newId();
          var op = (v.mode === 'exact') ? '=' : '~';
          var st = 'Then Вижу в "' + esc(nm) + '"/"' + esc(sel) + '" текст ' + op + ' "' + esc(v.txt || '') + '"';
          send({ type: 'ui_step', step_id: sid, step_text: st });
          timelineAppend(sid, st);
        }
      });
    }));

    // 4. Текст НЕ содержит
    menu.appendChild(mBtn('', 'Текст НЕ содержит…', function() {
      openModal({
        title: 'Текст НЕ содержит',
        fields: [{ id: 'txt', label: 'Текст (которого НЕ должно быть):', placeholder: 'Введите текст' }],
        onOk: function(v) {
          var sid = newId(), st = 'Then НЕ Вижу текст "' + esc(v.txt || '') + '"';
          send({ type: 'ui_step', step_id: sid, step_text: st });
          timelineAppend(sid, st);
        }
      });
    }));

    // 5. Эталонный скрин — только отправляет запрос; шаг добавится после сохранения в Finder
    menu.appendChild(mBtn('', 'Эталонный скрин', function() {
      var sid = newId(), fn = 'baseline.png', st = 'Then Сравнить со скрином "' + esc(fn) + '"';
      send({ type: 'baseline_screenshot', step_id: sid, step_text: st, file_name: fn });
    }));

    var hint = document.createElement('div');
    hint.textContent = 'Shift + ПКМ';
    hint.style.cssText = 'font-size:11px;opacity:0.28;padding:6px 8px 2px;text-align:right;';
    menu.appendChild(hint);

    document.documentElement.appendChild(menu);

    // Закрываем по клику снаружи
    var onDown = function(e) {
      if (!menu.contains(e.target)) {
        removeMenu();
        document.removeEventListener('pointerdown', onDown, true);
      }
    };
    document.addEventListener('pointerdown', onDown, true);
  }

  /* ── модальное окно ──────────────────────────────────────────── */

  function openModal(opts) {
    var ex = document.getElementById('___uiRec_modal');
    if (ex) ex.remove();

    var overlay = document.createElement('div');
    overlay.id = '___uiRec_modal';
    overlay.style.cssText =
      'position:fixed;inset:0;background:rgba(0,0,0,0.28);' +
      'backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);' +
      'z-index:2147483647;display:flex;align-items:center;justify-content:center;';

    // Блокируем всплытие
    ['click', 'mousedown', 'pointerdown', 'keydown'].forEach(function(ev) {
      overlay.addEventListener(ev, function(e) { e.stopPropagation(); }, false);
    });

    var card = document.createElement('div');
    card.style.cssText = [
      'width:460px', 'max-width:calc(100vw - 32px)',
      'background:linear-gradient(160deg,rgba(16,18,24,0.96),rgba(8,10,14,0.88))',
      'backdrop-filter:blur(24px) saturate(160%)',
      '-webkit-backdrop-filter:blur(24px) saturate(160%)',
      'border:1px solid rgba(255,255,255,0.13)',
      'border-radius:18px',
      'box-shadow:0 24px 64px rgba(0,0,0,0.60), inset 0 1px 0 rgba(255,255,255,0.08)',
      'padding:20px',
      'color:#fff',
      'font-family:system-ui,-apple-system,Segoe UI,sans-serif'
    ].join(';');

    var ttl = document.createElement('div');
    ttl.textContent = opts.title || '';
    ttl.style.cssText = 'font-size:15px;font-weight:800;margin-bottom:16px;opacity:0.95;';
    card.appendChild(ttl);

    var inputs = {}, radios = {};

    (opts.fields || []).forEach(function(f) {
      var lbl = document.createElement('div');
      lbl.textContent = f.label || '';
      lbl.style.cssText = 'font-size:12px;opacity:0.62;margin-bottom:6px;margin-top:4px;';
      var inp = document.createElement('input');
      inp.type = 'text';
      inp.placeholder = f.placeholder || '';
      inp.value = f.def || '';
      inp.style.cssText =
        'width:100%;padding:10px 14px;border-radius:12px;border:1px solid rgba(255,255,255,0.15);' +
        'background:rgba(255,255,255,0.06);color:#fff;outline:none;font-size:13px;' +
        'font-family:inherit;box-sizing:border-box;';
      inp.onfocus = function() { inp.style.borderColor = 'rgba(58,134,255,0.65)'; inp.style.background = 'rgba(58,134,255,0.08)'; };
      inp.onblur  = function() { inp.style.borderColor = 'rgba(255,255,255,0.15)'; inp.style.background = 'rgba(255,255,255,0.06)'; };
      inputs[f.id] = { el: inp };
      card.appendChild(lbl);
      card.appendChild(inp);
    });

    (opts.extras || []).forEach(function(ex) {
      if (ex.type !== 'radio') return;
      var lbl = document.createElement('div');
      lbl.textContent = ex.label || '';
      lbl.style.cssText = 'font-size:12px;opacity:0.62;margin:12px 0 6px;';
      card.appendChild(lbl);

      var grp = document.createElement('div');
      grp.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap;';
      var sel = ex.def || (ex.options[0] && ex.options[0].value);
      var btns = {};
      var ACT = 'background:rgba(58,134,255,0.85);border-color:rgba(58,134,255,0.75);';
      var IDL = 'background:rgba(255,255,255,0.06);border-color:rgba(255,255,255,0.15);';
      var BASE = 'padding:8px 14px;border-radius:10px;border:1px solid;color:#fff;cursor:pointer;font-size:12px;font-family:inherit;';

      ex.options.forEach(function(opt) {
        var b = document.createElement('button');
        b.type = 'button';
        b.textContent = opt.label;
        b.style.cssText = BASE + (opt.value === sel ? ACT : IDL);
        b.addEventListener('click', function(e) {
          e.preventDefault(); e.stopPropagation();
          sel = opt.value;
          Object.keys(btns).forEach(function(v) {
            btns[v].style.cssText = BASE + (v === sel ? ACT : IDL);
          });
        });
        btns[opt.value] = b;
        grp.appendChild(b);
      });
      radios[ex.id] = { get: function() { return sel; } };
      card.appendChild(grp);
    });

    var row = document.createElement('div');
    row.style.cssText = 'display:flex;gap:10px;justify-content:flex-end;margin-top:18px;';

    function dlgBtn(label, primary, onClick) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = label;
      var bc = primary ? 'rgba(58,134,255,0.70)' : 'rgba(255,255,255,0.15)';
      var bg = primary ? 'rgba(58,134,255,0.85)' : 'rgba(255,255,255,0.06)';
      b.style.cssText =
        'padding:10px 18px;border-radius:12px;border:1px solid ' + bc + ';background:' + bg + ';' +
        'color:#fff;cursor:pointer;font-size:13px;font-weight:' + (primary ? '700' : '400') + ';font-family:inherit;';
      b.addEventListener('click', function(e) { e.preventDefault(); e.stopPropagation(); onClick(); });
      return b;
    }

    var close = function() { overlay.remove(); };
    row.appendChild(dlgBtn('Отмена', false, close));
    row.appendChild(dlgBtn('Добавить', true, function() {
      var vals = {};
      Object.keys(inputs).forEach(function(id) { vals[id] = inputs[id].el.value; });
      Object.keys(radios).forEach(function(id) { vals[id] = radios[id].get(); });
      try { (opts.onOk || function(){})(vals); } finally { close(); }
    }));
    card.appendChild(row);

    var onKey = function(e) {
      if (!overlay.isConnected) { document.removeEventListener('keydown', onKey, true); return; }
      if (e.key === 'Escape') { e.preventDefault(); close(); document.removeEventListener('keydown', onKey, true); }
      else if (e.key === 'Enter' && !e.shiftKey) {
        var tag = document.activeElement && document.activeElement.tagName;
        if (tag !== 'TEXTAREA') {
          e.preventDefault();
          var addBtn = row.querySelectorAll('button')[1];
          if (addBtn) addBtn.click();
          document.removeEventListener('keydown', onKey, true);
        }
      }
    };
    document.addEventListener('keydown', onKey, true);

    overlay.addEventListener('click', function(e) { if (e.target === overlay) close(); });
    overlay.appendChild(card);
    document.documentElement.appendChild(overlay);
    setTimeout(function() {
      var inp = card.querySelector('input');
      try { if (inp) { inp.focus(); inp.select(); } } catch(e) {}
    }, 0);
  }

  /* ── инициализация и листенеры ───────────────────────────────── */

  buildPanel();

  // Запись кликов
  document.addEventListener('click', function(e) {
    if (!window.___uiRecActive) return;
    var el = e.target;
    if (!el || el === document.documentElement || el === document.body) return;
    if (isOurs(el)) return;
    var sel = getBestSel(el), nm = getName(el);
    var sid = newId(), st = 'When Я нажимаю "' + esc(nm) + '"/"' + esc(sel) + '"';
    send({ type: 'ui_step', step_id: sid, step_text: st });
    timelineAppend(sid, st);
  }, true);

  // Запись ввода текста (дебаунс 400ms)
  var _inputTimers = typeof WeakMap !== 'undefined' ? new WeakMap() : null;
  document.addEventListener('input', function(e) {
    if (!window.___uiRecActive) return;
    var el = e.target;
    if (!el || isOurs(el)) return;
    var tag = (el.tagName || '').toLowerCase();
    if (tag !== 'input' && tag !== 'textarea') return;
    if (_inputTimers) clearTimeout(_inputTimers.get(el));
    var handle = setTimeout(function() {
      var sel = getBestSel(el), nm = getName(el), val = el.value || '';
      var sid = newId(), st = 'When Я ввожу "' + esc(val) + '" в "' + esc(nm) + '"/"' + esc(sel) + '"';
      send({ type: 'ui_step', step_id: sid, step_text: st });
      timelineAppend(sid, st);
    }, 400);
    if (_inputTimers) _inputTimers.set(el, handle);
  }, false);

  // Shift+ПКМ → контекстное меню
  document.addEventListener('contextmenu', function(e) {
    if (!e.shiftKey || !window.___uiRecActive) return;
    if (isOurs(e.target)) return;
    e.preventDefault(); e.stopPropagation();
    buildMenu(e.clientX, e.clientY, e.target);
  }, true);

  /* ── SPA-навигация: перехват history API ─────────────────────── */

  var _lastNavUrl = location.href;

  function onSpaNav() {
    var newUrl = location.href;
    if (newUrl === _lastNavUrl) return;
    _lastNavUrl = newUrl;
    sessionStorage.setItem(SS_URL, newUrl);
    if (!window.___uiRecTrackUrls) return;  // галочка выключена — не записываем
    var sid = newId();
    var st = 'When Я перехожу на страницу "' + esc(newUrl) + '"';
    send({ type: 'ui_step', step_id: sid, step_text: st });
    timelineAppend(sid, st);
  }

  try {
    var _origPush    = history.pushState;
    var _origReplace = history.replaceState;
    history.pushState = function() {
      _origPush.apply(this, arguments);
      setTimeout(onSpaNav, 0);
    };
    // replaceState — тихая замена URL (скролл, фильтры), не записываем
    window.addEventListener('popstate',   function() { setTimeout(onSpaNav, 0); });
    window.addEventListener('hashchange', function() { setTimeout(onSpaNav, 0); });
  } catch(e) {}

  /* ── Запись навигации при полной смене страницы ──────────────── */
  // _pendingNavStep был установлен вверху файла при сравнении SS_URL с location.href
  if (_pendingNavStep && window.___uiRecTrackUrls) {
    var _pn = _pendingNavStep;
    _pendingNavStep = null;
    setTimeout(function() {
      send({ type: 'ui_step', step_id: _pn.sid, step_text: _pn.st });
      timelineAppend(_pn.sid, _pn.st);
    }, 300);
  }

})();
"""
