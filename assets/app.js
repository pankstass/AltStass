(function () {
  "use strict";
  var N = window.NET, PAGE = document.body.dataset.page || "m1";
  var KEY_P = "stand.params.v1", KEY_D = "stand.done.v1." + PAGE, KEY_HL = "stand.hl.v1";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var DEF = N.defaults(), D0 = N.derive(DEF);

  function store(k, v) { try { if (v === undefined) return JSON.parse(localStorage.getItem(k)); localStorage.setItem(k, JSON.stringify(v)); } catch (e) { return null; } }
  function toast(t) { var el = $("[data-toast]"); el.textContent = t; el.classList.add("on"); clearTimeout(el._t); el._t = setTimeout(function () { el.classList.remove("on"); }, 2200); }

  /* ---------- параметры ---------- */
  function loadParams() {
    var s = store(KEY_P) || {}, p = {};
    for (var k in DEF) p[k] = (s[k] !== undefined && s[k] !== null) ? String(s[k]) : DEF[k];
    return p;
  }
  var P = loadParams();
  if (Object.keys(N.validate(P).errors).length) P = N.defaults();

  function applyValues() {
    var d = N.derive(P);
    $$("[data-k]").forEach(function (el) {
      var k = el.dataset.k, v = d[k] !== undefined ? d[k] : el.textContent;
      if (el.textContent !== v) el.textContent = v;
      el.classList.toggle("chg", v !== D0[k]);
    });
    var n = 0; for (var k in DEF) if (P[k] !== DEF[k]) n++;
    $$("[data-pstate]").forEach(function (el) {
      el.textContent = n ? "Изменено параметров: " + n : "Параметры стенда по умолчанию";
      el.classList.toggle("chg", !!n);
    });
    renderKim();
  }
  function renderKim() {
    var ul = $("#kimcheck"); if (!ul) return;
    ul.innerHTML = "";
    N.kim(P).forEach(function (r) {
      var li = document.createElement("li");
      li.innerHTML = '<span class="st ' + (r[1] ? "ok" : "bad") + '">' + (r[1] ? "OK" : "НЕТ") + "</span><span></span><span class=\"val\"></span>";
      li.children[1].textContent = r[0]; li.children[2].textContent = r[2];
      ul.appendChild(li);
    });
  }

  /* ---------- диалог ---------- */
  var dlg = $("#params"), body = $("[data-pbody]"), msg = $("[data-pmsg]");
  function buildForm() {
    N.GROUPS.forEach(function (g) {
      var fs = document.createElement("fieldset"), lg = document.createElement("legend");
      lg.textContent = g.title; fs.appendChild(lg);
      g.fields.forEach(function (f) {
        var row = document.createElement("div"), id = "p_" + f[0];
        row.className = "fld"; row.dataset.key = f[0];
        row.innerHTML = '<label for="' + id + '"></label><input id="' + id + '" name="' + f[0] + '" spellcheck="false" autocomplete="off">';
        row.firstChild.textContent = f[1];
        var inp = row.lastChild; inp.placeholder = f[2];
        inp.addEventListener("input", function () { markField(row, inp.value); });
        fs.appendChild(row);
      });
      body.appendChild(fs);
    });
  }
  function markField(row, v, forced) {
    var f = N.FIELDS[row.dataset.key], e = forced !== undefined ? forced : (function () {
      var p = {}; p[f.key] = v; var r = N.validate(Object.assign({}, DEF, p)); return r.errors[f.key] && r.errors[f.key] !== "см. ниже" ? r.errors[f.key] : "";
    })();
    row.classList.toggle("chg", String(v).trim() !== f.def);
    row.classList.toggle("err", !!e);
    var em = $(".em", row);
    if (e) { if (!em) { em = document.createElement("div"); em.className = "em"; row.appendChild(em); } em.textContent = e; }
    else if (em) em.remove();
  }
  function fillForm(p) {
    $$(".fld", body).forEach(function (row) { var i = $("input", row); i.value = p[row.dataset.key]; markField(row, i.value, ""); });
  }
  function readForm() { var p = {}; $$(".fld", body).forEach(function (row) { p[row.dataset.key] = $("input", row).value.trim(); }); return p; }
  function showMsg(r, info) {
    var h = "";
    if (info) h += '<p class="i">' + info + "</p>";
    if (r && r.global.length) h += '<ul class="e">' + r.global.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>";
    if (r && Object.keys(r.errors).length && !r.global.length) h += '<p class="e">Исправьте отмеченные поля.</p>';
    if (r && r.warnings.length) h += '<ul class="w">' + r.warnings.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>";
    msg.innerHTML = h;
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function openDlg() {
    if (!body.children.length) buildForm();
    fillForm(P); showMsg(null, "");
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
  }
  function closeDlg() { if (dlg.close) dlg.close(); else dlg.removeAttribute("open"); }
  $$("[data-open-params]").forEach(function (b) { b.addEventListener("click", openDlg); });
  $("[data-close]").addEventListener("click", closeDlg);
  dlg.addEventListener("click", function (e) { if (e.target === dlg) closeDlg(); });
  $("[data-apply]").addEventListener("click", function () {
    var p = readForm(), r = N.validate(p);
    $$(".fld", body).forEach(function (row) { markField(row, p[row.dataset.key], r.errors[row.dataset.key] || ""); });
    if (Object.keys(r.errors).length) { showMsg(r); var first = $(".fld.err input", body); if (first) first.focus(); return; }
    P = p; store(KEY_P, P); applyValues(); closeDlg();
    toast(r.warnings.length ? "Команды пересобраны · есть предупреждения" : "Команды пересобраны под новые параметры");
    if (r.warnings.length) console.warn(r.warnings.join("\n"));
  });
  $("[data-preset]").addEventListener("click", function () {
    var p = Object.assign(readForm(), N.KIM_PRESET); fillForm(p);
    showMsg(null, "Подставлены маски по КИМ (VLAN /27, /28, /29, BR /28). Нажмите «Пересобрать команды», чтобы применить.");
  });
  $("[data-defaults]").addEventListener("click", function () { fillForm(DEF); showMsg(null, "Подставлены значения стенда. Нажмите «Пересобрать команды», чтобы применить."); });
  $("[data-export]").addEventListener("click", function () { download("stand-params.json", JSON.stringify(readForm(), null, 2), "application/json"); });
  $("[data-import]").addEventListener("change", function (e) {
    var f = e.target.files[0]; if (!f) return;
    var rd = new FileReader();
    rd.onload = function () {
      try { var j = JSON.parse(rd.result), p = readForm(); for (var k in DEF) if (j[k] !== undefined) p[k] = String(j[k]); fillForm(p); showMsg(N.validate(p), "Файл загружен. Проверьте значения и нажмите «Пересобрать команды»."); }
      catch (x) { showMsg(null, "Не удалось прочитать JSON."); }
      e.target.value = "";
    };
    rd.readAsText(f);
  });

  /* ---------- копирование ---------- */
  function copyText(t) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(t);
    return new Promise(function (ok, no) {
      var a = document.createElement("textarea"); a.value = t; a.setAttribute("readonly", ""); a.style.position = "fixed"; a.style.opacity = "0";
      document.body.appendChild(a); a.select();
      try { document.execCommand("copy") ? ok() : no(); } catch (e) { no(e); }
      document.body.removeChild(a);
    });
  }
  function codeOf(b) { return $("code", b).textContent.replace(/\s+$/, "") + "\n"; }
  function flash(btn, t, cls) { var o = btn.dataset.label || (btn.dataset.label = btn.textContent); btn.textContent = t; if (cls) btn.classList.add(cls); clearTimeout(btn._t); btn._t = setTimeout(function () { btn.textContent = o; btn.classList.remove("ok"); }, 1600); }
  $$(".block .copy").forEach(function (btn) {
    btn.addEventListener("click", function () {
      copyText(codeOf(btn.closest(".block"))).then(function () { flash(btn, "Скопировано ✓", "ok"); }, function () { flash(btn, "Ошибка"); });
    });
  });

  /* ---------- отметки «готово» ---------- */
  var done = store(KEY_D) || {};
  function updProgress() {
    var all = $$(".block"), n = 0;
    all.forEach(function (b) { var on = !!done[b.id]; b.classList.toggle("isdone", on); $(".done input", b).checked = on; if (on) n++; });
    $$(".step").forEach(function (s) {
      var bs = $$(".block", s), k = bs.filter(function (b) { return done[b.id]; }).length;
      s.classList.toggle("alldone", k === bs.length);
      var c = $('[data-cnt="' + s.id + '"]'); if (c) { c.textContent = k ? k + "/" + bs.length : ""; c.classList.toggle("full", k === bs.length); }
    });
    var pct = all.length ? Math.round(n * 100 / all.length) : 0;
    $$("[data-prog]").forEach(function (e) { e.style.width = pct + "%"; });
    $$("[data-prog-txt]").forEach(function (e) { e.textContent = n ? pct + "%" : ""; });
  }
  $$(".block .done input").forEach(function (cb) {
    cb.addEventListener("change", function () { var id = cb.closest(".block").id; if (cb.checked) done[id] = 1; else delete done[id]; store(KEY_D, done); updProgress(); });
  });
  $$("[data-reset-done]").forEach(function (b) { b.addEventListener("click", function () { if (confirm("Сбросить все отметки на этой странице?")) { done = {}; store(KEY_D, done); updProgress(); } }); });

  /* ---------- фильтр и поиск ---------- */
  var curDev = "", query = "";
  function matchDev(b) { var d = b.dataset.dev.split("|"); return !curDev || d.indexOf(curDev) >= 0 || d.indexOf("Все ВМ") >= 0; }
  function applyFilter() {
    var any = false, q = query.toLowerCase();
    $$(".step").forEach(function (s) {
      var vis = false, stepHit = q && (s.dataset.title || "").toLowerCase().indexOf(q) >= 0;
      $$(".block", s).forEach(function (b) {
        var ok = matchDev(b) && (!q || stepHit || b.textContent.toLowerCase().indexOf(q) >= 0);
        b.classList.toggle("hidden", !ok); if (ok) vis = true;
      });
      s.classList.toggle("hidden", !vis); if (vis) any = true;
    });
    $("[data-empty]").hidden = any;
    var da = $("[data-devact]");
    da.hidden = !curDev;
    if (curDev) { var n = $$(".block").filter(matchDev).length; $("[data-devact-txt]").textContent = curDev + ": блоков — " + n + " (все шаги страницы, без учёта поиска)"; }
  }
  $$(".filter [data-f]").forEach(function (b) {
    b.addEventListener("click", function () {
      curDev = b.dataset.f;
      $$(".filter [data-f]").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
      applyFilter();
    });
  });
  var st; $("[data-search]").addEventListener("input", function (e) { clearTimeout(st); st = setTimeout(function () { query = e.target.value.trim(); applyFilter(); }, 120); });

  /* ---------- скрипт для одной ВМ ---------- */
  function scriptFor(dev) {
    var lines = ["#!/bin/bash", "# " + dev + " — " + document.title, "# Собрано: " + new Date().toLocaleString("ru-RU"), "# Выполняйте по частям и проверяйте вывод: часть команд (exec bash, reboot, ssh-copy-id) интерактивны.", ""];
    $$(".step").forEach(function (s) {
      $$(".block", s).filter(matchDev).forEach(function (b) {
        lines.push("# ===== " + s.dataset.num + ". " + s.dataset.title + " — " + $(".btitle", b).textContent + (b.dataset.kind === "check" ? " (проверка)" : "") + " =====");
        lines.push(codeOf(b));
      });
    });
    return lines.join("\n");
  }
  function download(name, text, type) {
    var a = document.createElement("a"), url = URL.createObjectURL(new Blob([text], { type: type || "text/x-shellscript" }));
    a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }
  $("[data-copy-all]").addEventListener("click", function (e) {
    var btn = e.currentTarget; copyText(scriptFor(curDev)).then(function () { flash(btn, "Скопировано ✓"); }, function () { flash(btn, "Ошибка"); });
  });
  $("[data-download]").addEventListener("click", function () { download(curDev.toLowerCase() + (PAGE === "m2" ? "-m2" : "") + ".sh", scriptFor(curDev)); });

  /* ---------- подсветка параметров ---------- */
  var hl = $("[data-hl]"), hlOn = store(KEY_HL); if (hlOn === false) hl.checked = false;
  function setHl() { document.body.classList.toggle("nohl", !hl.checked); store(KEY_HL, hl.checked); }
  hl.addEventListener("change", setHl); setHl();

  /* ---------- сворачивание длинных блоков ---------- */
  $$(".block pre").forEach(function (pre) {
    var n = pre.textContent.split("\n").length;
    if (n <= 22) return;
    pre.classList.add("collapsed");
    var b = document.createElement("button"); b.type = "button"; b.className = "more";
    b.textContent = "Развернуть · " + n + " строк"; b.setAttribute("aria-expanded", "false");
    b.addEventListener("click", function () {
      var c = pre.classList.toggle("collapsed");
      b.textContent = c ? "Развернуть · " + n + " строк" : "Свернуть"; b.setAttribute("aria-expanded", String(!c));
      if (c) b.closest(".block").scrollIntoView({ block: "nearest" });
    });
    pre.after(b);
  });

  /* ---------- подсветка текущего раздела ---------- */
  var links = {}; $$(".toc a").forEach(function (a) { links[a.getAttribute("href").slice(1)] = a; });
  var targets = Object.keys(links).map(function (id) { return document.getElementById(id); }).filter(Boolean);
  function spy() {
    var y = window.innerHeight * 0.3, cur = null;
    targets.forEach(function (t) { if (t.offsetParent !== null && t.getBoundingClientRect().top <= y) cur = t; });
    Object.keys(links).forEach(function (id) { links[id].classList.toggle("active", cur && cur.id === id); });
    if (cur) { var a = links[cur.id], side = a.closest("aside"); if (side) { var r = a.getBoundingClientRect(); if (r.top < 0 || r.bottom > window.innerHeight) a.scrollIntoView({ block: "nearest" }); } }
  }
  var raf; window.addEventListener("scroll", function () { cancelAnimationFrame(raf); raf = requestAnimationFrame(spy); }, { passive: true });

  window.addEventListener("beforeprint", function () { $$("pre.collapsed").forEach(function (p) { p.dataset.wasCollapsed = "1"; p.classList.remove("collapsed"); }); });
  window.addEventListener("afterprint", function () { $$("pre[data-was-collapsed]").forEach(function (p) { p.classList.add("collapsed"); delete p.dataset.wasCollapsed; }); });

  applyValues(); updProgress(); applyFilter(); spy();
})();
