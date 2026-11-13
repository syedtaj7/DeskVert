// Deskvert website: the live picker in the hero, the drifting file types, reveals, counters, the processor
// gauge, the download link (newest release from GitHub) and the theme switch. No libraries.
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const root = document.documentElement;

  // ---------------------------------------------------------------- theme (auto, light, dark)
  const darkQuery = matchMedia("(prefers-color-scheme: dark)");
  const isDark = () => root.dataset.theme === "dark" || (root.dataset.theme !== "light" && darkQuery.matches);
  // the animations are the app's own, as short videos: a still picture at once, the video only while on screen
  const mediaName = (v) => v.dataset.media || v.closest("[data-story]")?.dataset.story;
  const mediaSrc = (v, ext) => "assets/media/" + mediaName(v) + "-" + (isDark() ? "dark" : "light") + "." + ext;
  function applyTheme() {
    $$("video.themed").forEach((v) => {
      v.poster = mediaSrc(v, "jpg");
      if (v.dataset.live) { // playing already: swap to the other theme's video in place
        v.src = mediaSrc(v, "mp4");
        v.play().catch(() => {});
      }
    });
    const icon = $("#theme-toggle i");
    if (icon) icon.className = isDark() ? "ph ph-sun" : "ph ph-moon-stars";
    sky.recolor();
  }
  $("#theme-toggle")?.addEventListener("click", () => {
    root.dataset.theme = isDark() ? "light" : "dark";
    try { localStorage.setItem("deskvert-theme", root.dataset.theme); } catch (e) { /* private window */ }
    applyTheme();
  });
  darkQuery.addEventListener("change", applyTheme);

  // ---------------------------------------------------------------- the sky: file types drifting by
  const sky = (() => {
    const canvas = $("#sky");
    const ctx = canvas.getContext("2d");
    const words = ["HEIC", "JPG", "PDF", "DOCX", "PNG", "WEBP", "MP3", "XLSX", "AVIF", "ZIP", "PPTX", "SVG", "EPUB", "MSG",
                   "CSV", "MP4", "RAW", "TXT", "FLAC", "ICO", "GIF", "JSON", "MD", "WAV"];
    let w = 0, h = 0, dpr = 1, items = [], color = "#888", accent = "#34be84", running = false, last = 0;
    const pointer = { x: 0.5, y: 0.5 };
    function size() {
      dpr = Math.min(2, window.devicePixelRatio || 1);
      w = canvas.clientWidth; h = canvas.clientHeight;
      canvas.width = w * dpr; canvas.height = h * dpr;
      const n = Math.round(Math.min(34, (w * h) / 42000));
      items = Array.from({ length: n }, (_, i) => ({
        word: words[i % words.length], x: Math.random() * w, y: Math.random() * h,
        z: 0.35 + Math.random() * 0.65, v: 6 + Math.random() * 10, hl: Math.random() < 0.18,
      }));
    }
    function recolor() {
      const cs = getComputedStyle(root);
      color = cs.getPropertyValue("--dim").trim() || "#888";
      accent = cs.getPropertyValue("--accent").trim() || "#34be84";
    }
    function frame(now) {
      if (!running) return;
      const dt = Math.min(0.05, (now - last) / 1000 || 0);
      last = now;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      for (const it of items) {
        it.y -= it.v * it.z * dt;
        if (it.y < -30) { it.y = h + 30; it.x = Math.random() * w; }
        const px = (pointer.x - 0.5) * 40 * it.z, py = (pointer.y - 0.5) * 30 * it.z;
        ctx.globalAlpha = 0.03 + it.z * (it.hl ? 0.12 : 0.06);
        ctx.fillStyle = it.hl ? accent : color;
        ctx.font = `700 ${Math.round(11 + it.z * 13)}px ${getComputedStyle(document.body).fontFamily}`;
        ctx.fillText(it.word, it.x + px, it.y + py);
      }
      requestAnimationFrame(frame);
    }
    function start() { if (!running && !reduce) { running = true; last = performance.now(); requestAnimationFrame(frame); } }
    function stop() { running = false; }
    addEventListener("resize", size);
    addEventListener("pointermove", (e) => { pointer.x = e.clientX / innerWidth; pointer.y = e.clientY / innerHeight; }, { passive: true });
    document.addEventListener("visibilitychange", () => (document.hidden ? stop() : start()));
    size(); recolor();
    if (reduce) { // one still frame
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      for (const it of items) { ctx.globalAlpha = 0.08; ctx.fillStyle = color; ctx.font = "700 16px sans-serif"; ctx.fillText(it.word, it.x, it.y); }
    } else start();
    return { recolor };
  })();

  // ---------------------------------------------------------------- the live picker
  const picker = (() => {
    const stage = $("#stage"), disc = $("#disc"), peek = $("#peek"), toast = $("#toast"), ghost = $("#ghost");
    if (!stage) return null;
    const inner = [
      ["JPG", "everywhere", "Plays nice with every app and site."], ["PNG", "lossless", "Every pixel exactly, transparency kept."],
      ["WEBP", "small, sharp", "Same look at a fraction of the size."], ["PDF", "1 page each", "Ready to print or e-mail."],
      ["AVIF", "smallest", "The newest format: tiny files."], ["Compress", "to a size", "Under 100 KB, 1 MB, or your own limit."],
    ];
    const outer = [
      ["Crop", "4:5, 16:9", "Square, 4:5, 16:9, passport."], ["Resize", "1920 px", "Half, 1920, 1280 or 1080 px."],
      ["Read text", "OCR", "The words in the picture, as text."], ["Turn", "90°", "Left, right or upside down."],
      ["Clean info", "no GPS", "Removes location and camera details."], ["1 PDF", "all pages", "Every picture in one PDF."],
      ["Watermark", "text", "Your text across the middle or a corner."], ["Passport", "photo sheet", "8 photos on a 4x6 print."],
    ];
    const sizes = { JPG: "610 KB", PNG: "3.1 MB", WEBP: "380 KB", PDF: "702 KB", AVIF: "290 KB", Compress: "96 KB" };
    const planets = [];
    function make(list, ring, base) {
      list.forEach(([name, cap, blurb], i) => {
        const el = document.createElement("button");
        el.type = "button";
        el.className = "planet" + (ring === 2 ? " tool" : "");
        el.innerHTML = `${name}<small>${cap}</small>`;
        el.setAttribute("aria-label", `${name}: ${blurb}`);
        stage.appendChild(el); // stage coordinates, like the pointer
        planets.push({ el, name, blurb, ring, a: base + (i / list.length) * Math.PI * 2, s: 1, show: 1 });
        el.addEventListener("click", () => choose(planets.find((p) => p.el === el)));
        el.addEventListener("focus", () => focusOn(planets.find((p) => p.el === el)));
      });
    }
    make(inner, 1, -Math.PI / 2);
    make(outer, 2, -Math.PI / 2 + 0.2);

    let W = 0, cx = 0, cy = 0, r1 = 0, r2 = 0, sz1 = 0, sz2 = 0;
    function measure() {
      W = disc.offsetWidth; // layout size: not affected by the disc's own scale animation
      cx = disc.offsetLeft + W / 2; cy = disc.offsetTop + disc.offsetHeight / 2;
      r1 = W * 0.28; r2 = W * 0.43; sz1 = W * 0.13; sz2 = W * 0.122;
      planets.forEach((p) => p.el.style.setProperty("--size", `${p.ring === 1 ? sz1 : sz2}px`));
    }
    addEventListener("resize", measure);
    measure();

    const ptr = { x: -999, y: -999, real: false, idle: 0 };
    let hot = null, spin = 0, open = 1, script = 0, scriptT = 0, busy = false, visible = true, last = 0;

    stage.addEventListener("pointermove", (e) => {
      const s = stage.getBoundingClientRect();
      ptr.x = e.clientX - s.left; ptr.y = e.clientY - s.top; ptr.real = true; ptr.idle = 0;
      ghost.classList.add("off");
    });
    stage.addEventListener("pointerleave", () => { ptr.real = false; ptr.idle = 0; });

    function pos(p) {
      const r = p.ring === 1 ? r1 : r2;
      const a = p.a + spin * (p.ring === 1 ? 1 : -0.7);
      const k = 0.55 + 0.45 * open;
      return { x: cx + Math.cos(a) * r * k, y: cy + Math.sin(a) * r * k };
    }
    function focusOn(p) {
      if (hot === p) return;
      hot?.el.classList.remove("hot");
      hot = p;
      if (p) {
        p.el.classList.add("hot");
        peek.querySelector("strong").textContent = p.name;
        peek.querySelector("span").textContent = p.blurb;
        peek.classList.add("on");
      } else peek.classList.remove("on");
    }
    function burst(x, y) {
      const r = document.createElement("span");
      r.className = "ripple"; r.style.left = `${x}px`; r.style.top = `${y}px`;
      stage.appendChild(r); setTimeout(() => r.remove(), 800);
      for (let i = 0; i < 8; i++) {
        const s = document.createElement("span"), a = (i / 8) * Math.PI * 2;
        s.className = "spark"; s.style.left = `${x}px`; s.style.top = `${y}px`;
        s.style.setProperty("--dx", `${Math.cos(a) * 46}px`); s.style.setProperty("--dy", `${Math.sin(a) * 46}px`);
        stage.appendChild(s); setTimeout(() => s.remove(), 900);
      }
    }
    function choose(p) {
      if (!p || busy) return;
      busy = true;
      const q = pos(p);
      burst(q.x, q.y);
      const out = p.ring === 1 ? `Holiday${p.name === "Compress" ? " (compressed).jpg" : "." + p.name.toLowerCase()}` : `Holiday (${p.name.toLowerCase()}).jpg`;
      toast.querySelector("strong").textContent = p.ring === 1 && p.name !== "Compress" ? `Saved as ${p.name}` : `${p.name}: done`;
      toast.querySelector("span").textContent = `${out}  ${sizes[p.name] ? "2.4 MB → " + sizes[p.name] : "checked"}`;
      setTimeout(() => toast.classList.add("on"), 250);
      setTimeout(() => { toast.classList.remove("on"); busy = false; }, 3200);
    }
    function keys(down) { $$(".key", stage).forEach((k) => k.classList.toggle("down", down)); }

    // the ghost's little film: tap the keys, the web opens, point at WEBP, click, saved
    const ghostAt = (t) => {
      const target = planets.find((p) => p.name === "WEBP");
      const q = pos(target);
      const start = { x: W * 0.95, y: W * 1.02 };
      const k = Math.min(1, Math.max(0, (t - 1.6) / 1.5));
      const e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
      return { x: start.x + (q.x + 6 - start.x) * e, y: start.y + (q.y + 8 - start.y) * e - Math.sin(Math.PI * e) * 40 };
    };
    function frame(now) {
      const dt = Math.min(0.05, (now - last) / 1000 || 0);
      last = now;
      if (visible) {
        spin += dt * 0.08;
        if (!ptr.real) {
          ptr.idle += dt;
          if (ptr.idle > 1.2) { // the ghost plays when you're not pointing
            scriptT += dt;
            const t = scriptT % 8.5;
            keys(t > 0.2 && t < 0.55);
            open = t < 0.55 ? 0.15 : Math.min(1, open + dt * 2.2);
            disc.style.setProperty("--disc", String(0.82 + 0.18 * open));
            if (t > 6.6) open = Math.max(0.15, open - dt * 1.5);
            const g = ghostAt(t);
            ghost.classList.toggle("off", t < 1.2 || t > 6.4);
            ghost.style.transform = `translate(${g.x}px, ${g.y}px)`;
            ptr.x = g.x; ptr.y = g.y;
            const shot = Math.floor(t / 4.2) % 2 === 1;
            if (shot && script !== Math.floor(scriptT / 8.5)) { script = Math.floor(scriptT / 8.5); choose(planets.find((p) => p.name === "WEBP")); }
          }
        } else { open = Math.min(1, open + dt * 3); disc.style.setProperty("--disc", "1"); }
        // planets: place, and lean toward (grow near) the pointer
        let best = null, bestD = 1e9;
        for (const p of planets) {
          const q = pos(p);
          const d = Math.hypot(ptr.x - q.x, ptr.y - q.y);
          const near = Math.max(0, 1 - d / (W * 0.16));
          const target = 1 + 0.55 * near;
          p.s += (target - p.s) * Math.min(1, dt * 12);
          const lean = 0.12 * near;
          const x = q.x + (ptr.x - q.x) * lean, y = q.y + (ptr.y - q.y) * lean;
          p.el.style.transform = `translate(${x}px, ${y}px) scale(${p.s * (0.4 + 0.6 * open)})`;
          p.el.style.opacity = String(Math.min(1, open * 1.4));
          if (d < bestD) { bestD = d; best = p; }
        }
        focusOn(bestD < W * 0.09 && open > 0.9 ? best : null);
      }
      requestAnimationFrame(frame);
    }
    if (reduce) { // still: the web open, WEBP chosen
      open = 1;
      planets.forEach((p) => { const q = pos(p); p.el.style.transform = `translate(${q.x}px, ${q.y}px)`; });
      ghost.classList.add("off");
      focusOn(planets.find((p) => p.name === "WEBP"));
    } else {
      new IntersectionObserver(([e]) => { visible = e.isIntersecting; }).observe(stage);
      requestAnimationFrame(frame);
    }
    return { measure };
  })();

  // ---------------------------------------------------------------- reveal on scroll, staggered
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
  }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
  $$(".reveal").forEach((el) => {
    const siblings = [...el.parentElement.children].filter((c) => c.classList.contains("reveal"));
    el.style.setProperty("--d", `${Math.min(6, siblings.indexOf(el)) * 0.07}s`);
    io.observe(el);
  });

  // ---------------------------------------------------------------- videos play only while they're on screen
  // (watching where they really are, so the sideways strip works too); less motion: the still picture only
  const playing = new IntersectionObserver((entries) => {
    entries.forEach(({ target: v, isIntersecting }) => {
      if (isIntersecting && !reduce) {
        if (!v.dataset.live) { v.src = mediaSrc(v, "mp4"); v.dataset.live = "1"; }
        v.muted = true;
        v.play().catch(() => {});
      } else if (!isIntersecting && v.dataset.live) v.pause();
    });
  }, { rootMargin: "200px 0px" });
  $$("video.themed").forEach((v) => playing.observe(v));

  // ---------------------------------------------------------------- counters
  const counted = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting) return;
      counted.unobserve(e.target);
      const to = Number(e.target.dataset.to), t0 = performance.now();
      if (reduce) return;
      const step = (now) => {
        const k = Math.min(1, (now - t0) / 1600), v = Math.round(to * (1 - Math.pow(1 - k, 4)));
        e.target.textContent = String(v);
        if (k < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  }, { threshold: 0.6 });
  $$(".count").forEach((el) => counted.observe(el));

  // ---------------------------------------------------------------- the marquee of file types
  const exts = ["HEIC", "JPG", "PNG", "WEBP", "AVIF", "GIF", "BMP", "TIFF", "ICO", "PSD", "SVG", "RAW", "DNG", "PDF", "DOCX",
    "DOC", "ODT", "RTF", "TXT", "XLSX", "XLS", "ODS", "CSV", "PPTX", "PPT", "KEY", "PAGES", "NUMBERS", "JSON", "YAML", "TOML",
    "XML", "MD", "HTML", "EPUB", "MOBI", "FB2", "CBZ", "ZIP", "7Z", "RAR", "ISO", "TAR.GZ", "MP3", "M4A", "WAV", "FLAC", "WMA",
    "OGG", "MP4", "MOV", "MKV", "AVI", "SRT", "VTT", "EML", "MSG", "VCF", "ICS", "GPX", "KML", "GEOJSON", "STL", "OBJ", "GLB",
    "DXF", "TTF", "OTF", "WOFF", "IPYNB", "SQLITE", "QOI", "URL"];
  const fill = (el, list, every) => {
    if (!el) return;
    const html = list.map((x, i) => `<span class="chip${i % every === 0 ? " hl" : ""}">${x}</span>`).join("");
    el.innerHTML = html + html; // twice, for a seamless loop
  };
  fill($("#track-a"), exts.slice(0, 37), 5);
  fill($("#track-b"), exts.slice(37), 4);

  // ---------------------------------------------------------------- the pointer light on cards, magnetic buttons
  $$(".spot").forEach((el) => el.addEventListener("pointermove", (e) => {
    const r = el.getBoundingClientRect();
    el.style.setProperty("--x", `${e.clientX - r.left}px`); el.style.setProperty("--y", `${e.clientY - r.top}px`);
  }));
  if (!reduce && matchMedia("(pointer: fine)").matches) {
    $$(".magnetic").forEach((b) => {
      b.addEventListener("pointermove", (e) => {
        const r = b.getBoundingClientRect();
        b.style.setProperty("--mx", `${(e.clientX - r.left - r.width / 2) * 0.18}px`);
        b.style.setProperty("--my", `${(e.clientY - r.top - r.height / 2) * 0.28}px`);
      });
      b.addEventListener("pointerleave", () => { b.style.setProperty("--mx", "0px"); b.style.setProperty("--my", "0px"); });
    });
  }

  // ---------------------------------------------------------------- the processor gauge
  const arc = $("#gauge-arc"), num = $("#gauge-num"), C = 2 * Math.PI * 80;
  $$(".seg button").forEach((b) => b.addEventListener("click", () => {
    $$(".seg button").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
    const v = Number(b.dataset.cpu);
    arc.style.strokeDashoffset = String(C * (1 - v / 100));
    num.textContent = `${v}%`;
  }));

  // ---------------------------------------------------------------- download: the newest release, straight from GitHub
  (async () => {
    const show = (rel) => {
      const setup = rel.assets.find((a) => /^Deskvert-Setup-.*\.exe$/.test(a.name))
        || rel.assets.find((a) => /^Tapshift-Setup-.*\.exe$/.test(a.name)); // releases from before the rename
      const zip = rel.assets.find((a) => /portable\.zip$/.test(a.name));
      if (setup) $$(".js-download").forEach((a) => (a.href = setup.browser_download_url));
      if (zip) $("#dl-portable").href = zip.browser_download_url;
      const mb = setup ? ` · ${(setup.size / 1048576).toFixed(1)} MB` : "";
      $("#dl-meta").textContent = `Version ${rel.tag_name.replace(/^v/, "")}${mb}`;
      const sha = setup?.digest?.replace(/^sha256:/, "");
      if (sha) {
        const btn = $("#dl-sha");
        btn.hidden = false;
        btn.title = sha;
        btn.addEventListener("click", async () => {
          try { await navigator.clipboard.writeText(sha); btn.querySelector("span").textContent = "SHA-256 copied"; }
          catch (e) { btn.querySelector("span").textContent = sha.slice(0, 16) + "..."; }
        });
      }
    };
    try {
      const cached = sessionStorage.getItem("deskvert-release");
      if (cached) return show(JSON.parse(cached));
    } catch (e) { /* storage blocked: just ask GitHub */ }
    try {
      const r = await fetch("https://api.github.com/repos/syedtaj7/DeskVert/releases/latest", { headers: { Accept: "application/vnd.github+json" } });
      if (!r.ok) throw new Error(r.status);
      const rel = await r.json();
      try { sessionStorage.setItem("deskvert-release", JSON.stringify({ tag_name: rel.tag_name, assets: rel.assets })); } catch (e) { /* fine */ }
      show(rel);
    } catch (e) {
      $("#dl-meta").textContent = "Latest release on GitHub"; // links already point at the releases page
    }
  })();

  applyTheme();
})();
