// Draws every <figure data-chart> from the JSON the site build put inside it (site/research.py).
// Without this script the figure shows its data table; with it the table folds away under the chart.
// A chart is rows of measures on one axis from zero: a bar per series, or, where the build has the
// value of every piece behind a mean, a dot per piece with the mean marked. Values that span several
// powers of ten get a logarithmic axis and dots: a bar needs a zero to stand on.
// The exact values of the row under the pointer or the keyboard are written in a panel under the
// plot, so nothing ever covers the rows.
(function () {
  "use strict";
  var NS = "http://www.w3.org/2000/svg";
  var uid = 0;

  function svg(name, attrs, parent) {
    var el = document.createElementNS(NS, name);
    for (var k in attrs) el.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(el);
    return el;
  }
  function htm(name, cls, text, parent) {
    var el = document.createElement(name);
    if (cls) el.className = cls;
    if (text != null) el.textContent = text;
    if (parent) parent.appendChild(el);
    return el;
  }
  // Wraps a label into lines of at most `width` px, measured in the SVG it will sit in.
  function wrap(text, width, probe) {
    var lines = [], line = "";
    text.split(" ").forEach(function (word) {
      probe.textContent = line ? line + " " + word : word;
      if (line && probe.getComputedTextLength() > width) { lines.push(line); line = word; }
      else line = probe.textContent;
    });
    lines.push(line);
    probe.textContent = "";
    return lines;
  }

  function Chart(figure) {
    this.figure = figure;
    this.data = JSON.parse(figure.querySelector('script[type="application/json"]').textContent);
    this.plot = figure.querySelector(".chart-plot");
    this.view = 0;
    this.row = 0;
    this.id = "chart" + ++uid;
    this.controls();
    this.canvas = htm("div", "chart-canvas", null, this.plot);
    this.tip = htm("div", "chart-tip", null, this.plot);
    this.tip.setAttribute("aria-hidden", "true");  // each row's own label says the same to a screen reader
    this.plot.hidden = false;
    figure.classList.add("is-live");
    figure.querySelector(".chart-data").open = false;
    var self = this;
    if (window.ResizeObserver) {
      new ResizeObserver(function () {
        if (Math.abs(self.canvas.clientWidth - self.width) > 1) self.draw();
      }).observe(this.canvas);
    }
    this.draw();
    this.hide();
  }

  Chart.prototype.controls = function () {
    var d = this.data, self = this, bar = htm("div", "chart-controls", null, this.plot);
    if (d.views.length > 1) {
      var set = htm("fieldset", "chart-views", null, bar);
      htm("legend", null, d.viewLabel, set);
      d.views.forEach(function (view, i) {
        var label = htm("label", null, null, set);
        var input = htm("input", null, null, label);
        input.type = "radio"; input.name = self.id; input.checked = i === 0;
        input.addEventListener("change", function () { self.view = i; self.row = 0; self.hide(); self.draw(true); });
        htm("span", null, view.l, label);
      });
    }
    if (d.series.length > 1) {
      var key = htm("ul", "chart-key", null, bar);
      this.keys = d.series.map(function (name, i) {
        var li = htm("li", null, null, key);
        htm("i", "s" + (i + 1), null, li);
        htm("span", null, name, li);
        return li;
      });
    }
    this.note = htm("p", "chart-note", null, this.plot);
    this.note.setAttribute("aria-live", "polite");  // a new view is announced: its name, what it is, how much was measured
  };

  Chart.prototype.draw = function (animate) {
    var d = this.data, view = d.views[this.view], self = this;
    var W = this.width = Math.max(240, this.canvas.clientWidth);
    var wide = W >= 560, labelW = wide ? Math.min(230, W * 0.34) : 0;
    var dots = view.rows.some(function (r) { return r.c.some(function (c) { return c && c.p; }); });
    if (view.log) dots = true;
    var x0 = labelW, x1 = W - (dots ? 58 : 52);
    var at = view.log
      ? function (v) { return x0 + (x1 - x0) * Math.log(Math.max(v, view.min) / view.min) / Math.log(view.max / view.min); }
      : function (v) { return x0 + v * (x1 - x0) / view.max; };
    var lane = dots ? 20 : 16;
    this.note.textContent = [d.views.length > 1 ? view.l + "." : "", view.note, view.n ? view.n.charAt(0).toUpperCase() + view.n.slice(1) + "." : ""].join(" ").trim();
    (this.keys || []).forEach(function (li, s) {
      li.hidden = !view.rows.some(function (r) { return r.c[s]; });
    });
    this.canvas.textContent = "";
    var root = svg("svg", { "class": "chart-svg" + (animate ? " is-new" : ""), width: W, role: "group",
      "aria-label": this.figure.querySelector(".chart-title").textContent + ". " + view.l }, this.canvas);
    var probe = svg("text", { "class": "chart-label", x: 0, y: -99 }, root);
    var grid = svg("g", { "aria-hidden": "true" }, root), rows = svg("g", null, root);
    var y = view.mark ? 18 : 6;
    this.rows = view.rows.map(function (row, r) {
      var lines = wrap(row.l, wide ? labelW - 14 : W - 4, probe);
      var own = view.n ? [] : wrap(row.n || "", wide ? labelW - 14 : W - 4, probe).filter(Boolean);  // its own sample size
      var count = lines.length;
      lines = lines.concat(own);
      var bars = row.c.length * lane, head = wide ? 0 : lines.length * 17 + 3;
      var height = Math.max(bars, wide ? lines.length * 17 : 0) + head + 14;
      var g = svg("g", { "class": "chart-row", role: "img", tabindex: r === self.row ? 0 : -1, "aria-label": self.describe(row) }, rows);
      svg("rect", { "class": "chart-hit", x: 0, y: y, width: W, height: height, rx: 6 }, g);
      var ty = wide ? y + 7 + (Math.max(bars, lines.length * 17) - lines.length * 17) / 2 + 12 : y + 7 + 12;
      lines.forEach(function (line, i) {
        svg("text", { "class": i < count ? "chart-label" : "chart-count", x: wide ? 6 : 2, y: ty + i * 17 }, g).textContent = line;
      });
      var by = y + 7 + head + (wide ? Math.max(0, lines.length * 17 - bars) / 2 : 0);
      row.c.forEach(function (cell, s) {
        if (!cell) return;
        var cy = by + s * lane + lane / 2, cls = " s" + (s + 1), end = at(cell.v);
        if (cell.p) {
          var lo = Math.min.apply(null, cell.p), hi = Math.max.apply(null, cell.p);
          svg("line", { "class": "chart-range" + cls, x1: at(lo), x2: at(hi), y1: cy, y2: cy }, g);
          cell.p.forEach(function (p) { svg("circle", { "class": "chart-piece" + cls, cx: at(p), cy: cy, r: 3 }, g); });
        }
        if (dots) {
          // The mean's number goes in a column at the right: beside the dot it would sit among the pieces.
          svg("circle", { "class": "chart-mean" + cls, cx: end, cy: cy, r: 6 }, g);
          svg("text", { "class": "chart-value", x: W - 2, y: cy + 4.5, "text-anchor": "end" }, g).textContent = cell.t;
        } else {
          svg("path", { "class": "chart-bar" + cls, d: bar(x0, cy - 6, Math.max(1, end - x0), 12) }, g);
          svg("text", { "class": "chart-value", x: end + 6, y: cy + 4.5 }, g).textContent = cell.t;
        }
      });
      var top = y;
      g.addEventListener("pointerenter", function () { self.show(r); });
      // A row that has the keyboard's focus keeps its tip when the pointer leaves another row.
      g.addEventListener("pointerleave", function () { if (self.focused == null) self.hide(); else self.show(self.focused); });
      g.addEventListener("focus", function () { self.row = self.focused = r; self.show(r); });
      g.addEventListener("blur", function () { self.focused = null; self.hide(); });
      g.addEventListener("keydown", function (ev) { self.key(ev, r); });
      y += height;
      return { g: g, top: top, height: height, row: row };
    });
    view.ticks.forEach(function (tick) {
      var x = Math.round(at(tick.v)) + 0.5;
      svg("line", { "class": "chart-grid" + (tick.v === 0 ? " zero" : ""), x1: x, x2: x, y1: 2, y2: y + 2 }, grid);
      var anchor = tick.v === 0 && !wide ? "start" : "middle";
      svg("text", { "class": "chart-tick", x: x, y: y + 17, "text-anchor": anchor }, grid).textContent = tick.t;
    });
    if (view.mark) {
      var mx = Math.round(at(view.mark.v)) + 0.5;
      svg("line", { "class": "chart-mark", x1: mx, x2: mx, y1: 0, y2: y + 2 }, grid);
      svg("text", { "class": "chart-mark-label", x: mx - 5, y: 11, "text-anchor": "end" }, grid).textContent = view.mark.t;
    }
    var ax = wrap(view.axis, x1 - x0 + 40, probe);
    ax.forEach(function (line, i) {
      svg("text", { "class": "chart-axis", x: x0, y: y + 36 + i * 15 }, grid).textContent = line;
    });
    root.setAttribute("height", y + 42 + (ax.length - 1) * 15);
    root.setAttribute("viewBox", "0 0 " + W + " " + (y + 42 + (ax.length - 1) * 15));
  };

  // A bar from the baseline: square where it starts, rounded where the value ends.
  function bar(x, y, w, h) {
    var r = Math.min(4, w);
    return "M" + x + " " + y + "h" + (w - r) + "a" + r + " " + r + " 0 0 1 " + r + " " + r + "v" + (h - 2 * r) +
      "a" + r + " " + r + " 0 0 1 " + -r + " " + r + "h" + -(w - r) + "z";
  }

  Chart.prototype.describe = function (row) {
    var d = this.data, parts = [row.l];
    row.c.forEach(function (cell, s) {
      if (!cell) return;
      var text = (d.series.length > 1 ? d.series[s] + ": " : "") + cell.t;
      if (cell.p) text += " (" + d.words.range + " " + cell.lo + "–" + cell.hi + ")";
      parts.push(text);
    });
    if (row.n) parts.push(row.n);
    return parts.join(". ");
  };

  Chart.prototype.show = function (r) {
    var d = this.data, at = this.rows[r], tip = this.tip;
    tip.textContent = "";
    htm("p", "chart-tip-title", at.row.l, tip);
    at.row.c.forEach(function (cell, s) {
      if (!cell) return;
      var line = htm("p", "chart-tip-row", null, tip);
      htm("i", "s" + (s + 1), null, line);
      htm("b", null, cell.t, line);
      if (d.series.length > 1) htm("span", null, d.series[s], line);
      if (cell.p) htm("span", "chart-tip-range", d.words.range + ": " + cell.lo + "–" + cell.hi, line);
    });
    if (at.row.n) htm("p", "chart-tip-n", at.row.n, tip);
    tip.classList.add("is-on");
    this.rows.forEach(function (row, i) { row.g.classList.toggle("is-on", i === r); });
  };
  Chart.prototype.hide = function () {
    this.tip.classList.remove("is-on");
    this.tip.textContent = this.data.words.hint;
    (this.rows || []).forEach(function (row) { row.g.classList.remove("is-on"); });
  };
  Chart.prototype.key = function (ev, r) {
    var next = { ArrowDown: r + 1, ArrowUp: r - 1, Home: 0, End: this.rows.length - 1 }[ev.key];
    if (ev.key === "Escape") { this.hide(); return; }
    if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); this.show(r); return; }
    if (next == null || next < 0 || next >= this.rows.length) return;
    ev.preventDefault();
    this.rows[r].g.setAttribute("tabindex", -1);
    this.rows[next].g.setAttribute("tabindex", 0);
    this.rows[next].g.focus();
  };

  function start() {
    Array.prototype.forEach.call(document.querySelectorAll("figure[data-chart]"), function (figure) {
      try { new Chart(figure); } catch (e) {
        // The table stays: a figure never ends up empty.
        figure.classList.remove("is-live");
        figure.querySelector(".chart-plot").hidden = true;
        figure.querySelector(".chart-data").open = true;
      }
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
