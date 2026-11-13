// Deskvert website: the extra motion. The picker on this page (Ctrl + Shift), a real conversion in the browser,
// the changing headline, stickers to throw, cards that lean, headings word by word, the giant name at the end.
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const root = document.documentElement;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const fine = matchMedia("(pointer: fine)").matches;
  root.classList.add("fx");

  const kb = (n) => n < 1024 ? `${n} B` : n < 1048576 ? `${Math.round(n / 1024)} KB` : `${(n / 1048576).toFixed(1)} MB`;
  const sparks = (host, x, y, n = 12) => {
    if (reduce) return;
    for (let i = 0; i < n; i++) {
      const s = document.createElement("span"), a = (i / n) * Math.PI * 2 + Math.random() * .4, d = 40 + Math.random() * 46;
      s.className = "spark";
      s.style.left = `${x}px`; s.style.top = `${y}px`;
      s.style.setProperty("--dx", `${Math.cos(a) * d}px`); s.style.setProperty("--dy", `${Math.sin(a) * d}px`);
      host.appendChild(s);
      setTimeout(() => s.remove(), 900);
    }
  };

  // ---------------------------------------------------------------- the picker, on this page: tap Ctrl + Shift
  const CHIPS = [
    ["JPG", "photo.jpg", "612 KB"], ["PNG", "photo.png", "3.1 MB"], ["PDF", "photo.pdf", "540 KB"], ["WEBP", "photo.webp", "388 KB"],
    ["Compress", "photo (small).jpg", "214 KB", 1], ["Crop", "photo (cropped).heic", "1.6 MB", 1],
    ["Read text", "photo.txt", "2 KB", 1], ["ZIP", "photo.zip", "2.3 MB", 1],
  ];
  const qp = document.createElement("div");
  qp.className = "qp"; qp.inert = true; qp.setAttribute("role", "dialog"); qp.setAttribute("aria-label", "Convert photo.heic to");
  qp.innerHTML = `<div class="qp-ring"></div><div class="qp-hub"><i class="ph-fill ph-file-image" aria-hidden="true"></i>`
    + `<strong>photo.heic</strong><small>2.4 MB</small></div>`
    + CHIPS.map(([name, , , tool], i) => {
      const a = (i / CHIPS.length) * Math.PI * 2 - Math.PI / 2, r = 132;
      return `<button type="button" class="qp-chip${tool ? " tool" : ""}" style="--i:${i};--cx:${(Math.cos(a) * r).toFixed(1)}px;`
        + `--cy:${(Math.sin(a) * r).toFixed(1)}px" data-i="${i}">${name}</button>`;
    }).join("");
  const toast = document.createElement("div");
  toast.className = "qp-toast"; toast.setAttribute("role", "status");
  toast.innerHTML = `<i class="ph-fill ph-check-circle" aria-hidden="true"></i><div><strong></strong><span></span></div>`;
  document.body.append(qp, toast);

  let px = innerWidth / 2, py = innerHeight / 2, open = false, toastTimer = 0, opener = null;
  addEventListener("pointermove", (e) => { px = e.clientX; py = e.clientY; }, { passive: true });
  function openPicker(x = px, y = py, from = null) {
    const m = 175; // keep the whole ring on screen
    x = Math.min(Math.max(x, m), innerWidth - m); y = Math.min(Math.max(y, m), innerHeight - m);
    if (innerWidth < 360) x = innerWidth / 2;
    qp.style.left = `${x}px`; qp.style.top = `${y}px`;
    opener = from || document.activeElement;
    qp.inert = false; qp.classList.remove("on"); void qp.offsetWidth; qp.classList.add("on");
    open = true;
    setTimeout(() => open && $(".qp-chip", qp).focus({ preventScroll: true }), 60);
  }
  function closePicker() {
    if (!open) return;
    open = false; qp.inert = true; qp.classList.remove("on");
    if (opener && opener.focus) opener.focus({ preventScroll: true });
  }
  qp.addEventListener("click", (e) => {
    const chip = e.target.closest(".qp-chip");
    if (!chip) return;
    const [, out, size] = CHIPS[+chip.dataset.i];
    sparks(qp, parseFloat(chip.style.getPropertyValue("--cx")), parseFloat(chip.style.getPropertyValue("--cy")), 14);
    setTimeout(closePicker, 260);
    $("strong", toast).textContent = `Saved as ${out}`;
    $("span", toast).textContent = `2.4 MB → ${size}  ·  next to the original`;
    toast.classList.add("on");
    clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove("on"), 2800);
  });
  // just the two keys, pressed and let go, with nothing else in between (Ctrl+Shift+I and friends still work)
  let armed = false;
  addEventListener("keydown", (e) => {
    if (open && e.key === "Escape") { closePicker(); return; }
    if (open && e.key === "Tab") { // the focus stays on the ring
      const chips = $$(".qp-chip", qp), i = chips.indexOf(document.activeElement);
      e.preventDefault(); chips[(i + (e.shiftKey ? -1 : 1) + chips.length) % chips.length].focus();
      return;
    }
    armed = (e.key === "Control" || e.key === "Shift") && e.ctrlKey && e.shiftKey && !e.altKey && !e.metaKey && !e.repeat
      ? true : (e.key === "Control" || e.key === "Shift") ? armed : false;
  });
  addEventListener("keyup", (e) => {
    if (armed && (e.key === "Control" || e.key === "Shift")) {
      armed = false;
      const t = e.target;
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) && t.type !== "range")) return;
      open ? closePicker() : openPicker();
    }
  });
  addEventListener("pointerdown", (e) => { if (open && !e.target.closest(".qp-chip, .qp-hub")) closePicker(); });
  addEventListener("scroll", () => open && closePicker(), { passive: true });
  addEventListener("blur", () => { armed = false; });

  // ---------------------------------------------------------------- the headline: what it converts keeps changing
  const swap = $("#swap");
  if (swap && !reduce) {
    const pairs = ["HEIC → JPG", "DOCX → PDF", "MP4 → MP3", "MSG → PDF", "PNG → WEBP", "PDF → XLSX", "EPUB → PDF", "CSV → XLSX"];
    const glyphs = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    let n = 0;
    const scramble = (to) => {
      const from = swap.textContent, len = Math.max(from.length, to.length), t0 = performance.now(), dur = 620;
      swap.classList.add("busy");
      const step = (now) => {
        const k = Math.min(1, (now - t0) / dur);
        let s = "";
        for (let i = 0; i < len; i++) {
          const ch = to[i] || "";
          if (ch === " " || ch === "→") s += ch;
          else if (k > i / len * .7 + .3) s += ch;
          else s += k < .15 ? (from[i] || "") : glyphs[(Math.random() * glyphs.length) | 0];
        }
        swap.textContent = s.trimEnd();
        if (k < 1) requestAnimationFrame(step); else { swap.textContent = to; swap.classList.remove("busy"); }
      };
      requestAnimationFrame(step);
    };
    setInterval(() => { if (!document.hidden) scramble(pairs[(n = (n + 1) % pairs.length)]); }, 2600);
  }

  // ---------------------------------------------------------------- stickers: grab them, throw them
  const hero = $(".hero");
  $$(".sticker").forEach((el, i) => {
    el.style.setProperty("--i", i);
    let x = 0, y = 0, vx = 0, vy = 0, spin = 0, sx = 0, sy = 0, lx = 0, ly = 0, lt = 0, moved = 0, held = false, raf = 0;
    const put = () => {
      el.style.setProperty("--tx", `${x}px`); el.style.setProperty("--ty", `${y}px`); el.style.setProperty("--spin", `${spin}deg`);
    };
    const bounds = () => { // where it may go: inside the hero
      const h = hero.getBoundingClientRect(), r = el.getBoundingClientRect();
      return { minX: x - (r.left - h.left), maxX: x + (h.right - r.right), minY: y - (r.top - h.top), maxY: y + (h.bottom - r.bottom) };
    };
    const fly = () => {
      const b = bounds();
      vx *= .94; vy *= .94; x += vx; y += vy; spin += vx * .35;
      if (x < b.minX || x > b.maxX) { x = Math.min(Math.max(x, b.minX), b.maxX); vx *= -.6; }
      if (y < b.minY || y > b.maxY) { y = Math.min(Math.max(y, b.minY), b.maxY); vy *= -.6; }
      put();
      if (Math.abs(vx) + Math.abs(vy) > .3) raf = requestAnimationFrame(fly);
    };
    el.addEventListener("pointerdown", (e) => {
      if (e.button) return;
      cancelAnimationFrame(raf); held = true; moved = 0;
      sx = e.clientX - x; sy = e.clientY - y; lx = e.clientX; ly = e.clientY; lt = performance.now(); vx = vy = 0;
      el.setPointerCapture(e.pointerId); el.classList.add("held");
    });
    el.addEventListener("pointermove", (e) => {
      if (!held) return;
      const now = performance.now(), dt = Math.max(8, now - lt);
      vx = (e.clientX - lx) / dt * 16; vy = (e.clientY - ly) / dt * 16;
      moved += Math.abs(e.clientX - lx) + Math.abs(e.clientY - ly);
      lx = e.clientX; ly = e.clientY; lt = now;
      x = e.clientX - sx; y = e.clientY - sy; spin = Math.max(-25, Math.min(25, vx * 2)); put();
    });
    const drop = () => {
      if (!held) return;
      held = false; el.classList.remove("held");
      if (moved > 6 && !reduce) raf = requestAnimationFrame(fly);
      else if (el.id === "try-keys") { const r = el.getBoundingClientRect(); openPicker(r.left + r.width / 2, r.top - 150, el); }
    };
    el.addEventListener("pointerup", drop);
    el.addEventListener("pointercancel", drop);
    el.addEventListener("click", (e) => { if (e.detail === 0 && el.id === "try-keys") openPicker(undefined, undefined, el); }); // keyboard
  });

  // ---------------------------------------------------------------- try it right here: a real conversion, in this browser
  const drop = $("#drop"), input = $("#try-file"), note = $("#try-note"), result = $("#result");
  if (drop && input) {
    let file = null, outUrl = "", fmt = "image/jpeg", timer = 0;
    const quality = $("#try-quality"), qOut = $("#try-quality-out"), qRow = $("#try-quality-row");
    const ext = { "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp" };
    const decode = async (f) => {
      try { return await createImageBitmap(f); } catch { /* try the older way */ }
      const url = URL.createObjectURL(f);
      try {
        const img = new Image(); img.src = url; await img.decode(); return img;
      } finally { URL.revokeObjectURL(url); }
    };
    async function convert() {
      if (!file) return;
      drop.classList.add("busy"); note.textContent = "Converting…";
      let pic;
      try { pic = await decode(file); } catch {
        drop.classList.remove("busy");
        const heic = /\.(heic|heif)$/i.test(file.name);
        note.textContent = heic ? "Browsers can't open HEIC pictures. Deskvert can: tap Ctrl + Shift on it."
          : "That one isn't a picture this browser can open. Deskvert opens 197 kinds of files.";
        result.hidden = true; return;
      }
      const w = pic.width, h = pic.height, k = Math.min(1, 6000 / Math.max(w, h));
      const c = document.createElement("canvas"); c.width = Math.round(w * k); c.height = Math.round(h * k);
      const g = c.getContext("2d");
      if (fmt === "image/jpeg") { g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height); } // JPG has no see-through
      g.drawImage(pic, 0, 0, c.width, c.height);
      if (pic.close) pic.close();
      const blob = await new Promise((ok) => c.toBlob(ok, fmt, +quality.value / 100));
      drop.classList.remove("busy");
      if (!blob) { note.textContent = "This browser couldn't make that kind of file."; return; }
      const real = ext[blob.type] || "png";
      if (outUrl) URL.revokeObjectURL(outUrl);
      outUrl = URL.createObjectURL(blob);
      const name = file.name.replace(/\.[^.]+$/, "") + "." + real;
      $("#result-img").src = outUrl;
      $("#result-name").textContent = name;
      const diff = Math.round((1 - blob.size / file.size) * 100);
      $("#result-sizes").innerHTML = `${kb(file.size)} → ${kb(blob.size)}`
        + (diff > 0 ? ` <b class="smaller">−${diff}%</b>` : "");
      const save = $("#result-save"); save.href = outUrl; save.download = name;
      result.hidden = false; result.style.animation = "none"; void result.offsetWidth; result.style.animation = "";
      note.textContent = blob.type !== fmt ? `This browser can't write ${ext[fmt].toUpperCase()}, so it's a ${real.toUpperCase()}.`
        : "Done on your computer. Nothing was uploaded.";
      const r = drop.getBoundingClientRect();
      sparks(drop, r.width / 2, r.height / 2, 16);
    }
    const take = (f) => { if (f) { file = f; convert(); } };
    input.addEventListener("change", () => take(input.files[0]));
    drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
    ["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
    ["dragleave", "dragend"].forEach((t) => drop.addEventListener(t, () => drop.classList.remove("over")));
    drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); take(e.dataTransfer.files[0]); });
    // a picture dropped anywhere else on this part of the page still lands here
    const sec = $("#try");
    sec.addEventListener("dragover", (e) => e.preventDefault());
    sec.addEventListener("drop", (e) => { if (!drop.contains(e.target)) { e.preventDefault(); take(e.dataTransfer.files[0]); } });
    $$("#try-format button").forEach((b) => b.addEventListener("click", () => {
      $$("#try-format button").forEach((o) => o.setAttribute("aria-checked", String(o === b)));
      fmt = b.dataset.fmt; qRow.classList.toggle("off", fmt === "image/png");
      convert();
    }));
    quality.addEventListener("input", () => {
      qOut.textContent = quality.value; clearTimeout(timer); timer = setTimeout(convert, 180);
    });
  }

  // ---------------------------------------------------------------- headings come in word by word
  const words = new IntersectionObserver((entries) => entries.forEach((e) => {
    if (e.isIntersecting) { e.target.classList.add("in"); words.unobserve(e.target); }
  }), { threshold: .4 });
  $$("main h2").forEach((h) => {
    if (h.querySelector(".count") || h.closest(".policy")) return; // counters keep their own motion
    let i = 0;
    const walk = (node) => [...node.childNodes].forEach((n) => {
      if (n.nodeType === 3) {
        const frag = document.createDocumentFragment();
        n.textContent.split(/(\s+)/).forEach((part) => {
          if (!part) return;
          if (/^\s+$/.test(part)) { frag.append(" "); return; }
          const w = document.createElement("span"), inner = document.createElement("span");
          w.className = "w"; w.setAttribute("aria-hidden", "true"); inner.style.setProperty("--i", i++); inner.textContent = part;
          w.append(inner); frag.append(w);
        });
        n.replaceWith(frag);
      } else if (n.nodeType === 1 && n.tagName !== "BR") walk(n);
    });
    if (!h.getAttribute("aria-label")) h.setAttribute("aria-label", h.textContent.replace(/\s+/g, " ").trim());
    walk(h);
    h.classList.remove("reveal"); h.classList.add("split");
    words.observe(h);
  });

  // ---------------------------------------------------------------- videos wipe open; the giant name fills (older browsers)
  // (it watches the card, not the video: a fully clipped video never counts as on screen)
  const shown = new IntersectionObserver((entries) => entries.forEach((e) => {
    if (!e.isIntersecting) return;
    e.target.classList.add("in");
    $$("video", e.target).forEach((v) => v.classList.add("shown"));
    shown.unobserve(e.target);
  }), { threshold: .2 });
  $$(".cell, .slide, .demo").forEach((card) => shown.observe(card));
  if (!CSS.supports("animation-timeline: view()")) $$(".giant").forEach((g) => shown.observe(g));

  // ---------------------------------------------------------------- cards lean toward the pointer; the soft light follows it
  if (fine && !reduce) {
    $$(".cell, .slide").forEach((el) => {
      el.classList.add("tilt");
      el.addEventListener("pointermove", (e) => {
        const r = el.getBoundingClientRect(), dx = (e.clientX - r.left) / r.width - .5, dy = (e.clientY - r.top) / r.height - .5;
        el.style.setProperty("--ry", `${(dx * 7).toFixed(2)}deg`); el.style.setProperty("--rx", `${(-dy * 7).toFixed(2)}deg`);
      });
      el.addEventListener("pointerleave", () => { el.style.removeProperty("--rx"); el.style.removeProperty("--ry"); });
    });
    const glow = $("#glow");
    if (glow) {
      let gx = px, gy = py, on = false;
      const tick = () => {
        gx += (px - gx) * .12; gy += (py - gy) * .12;
        glow.style.transform = `translate(${gx.toFixed(1)}px, ${gy.toFixed(1)}px)`;
        if (Math.abs(px - gx) + Math.abs(py - gy) > .5) requestAnimationFrame(tick); else on = false;
      };
      addEventListener("pointermove", () => {
        glow.classList.add("on");
        if (!on) { on = true; requestAnimationFrame(tick); }
      }, { passive: true });
      document.addEventListener("pointerleave", () => glow.classList.remove("on"));
    }
  }
})();
