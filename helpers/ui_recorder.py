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

    # Загружаем шаги сценария в панель
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
            "['___uiRec_panel','___uiRec_fab','___uiRec_menu','___uiRec_modal'].forEach("
            "id => { const el = document.getElementById(id); if(el) el.style.setProperty('visibility','hidden','important'); }"
            "); } catch(e){} }"
        )
    except Exception:
        pass


def _show_our_elements(page) -> None:
    try:
        page.evaluate(
            "() => { try { "
            "['___uiRec_panel','___uiRec_fab','___uiRec_menu','___uiRec_modal'].forEach("
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

    # Native Save As dialog — пользователь выбирает место сохранения
    path = _ask_save_path(suggested_path)
    if not path:
        # Отмена — убираем шаг из таймлайна в браузере
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

    # Записываем шаг только при успешном сохранении
    from helpers.step_recording import append_ui_step_line, append_recorded_step_line

    # fn для шага: относительный путь от features/screens/
    path_real = os.path.realpath(path)
    screens_real = os.path.realpath(screens_dir)
    if path_real.startswith(screens_real + os.sep) or path_real == screens_real:
        step_fn = os.path.relpath(path, screens_dir)
    else:
        step_fn = fn  # baseline.png, т.к. скопируем в suggested_path
    step_line = f'Then Сравнить со скрином "{_escape(step_fn)}"'

    if step_id and step_text:
        append_ui_step_line(context, step_id=step_id, step_text=step_line)
    else:
        append_recorded_step_line(context, step_line)

    # Добавляем в таймлайн панели (шаг появится только после сохранения)
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

    # Если сохранили вне features/screens/, копируем туда для шага "Сравнить со скрином"
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

    # Finder уже открыт при выборе пути — не открывать повторно


def _ask_save_path(suggested_path: str) -> str | None:
    """
    Показывает native Save As dialog (Finder на macOS).
    Возвращает путь или None при отмене.
    """
    default_name = os.path.basename(suggested_path)
    if not default_name.lower().endswith(".png"):
        default_name = (default_name or "baseline") + ".png"

    if platform.system() == "Darwin":
        # macOS: AppleScript — нативный диалог Finder
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


# JS installer — raw string, пишем JS как есть, без двойного экранирования.
# Все JS-строки используют одинарные кавычки, поэтому r"""...""" безопасен.
_INSTALLER_JS = r"""
(() => {
  if (window.___uiRecInstalled) return;
  window.___uiRecInstalled = true;
  window.___uiRecActive = true;
  window.___uiRecPaused = false;
  try { window.___uiRecPaused = (sessionStorage.getItem('___uiRec.paused') === '1'); } catch(e) {}
  var DEFAULT_ELEM_NAME = 'Имя элемента';
  const PANEL_KEY  = '___uiRec.v3';
  const PANEL_COLLAPSE_KEY = '___uiRec.collapsed';
  const FAB_POS_KEY = '___uiRec.fabPos';
  const SS_TL      = '___uiRec.tl';    // timeline (sessionStorage)
  const SS_SC      = '___uiRec.sc';    // scenario steps (sessionStorage)
  const SS_META    = '___uiRec.meta';  // feature/scenario names
  const SS_URL     = '___uiRec.url';   // last known URL (navigation detection)

  /* ── sessionStorage: загрузка / сохранение ──────────────────── */

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

  /* Селектор в шаге: двойные кавычки как в DOM, без esc() — иначе ломается разбор шага */
  function selStep(sel) {
    return String(sel || '').replace(/[\r\n\t]+/g, ' ').replace(/\s+/g, ' ').trim();
  }

  function extractPauseSecondsFromSteps(steps) {
    if (!Array.isArray(steps)) return null;
    var re = /Пауза\s+"(\d+)"/;
    for (var i = 0; i < steps.length; i++) {
      var s = steps[i];
      var nm = String(s.name || '').trim();
      var m = nm.match(re);
      if (m) return parseInt(m[1], 10);
      var line = (String(s.keyword || '').trim() + ' ' + nm).trim();
      m = line.match(re);
      if (m) return parseInt(m[1], 10);
    }
    return null;
  }

  function cssEsc(v) {
    try { return CSS.escape(v); } catch(e) { return String(v); }
  }

  function dtiAttrSel(node) {
    if (!node || !node.getAttribute) return '';
    var v = node.getAttribute('data-test-id');
    if (v === null || v === '') return '';
    return '[data-test-id=' + JSON.stringify(v) + ']';
  }

  /* Снизу вверх: nodes[0] — ближайший к клику узел с data-test-id, далее родители */
  function collectDtiNodesInnerToOuter(el) {
    var out = [];
    var cur = el;
    var hops = 0;
    while (cur && cur.nodeType === 1 && hops < 50) {
      if (dtiAttrSel(cur)) out.push(cur);
      if (cur.tagName === 'BODY' || cur.tagName === 'HTML') break;
      cur = cur.parentElement;
      hops++;
    }
    return out;
  }

  function relativePathChildCombinator(ancestor, target) {
    if (!ancestor || !target || ancestor === target) return '';
    if (!ancestor.contains(target)) return '';
    var segs = [];
    var cur = target;
    while (cur && cur !== ancestor) {
      var par = cur.parentElement;
      if (!par) return '';
      var tag = (cur.tagName || '').toLowerCase();
      if (!tag) return '';
      var siblingsSameTag = [];
      for (var i = 0; i < par.children.length; i++) {
        var c = par.children[i];
        if (c.nodeType === 1 && (c.tagName || '').toLowerCase() === tag) siblingsSameTag.push(c);
      }
      var idx = siblingsSameTag.indexOf(cur);
      if (idx < 0) return '';
      segs.unshift(tag + ':nth-of-type(' + (idx + 1) + ')');
      cur = par;
    }
    return segs.join(' > ');
  }

  function countMatches(sel) {
    try {
      return document.querySelectorAll(sel).length;
    } catch (e) {
      return 999;
    }
  }

  function getBestSel(el) {
    if (!el) return '';
    var nodes = collectDtiNodesInnerToOuter(el);
    if (nodes.length > 0) {
      var built = [];
      var sel = '';
      for (var i = 0; i < nodes.length; i++) {
        built.unshift(dtiAttrSel(nodes[i]));
        sel = built.join(' ');
        if (countMatches(sel) === 1) return sel;
      }
      var innerDti = nodes[0];
      if (el !== innerDti && innerDti.contains(el)) {
        var rel = relativePathChildCombinator(innerDti, el);
        if (rel) {
          var sRel = sel + ' > ' + rel;
          if (countMatches(sRel) === 1) return sRel;
        }
      }
      if (countMatches(sel) > 1 && nodes.length > 0) {
        var root = nodes[nodes.length - 1];
        var tight = relativePathChildCombinator(root, el);
        if (tight) {
          var sTight = dtiAttrSel(root) + ' > ' + tight;
          if (countMatches(sTight) === 1) return sTight;
        }
      }
      return sel;
    }
    if (el.id) return '#' + cssEsc(el.id);
    var tag = (el.tagName || '').toLowerCase();
    if (!tag) return '';
    var cls = typeof el.className === 'string'
      ? el.className.trim().split(/\s+/).slice(0, 3).map(cssEsc) : [];
    return tag + (cls.length ? '.' + cls.join('.') : '');
  }

  function getTextFromAriaLabelled(el) {
    var lab = el.getAttribute && el.getAttribute('aria-labelledby');
    if (!lab) return '';
    var ids = lab.split(/\s+/);
    var parts = [];
    for (var i = 0; i < ids.length; i++) {
      var n = document.getElementById(ids[i]);
      if (n && n.textContent) parts.push(n.textContent);
    }
    return parts.join(' ').replace(/\s+/g, ' ').trim();
  }

  function findPlaceholderFromNearby(el) {
    if (!el) return '';
    var tag = (el.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea') {
      var ph = el.getAttribute('placeholder');
      return ph ? String(ph) : '';
    }
    if (tag === 'img') return el.getAttribute('alt') || '';
    try {
      var q = el.querySelector && el.querySelector('input:not([type=hidden]):not([type="hidden"]), textarea');
      if (q) { var p1 = q.getAttribute('placeholder'); if (p1) return p1; }
    } catch(e) {}
    try {
      var lbl = el.closest && el.closest('label');
      if (lbl && lbl.control) {
        var c = lbl.control;
        var t = (c.tagName || '').toLowerCase();
        if ((t === 'input' || t === 'textarea') && c.getAttribute('placeholder'))
          return c.getAttribute('placeholder') || '';
      }
    } catch(e2) {}
    var p = el.parentElement;
    for (var h = 0; h < 8 && p; h++) {
      try {
        var inp = p.querySelector && p.querySelector('input:not([type=hidden]):not([type="hidden"]), textarea');
        if (inp) { var ph = inp.getAttribute('placeholder'); if (ph) return ph; }
      } catch(e3) {}
      p = p.parentElement;
    }
    return '';
  }

  function getNameRaw(el) {
    if (!el) return '';
    var tag = (el.tagName || '').toLowerCase();
    var srcs = [
      el.getAttribute && el.getAttribute('aria-label'),
      getTextFromAriaLabelled(el),
      el.getAttribute && el.getAttribute('title'),
      findPlaceholderFromNearby(el),
      el.getAttribute && el.getAttribute('placeholder'),
      tag === 'img' ? (el.getAttribute && el.getAttribute('alt')) : '',
      el.innerText || el.textContent || ''
    ];
    for (var i = 0; i < srcs.length; i++) {
      var v = (srcs[i] || '').replace(/\s+/g, ' ').trim().slice(0, 60);
      if (v) return v;
    }
    return '';
  }

  function getName(el) {
    return getNameRaw(el);
  }

  function getDisplayName(el) {
    var n = getNameRaw(el);
    return n || DEFAULT_ELEM_NAME;
  }

  function recordingAllowed() {
    return !!window.___uiRecActive && !window.___uiRecPaused;
  }

  function needsScrollIntoView(el) {
    if (!el || !el.getBoundingClientRect) return false;
    var r = el.getBoundingClientRect();
    var m = 2;
    if (r.width < 1 && r.height < 1) return true;
    return r.top < m || r.left < m || r.bottom > window.innerHeight - m || r.right > window.innerWidth - m;
  }

  function maybeEmitScrollStep(el) {
    if (!recordingAllowed() || !el) return;
    if (!needsScrollIntoView(el)) return;
    var sel = getBestSel(el);
    if (!sel) return;
    var nm = getDisplayName(el);
    var sid = newId();
    var st = 'When Я скролю до "' + esc(nm) + '"/"' + selStep(sel) + '"';
    send({ type: 'ui_step', step_id: sid, step_text: st });
    timelineAppend(sid, st);
  }

  function isOurs(el) {
    if (!el || !el.closest) return false;
    return !!(el.closest('#___uiRec_panel') || el.closest('#___uiRec_fab') || el.closest('#___uiRec_menu') || el.closest('#___uiRec_modal'));
  }

  /* ── горячие клавиши → строка для Playwright keyboard.press ───── */

  function isEditableTarget(el) {
    if (!el || !el.closest) return false;
    try {
      if (el.isContentEditable) return true;
    } catch (e) {}
    var tag = (el.tagName || '').toLowerCase();
    if (tag === 'textarea') return true;
    if (tag === 'input') {
      var type = (el.getAttribute('type') || 'text').toLowerCase();
      if (['button', 'submit', 'checkbox', 'radio', 'file', 'hidden', 'reset', 'image'].indexOf(type) >= 0) return false;
      return true;
    }
    if (tag === 'select') return true;
    return false;
  }

  function mainKeyForPlaywright(e) {
    var k = e.key;
    if (!k || k === 'Unidentified' || k === 'Dead') return null;
    if (k === ' ') return 'Space';
    if (e.code && /^Key[A-Z]$/.test(e.code)) return e.code.slice(3).toLowerCase();
    if (e.code && /^Digit[0-9]$/.test(e.code)) return e.code.slice(5);
    var codeMap = {
      'Space': 'Space', 'Minus': '-', 'Equal': '=', 'BracketLeft': '[', 'BracketRight': ']',
      'Backslash': '\\', 'Semicolon': ';', 'Quote': "'", 'Comma': ',', 'Period': '.', 'Slash': '/',
      'Backquote': '`', 'IntlBackslash': '\\', 'NumpadDecimal': 'Numpad.', 'NumpadAdd': 'Numpad+',
      'NumpadSubtract': 'Numpad-', 'NumpadMultiply': 'Numpad*', 'NumpadDivide': 'Numpad/'
    };
    if (e.code && codeMap[e.code]) return codeMap[e.code];
    if (e.code && /^Numpad[0-9]$/.test(e.code)) return e.code;
    if (e.code === 'NumpadEnter') return 'NumpadEnter';
    var named = {
      'Escape': 'Escape', 'Enter': 'Enter', 'Tab': 'Tab', 'Backspace': 'Backspace',
      'Delete': 'Delete', 'Insert': 'Insert', 'Home': 'Home', 'End': 'End',
      'PageUp': 'PageUp', 'PageDown': 'PageDown',
      'ArrowLeft': 'ArrowLeft', 'ArrowRight': 'ArrowRight', 'ArrowUp': 'ArrowUp', 'ArrowDown': 'ArrowDown'
    };
    if (named[k]) return named[k];
    if (/^F([1-9]|1[0-2])$/i.test(k)) return 'F' + String(k).match(/\d+/)[0];
    if (k.length === 1) return k;
    return null;
  }

  function buildPlaywrightShortcut(e) {
    var k = e.key;
    if (!k || k === 'Unidentified' || k === 'Dead') return null;
    if (k === 'Shift' || k === 'Control' || k === 'Alt' || k === 'Meta') return null;

    var ed = isEditableTarget(e.target);
    var c = e.ctrlKey, m = e.metaKey, a = e.altKey, s = e.shiftKey;

    // Только Shift + печатный символ в поле ввода — обычный ввод, не хоткей (Shift зарезервирован под меню инструмента)
    if (!c && !m && !a && s) {
      if (ed && k.length === 1) return null;
      if (/^F([1-9]|1[0-2])$/i.test(k)) { /* Shift+F* — фиксируем */ }
      else {
        var nav = ['Tab', 'Enter', 'Escape', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End', 'PageUp', 'PageDown'];
        if (nav.indexOf(k) < 0 && k.length !== 1) return null;
      }
    }

    var main = mainKeyForPlaywright(e);
    if (!main) return null;

    if (!c && !m && !a && !s) {
      if (/^F([1-9]|1[0-2])$/i.test(k)) return main;
      return null;
    }

    if (!c && !m && !a && s) {
      var partsS = ['Shift', main];
      return partsS.join('+');
    }

    if (c || m || a) {
      var parts = [];
      if (m) parts.push('Meta');
      if (c) parts.push('Control');
      if (a) parts.push('Alt');
      if (s) parts.push('Shift');
      parts.push(main);
      return parts.join('+');
    }

    return null;
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

  function updateRecordingChrome() {
    var paused = !!window.___uiRecPaused;
    var panel = document.getElementById('___uiRec_panel');
    var fab = document.getElementById('___uiRec_fab');
    if (panel) panel.setAttribute('data-paused', paused ? '1' : '0');
    if (fab) fab.setAttribute('data-paused', paused ? '1' : '0');
    try {
      document.querySelectorAll('[data-ui-rec-pause-btn]').forEach(function(b) {
        b.textContent = paused ? '▶' : '⏸';
        b.title = paused ? 'Продолжить запись' : 'Пауза';
      });
    } catch(e) {}
  }

  function applyCollapseState(collapsed) {
    window.___uiRecCollapsed = !!collapsed;
    try { localStorage.setItem(PANEL_COLLAPSE_KEY, collapsed ? '1' : '0'); } catch(e) {}
    var panel = document.getElementById('___uiRec_panel');
    var fab = document.getElementById('___uiRec_fab');
    if (panel) panel.style.display = collapsed ? 'none' : '';
    if (fab) fab.style.display = collapsed ? 'flex' : 'none';
  }

  function togglePause(ev) {
    if (ev) { ev.preventDefault(); ev.stopPropagation(); }
    window.___uiRecPaused = !window.___uiRecPaused;
    try { sessionStorage.setItem('___uiRec.paused', window.___uiRecPaused ? '1' : '0'); } catch(e) {}
    updateRecordingChrome();
  }

  function sendBaselineScreenshot() {
    var sid = newId(), fn = 'baseline.png', st = 'Then Сравнить со скрином "' + esc(fn) + '"';
    send({ type: 'baseline_screenshot', step_id: sid, step_text: st, file_name: fn });
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
      'flex-direction:column',
      'overscroll-behavior:contain'
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
      st.textContent =
        '@keyframes ___uiRecBlink{0%,100%{opacity:1}50%{opacity:0.25}}' +
        '#___uiRec_panel[data-paused="1"] #___uiRec_hdrDot,' +
        '#___uiRec_fab[data-paused="1"] .___uiRecFabDot{animation:none!important;opacity:.55}';
      (document.head || document.documentElement).appendChild(st);
    }

    var hl = document.createElement('div');
    hl.style.cssText = 'display:flex;gap:10px;align-items:center;';

    var recDot = document.createElement('div');
    recDot.id = '___uiRec_hdrDot';
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

    function syncPauseTimerUi() {
      var old = document.getElementById('___uiRec_timerWrap');
      if (old) old.remove();
      var psec = extractPauseSecondsFromSteps(window.___uiRecScenarioSteps || []);
      if (psec == null) return;
      var wrap = document.createElement('div');
      wrap.id = '___uiRec_timerWrap';
      wrap.title = 'Обратный отсчёт шага Пауза';
      wrap.style.cssText =
        'display:none;align-items:center;gap:6px;margin-left:4px;' +
        'padding:3px 10px;border-radius:10px;border:1px solid rgba(255,200,0,0.35);' +
        'background:rgba(255,200,0,0.10);flex-shrink:0;';
      var lab = document.createElement('span');
      lab.textContent = 'Пауза';
      lab.style.cssText = 'font-size:11px;opacity:0.75;font-weight:600;letter-spacing:0.3px;';
      var tim = document.createElement('span');
      tim.id = '___uiRec_timer';
      tim.textContent = '00:00';
      tim.style.cssText =
        'font-size:13px;font-weight:800;font-variant-numeric:tabular-nums;letter-spacing:0.5px;' +
        'color:rgba(255,230,160,0.98);min-width:52px;text-align:right;';
      wrap.appendChild(lab);
      wrap.appendChild(tim);
      hl.appendChild(wrap);
    }
    window.___uiRecSyncPauseTimerUi = syncPauseTimerUi;
    syncPauseTimerUi();

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

    var pauseBtnP = document.createElement('button');
    pauseBtnP.type = 'button';
    pauseBtnP.setAttribute('data-ui-rec-pause-btn', '1');
    pauseBtnP.title = 'Пауза';
    pauseBtnP.textContent = '⏸';
    pauseBtnP.style.cssText =
      'padding:6px 10px;border-radius:10px;border:1px solid rgba(255,255,255,0.16);' +
      'background:rgba(255,255,255,0.06);color:#fff;cursor:pointer;font-size:14px;font-family:inherit;line-height:1;';
    pauseBtnP.onmouseenter = function() { pauseBtnP.style.background = 'rgba(255,255,255,0.13)'; };
    pauseBtnP.onmouseleave = function() { pauseBtnP.style.background = 'rgba(255,255,255,0.06)'; };
    pauseBtnP.addEventListener('click', togglePause);

    var collapseBtnP = document.createElement('button');
    collapseBtnP.type = 'button';
    collapseBtnP.title = 'Свернуть в иконку';
    collapseBtnP.textContent = '⤡';
    collapseBtnP.style.cssText = pauseBtnP.style.cssText;
    collapseBtnP.onmouseenter = function() { collapseBtnP.style.background = 'rgba(255,255,255,0.13)'; };
    collapseBtnP.onmouseleave = function() { collapseBtnP.style.background = 'rgba(255,255,255,0.06)'; };
    collapseBtnP.addEventListener('click', function(e) {
      e.preventDefault(); e.stopPropagation();
      applyCollapseState(true);
    });

    hr.appendChild(pauseBtnP);
    hr.appendChild(collapseBtnP);

    hdr.appendChild(hl);
    hdr.appendChild(hr);

    /* ── тело ── */
    var body = document.createElement('div');
    body.id = '___uiRec_body';
    body.style.cssText =
      'flex:1 1 0%;min-height:0;max-height:100%;overflow-y:auto;overflow-x:hidden;padding:4px 0;' +
      'position:relative;-webkit-overflow-scrolling:touch;overscroll-behavior:contain;';

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

    // Не отменяем wheel целиком (иначе ломается нативный скролл). Только гасим «проброс» на страницу у края.
    body.addEventListener('wheel', function(e) {
      var el = this;
      var dy = e.deltaY;
      if (e.deltaMode === 1) dy *= 16;
      if (e.deltaMode === 2) dy *= (window.innerHeight || 600);
      var max = el.scrollHeight - el.clientHeight;
      if (max <= 0) {
        e.preventDefault();
        return;
      }
      var st = el.scrollTop;
      var atTop = st <= 0;
      var atBottom = st >= max - 1;
      if ((dy < 0 && atTop) || (dy > 0 && atBottom)) e.preventDefault();
    }, { passive: false });

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
        try { if (window.___uiRecSyncPauseTimerUi) window.___uiRecSyncPauseTimerUi(); } catch(e2) {}
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

    window.___uiRecSetPauseCountdown = function(rem) {
      try {
        var wrap = document.getElementById('___uiRec_timerWrap');
        var tim = document.getElementById('___uiRec_timer');
        if (!wrap || !tim) return;
        wrap.style.display = 'flex';
        var r = Math.max(0, parseInt(rem, 10) || 0);
        var m = Math.floor(r / 60), s = r % 60;
        tim.textContent = ('0' + m).slice(-2) + ':' + ('0' + s).slice(-2);
      } catch(e) {}
    };
    window.___uiRecClearPauseTimer = function() {
      try {
        var wrap = document.getElementById('___uiRec_timerWrap');
        if (wrap) wrap.style.display = 'none';
      } catch(e) {}
    };
  }

  function buildFab() {
    if (document.getElementById('___uiRec_fab')) return;

    var fab = document.createElement('div');
    fab.id = '___uiRec_fab';
    fab.style.cssText = [
      'position:fixed', 'right:18px', 'bottom:18px', 'top:auto', 'left:auto',
      'z-index:2147483647',
      'display:none',
      'flex-direction:row',
      'align-items:center',
      'gap:8px',
      'padding:8px 10px',
      'border-radius:16px',
      'border:1px solid rgba(255,255,255,0.12)',
      'background:linear-gradient(160deg,rgba(16,18,24,0.92),rgba(8,10,14,0.78))',
      'backdrop-filter:blur(18px) saturate(160%)',
      '-webkit-backdrop-filter:blur(18px) saturate(160%)',
      'box-shadow:0 10px 32px rgba(0,0,0,0.5)',
      'font-family:system-ui,-apple-system,Segoe UI,sans-serif',
      'cursor:grab'
    ].join(';');

    ['click', 'mousedown', 'pointerdown', 'contextmenu', 'keydown'].forEach(function(ev) {
      fab.addEventListener(ev, function(e) { e.stopPropagation(); }, false);
    });

    /* Перетаскивание FAB (не с кнопок) */
    var fabDrag = null;
    fab.addEventListener('pointerdown', function(e) {
      if (e.target.closest && e.target.closest('button')) return;
      e.preventDefault();
      var r = fab.getBoundingClientRect();
      fabDrag = { ox: e.clientX - r.left, oy: e.clientY - r.top };
      fab.style.right = 'auto';
      fab.style.bottom = 'auto';
      fab.style.left = r.left + 'px';
      fab.style.top = r.top + 'px';
      fab.style.cursor = 'grabbing';
      try { fab.setPointerCapture(e.pointerId); } catch(err) {}
    }, false);
    document.addEventListener('pointermove', function(e) {
      if (!fabDrag) return;
      var w = fab.offsetWidth, h = fab.offsetHeight;
      var l = Math.max(0, Math.min(e.clientX - fabDrag.ox, window.innerWidth - w));
      var t = Math.max(0, Math.min(e.clientY - fabDrag.oy, window.innerHeight - h));
      fab.style.left = l + 'px';
      fab.style.top = t + 'px';
    }, false);
    function endFabDrag() {
      if (!fabDrag) return;
      fabDrag = null;
      fab.style.cursor = 'grab';
      try {
        var br = fab.getBoundingClientRect();
        localStorage.setItem(FAB_POS_KEY, JSON.stringify({ l: br.left, t: br.top }));
      } catch(err) {}
    }
    document.addEventListener('pointerup', endFabDrag, false);
    fab.addEventListener('pointerup', endFabDrag, false);

    var expandBtn = document.createElement('button');
    expandBtn.type = 'button';
    expandBtn.title = 'Развернуть панель записи';
    expandBtn.style.cssText =
      'width:36px;height:36px;border-radius:10px;border:none;background:rgba(255,255,255,0.06);' +
      'cursor:pointer;padding:0;display:flex;align-items:center;justify-content:center;flex-shrink:0;';
    expandBtn.onmouseenter = function() { expandBtn.style.background = 'rgba(255,255,255,0.12)'; };
    expandBtn.onmouseleave = function() { expandBtn.style.background = 'rgba(255,255,255,0.06)'; };
    var fabDot = document.createElement('div');
    fabDot.className = '___uiRecFabDot';
    fabDot.style.cssText =
      'width:12px;height:12px;border-radius:999px;background:rgba(255,70,70,0.88);' +
      'box-shadow:0 0 0 3px rgba(255,70,70,0.2);animation:___uiRecBlink 1.4s ease-in-out infinite;';
    expandBtn.appendChild(fabDot);
    expandBtn.addEventListener('click', function(e) {
      e.preventDefault(); e.stopPropagation();
      applyCollapseState(false);
    });

    var pauseFab = document.createElement('button');
    pauseFab.type = 'button';
    pauseFab.setAttribute('data-ui-rec-pause-btn', '1');
    pauseFab.title = 'Пауза';
    pauseFab.textContent = '⏸';
    pauseFab.style.cssText =
      'min-width:34px;height:34px;border-radius:10px;border:1px solid rgba(255,255,255,0.14);' +
      'background:rgba(255,255,255,0.06);color:#fff;cursor:pointer;font-size:15px;line-height:1;padding:0 8px;';
    pauseFab.onmouseenter = function() { pauseFab.style.background = 'rgba(255,255,255,0.12)'; };
    pauseFab.onmouseleave = function() { pauseFab.style.background = 'rgba(255,255,255,0.06)'; };
    pauseFab.addEventListener('click', togglePause);

    var photoFab = document.createElement('button');
    photoFab.type = 'button';
    photoFab.title = 'Эталонный скрин';
    photoFab.style.cssText = pauseFab.style.cssText +
      ';display:inline-flex;align-items:center;justify-content:center;padding:0;width:34px;';
    var svgCam = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svgCam.setAttribute('width', '18');
    svgCam.setAttribute('height', '18');
    svgCam.setAttribute('viewBox', '0 0 24 24');
    svgCam.setAttribute('fill', 'none');
    svgCam.style.cssText = 'pointer-events:none;opacity:0.92;';
    var p1 = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    p1.setAttribute('d', 'M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z');
    p1.setAttribute('stroke', 'currentColor');
    p1.setAttribute('stroke-width', '2');
    p1.setAttribute('stroke-linecap', 'round');
    p1.setAttribute('stroke-linejoin', 'round');
    var c1 = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    c1.setAttribute('cx', '12');
    c1.setAttribute('cy', '13');
    c1.setAttribute('r', '4');
    c1.setAttribute('stroke', 'currentColor');
    c1.setAttribute('stroke-width', '2');
    svgCam.appendChild(p1);
    svgCam.appendChild(c1);
    photoFab.appendChild(svgCam);
    photoFab.onmouseenter = function() { photoFab.style.background = 'rgba(255,255,255,0.12)'; };
    photoFab.onmouseleave = function() { photoFab.style.background = 'rgba(255,255,255,0.06)'; };
    photoFab.addEventListener('click', function(e) {
      e.preventDefault(); e.stopPropagation();
      sendBaselineScreenshot();
    });

    fab.appendChild(expandBtn);
    fab.appendChild(pauseFab);
    fab.appendChild(photoFab);
    document.documentElement.appendChild(fab);

    var startCollapsed = false;
    try { startCollapsed = localStorage.getItem(PANEL_COLLAPSE_KEY) === '1'; } catch(e) {}
    applyCollapseState(startCollapsed);
    updateRecordingChrome();
    setTimeout(function() {
      try {
        var fp = JSON.parse(localStorage.getItem(FAB_POS_KEY) || 'null');
        if (fp && typeof fp.l === 'number' && typeof fp.t === 'number') {
          fab.style.right = 'auto';
          fab.style.bottom = 'auto';
          var w = fab.offsetWidth || 160, h = fab.offsetHeight || 44;
          fab.style.left = Math.max(0, Math.min(fp.l, window.innerWidth - w - 4)) + 'px';
          fab.style.top = Math.max(0, Math.min(fp.t, window.innerHeight - h - 4)) + 'px';
        }
      } catch(e) {}
    }, 0);
  }

  /* ── контекстное меню ─────────────────────────────────────────── */

  function removeMenu() {
    var m = document.getElementById('___uiRec_menu');
    if (m) m.remove();
  }

  function buildMenu(x, y, target) {
    removeMenu();
    var sel = getBestSel(target);
    var nm  = getDisplayName(target);

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
      var sid = newId(), st = 'Then Вижу "' + esc(nm) + '"/"' + selStep(sel) + '"';
      send({ type: 'ui_step', step_id: sid, step_text: st });
      timelineAppend(sid, st);
    }));

    // 2. Элемент НЕ видим
    menu.appendChild(mBtn('', 'Элемент НЕ видим', function() {
      var sid = newId(), st = 'Then НЕ Вижу "' + esc(nm) + '"/"' + selStep(sel) + '"';
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
          var st = 'Then Вижу в "' + esc(nm) + '"/"' + selStep(sel) + '" текст ' + op + ' "' + esc(v.txt || '') + '"';
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
      sendBaselineScreenshot();
    }));

    var hint = document.createElement('div');
    hint.textContent = 'Shift+ПКМ — меню; обычный ПКМ — в сценарий';
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
  buildFab();

  function clickModifiersList(e) {
    var out = [];
    if (e.metaKey) out.push('Meta');
    if (e.ctrlKey) out.push('Control');
    if (e.altKey) out.push('Alt');
    if (e.shiftKey) out.push('Shift');
    return out;
  }

  function gherkinClickStep(nm, sel, mods) {
    if (!mods || !mods.length)
      return 'When Я нажимаю "' + esc(nm) + '"/"' + selStep(sel) + '"';
    if (mods.length === 1 && mods[0] === 'Control')
      return 'When Я нажимаю+ctrl "' + esc(nm) + '"/"' + selStep(sel) + '"';
    if (mods.length === 1 && mods[0] === 'Meta')
      return 'When Я нажимаю+meta "' + esc(nm) + '"/"' + selStep(sel) + '"';
    if (mods.length === 1 && mods[0] === 'Alt')
      return 'When Я нажимаю+alt "' + esc(nm) + '"/"' + selStep(sel) + '"';
    if (mods.length === 1 && mods[0] === 'Shift')
      return 'When Я нажимаю+shift "' + esc(nm) + '"/"' + selStep(sel) + '"';
    var enc = mods.join('+');
    return 'When Я нажимаю с модификаторами "' + esc(enc) + '" на "' + esc(nm) + '"/"' + selStep(sel) + '"';
  }

  function isTextInputLike(el) {
    if (!el) return false;
    var tag = (el.tagName || '').toLowerCase();
    if (tag === 'textarea') return true;
    if (tag === 'select') return true;
    if (tag !== 'input') return false;
    var t = (el.getAttribute('type') || 'text').toLowerCase();
    if (['button', 'submit', 'checkbox', 'radio', 'file', 'hidden', 'reset', 'image', 'range'].indexOf(t) >= 0) return false;
    return true;
  }

  function recordInputValueStep(el) {
    if (!recordingAllowed() || !el || isOurs(el)) return;
    if (!isTextInputLike(el)) return;
    maybeEmitScrollStep(el);
    var sel = getBestSel(el), nm = getDisplayName(el);
    var val = el.value || '';
    var sid = newId(), st = 'When Я ввожу "' + esc(val) + '" в "' + esc(nm) + '"/"' + selStep(sel) + '"';
    send({ type: 'ui_step', step_id: sid, step_text: st });
    timelineAppend(sid, st);
  }

  // Запись кликов (в т.ч. с зажатым Ctrl / Meta / Alt / Shift)
  document.addEventListener('click', function(e) {
    if (!recordingAllowed()) return;
    var el = e.target;
    if (!el || el === document.documentElement || el === document.body) return;
    if (isOurs(el)) return;
    var tag = (el.tagName || '').toLowerCase();
    if (tag === 'select' || tag === 'option') return;
    maybeEmitScrollStep(el);
    var sel = getBestSel(el), nm = getDisplayName(el);
    var mods = clickModifiersList(e);
    var sid = newId(), st = gherkinClickStep(nm, sel, mods);
    send({ type: 'ui_step', step_id: sid, step_text: st });
    timelineAppend(sid, st);
  }, true);

  // Один шаг «ввожу» на поле: событие change (фиксация значения при уходе с поля / выборе в списке)
  document.addEventListener('change', function(e) {
    if (!recordingAllowed()) return;
    var el = e.target;
    if (!el || isOurs(el)) return;
    recordInputValueStep(el);
  }, false);

  // ПКМ: Shift+ПКМ → меню инструмента; без Shift → запись шага ПКМ (нативное меню не блокируем)
  document.addEventListener('contextmenu', function(e) {
    if (!window.___uiRecActive) return;
    if (isOurs(e.target)) return;
    if (e.shiftKey) {
      e.preventDefault(); e.stopPropagation();
      buildMenu(e.clientX, e.clientY, e.target);
      return;
    }
    if (!recordingAllowed()) return;
    var el = e.target;
    if (!el || el === document.documentElement || el === document.body) return;
    maybeEmitScrollStep(el);
    var sel = getBestSel(el), nm = getDisplayName(el);
    var sid = newId(), st = 'When Я нажимаю ПКМ на "' + esc(nm) + '"/"' + selStep(sel) + '"';
    send({ type: 'ui_step', step_id: sid, step_text: st });
    timelineAppend(sid, st);
  }, true);

  // Горячие клавиши (Shift только вместе с Ctrl/Meta/Alt или для навигации — см. buildPlaywrightShortcut)
  document.addEventListener('keydown', function(e) {
    if (!recordingAllowed()) return;
    if (isOurs(e.target)) return;
    if (e.repeat) return;
    var combo = buildPlaywrightShortcut(e);
    if (!combo) return;
    var sid = newId(), st = 'When Я нажимаю "' + esc(combo) + '" на клавиатуре';
    send({ type: 'ui_step', step_id: sid, step_text: st });
    timelineAppend(sid, st);
  }, true);

  /* ── SPA-навигация: перехват history API ─────────────────────── */

  var _lastNavUrl = location.href;

  function onSpaNav() {
    var newUrl = location.href;
    if (newUrl === _lastNavUrl) return;
    _lastNavUrl = newUrl;
    sessionStorage.setItem(SS_URL, newUrl);
    if (!recordingAllowed()) return;
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
      if (!recordingAllowed()) return;
      send({ type: 'ui_step', step_id: _pn.sid, step_text: _pn.st });
      timelineAppend(_pn.sid, _pn.st);
    }, 300);
  }

})();
"""
