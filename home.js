/* Главная: значения из сохранённых параметров и прогресс по модулям. */
(function () {
  "use strict";
  var N = window.NET;
  function store(k) { try { return JSON.parse(localStorage.getItem(k)); } catch (e) { return null; } }
  var DEF = N.defaults(), s = store("stand.params.v1") || {}, P = {};
  for (var k in DEF) P[k] = (s[k] !== undefined && s[k] !== null) ? String(s[k]) : DEF[k];
  if (Object.keys(N.validate(P).errors).length) P = DEF;
  var d = N.derive(P), D0 = N.derive(DEF);
  Array.prototype.forEach.call(document.querySelectorAll("[data-k]"), function (el) {
    var v = d[el.dataset.k]; if (v === undefined) return;
    el.textContent = v; el.classList.toggle("chg", v !== D0[el.dataset.k]);
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-mod]"), function (c) {
    var ids = (c.dataset.blocks || "").split(" "), done = store("stand.done.v1." + c.dataset.mod) || {}, n = 0;
    ids.forEach(function (id) { if (done[id]) n++; });
    var pct = ids.length ? Math.round(n * 100 / ids.length) : 0;
    c.querySelector("[data-bar]").style.width = pct + "%";
    c.querySelector("[data-done]").textContent = n ? "выполнено " + n + " из " + ids.length + " · " + pct + "%" : "не начат";
  });
})();
