(function () {
  "use strict";

  // Used only if assets/data/youtube.js is missing or broken.
  // Refresh the real data with: python3 tools/update_youtube.py
  var FALLBACK = {
    channels: [
      { title: "My Village Show", url: "https://www.youtube.com/@MyVillageShow", subscribers: "3.15M", videos: "562", avatar: "assets/img/logo.png" }
    ],
    videos: [
      { id: "rsg9cfRxASE", title: "Gangavva Lockdown Incharge | My Village Show Comedy | 4K" },
      { id: "MZ3y2vKXuyo", title: "Lock Down lo Love Marriage | Gangavva Lock Down Incharge part -2" }
    ],
    shorts: []
  };

  var data = window.MVS_YT && window.MVS_YT.channels && window.MVS_YT.channels.length ? window.MVS_YT : FALLBACK;
  var FALLBACK_IMG = "assets/img/village.jpg";

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") node.textContent = attrs[k];
      else if (k === "class") node.className = attrs[k];
      else node.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }

  // Try progressively smaller YouTube thumbnails, then a local image, so nothing ever shows broken.
  function thumb(img, id, sizes) {
    var list = (sizes || ["maxresdefault", "hqdefault"]).map(function (s) { return "https://i.ytimg.com/vi/" + id + "/" + s + ".jpg"; });
    list.push(FALLBACK_IMG);
    var i = 0;
    img.onerror = function () { if (++i < list.length) img.src = list[i]; };
    // maxresdefault can "succeed" with a 120px grey placeholder when no HD thumbnail exists.
    img.onload = function () { if (img.naturalWidth <= 120 && i < list.length - 1) img.src = list[++i]; };
    img.src = list[0];
    return img;
  }

  function embed(id, title) {
    return el("iframe", {
      src: "https://www.youtube-nocookie.com/embed/" + encodeURIComponent(id) + "?autoplay=1&rel=0",
      title: title || "YouTube video",
      allow: "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture",
      allowfullscreen: ""
    });
  }

  // "3.15M" -> 3150000, "457K" -> 457000
  function parseCount(s) {
    var m = String(s || "").replace(/,/g, "").match(/([\d.]+)\s*([KMB])?/i);
    if (!m) return 0;
    return parseFloat(m[1]) * ({ K: 1e3, M: 1e6, B: 1e9 }[(m[2] || "").toUpperCase()] || 1);
  }
  function formatBig(n) {
    return n >= 1e9 ? (Math.floor(n / 1e8) / 10) + "B" : formatCount(n);
  }
  function formatCount(n) {
    if (n >= 1e6) return (Math.floor(n / 1e5) / 10) + "M";
    if (n >= 1e3) return Math.floor(n / 1e3) + "K";
    return String(n);
  }
  function timeAgo(iso) {
    var d = new Date(iso);
    if (isNaN(d)) return "";
    var days = Math.floor((Date.now() - d) / 864e5);
    if (days < 1) return "Today";
    if (days === 1) return "Yesterday";
    if (days < 30) return days + " days ago";
    var months = Math.floor(days / 30), years = Math.floor(days / 365);
    if (days < 365) return months === 1 ? "1 month ago" : months + " months ago";
    return years === 1 ? "1 year ago" : years + " years ago";
  }
  function cleanTitle(t) {
    // Drop hashtags and trailing "| My Village Show ..." credits so titles fit cards.
    return String(t || "").replace(/#\S+/g, "").split("|").slice(0, 2).join("|").replace(/\s+/g, " ").trim();
  }

  /* ---------- Stats ---------- */
  function renderStats() {
    var ch = data.channels;
    var subs = ch.reduce(function (a, c) { return a + parseCount(c.subscribers); }, 0);
    var vids = ch.reduce(function (a, c) { return a + parseCount(c.videos); }, 0);
    function set(id, text) { var n = $(id); if (n) n.textContent = text; }
    if (subs) set("#stat-subs", formatCount(subs) + "+");
    if (vids) set("#stat-videos", (Math.floor(vids / 100) * 100).toLocaleString("en-IN") + "+");
    set("#stat-channels", ch.length);
    // Views, from each channel's YouTube About page
    var views = ch.reduce(function (a, c) { return a + (c.views || 0); }, 0);
    if (ch[0] && ch[0].views) set("#stat-views", formatBig(ch[0].views) + "+");
    if (views) set("#fact-views", formatBig(views) + "+");
    if (subs) set("#fact-subs", formatCount(subs) + "+");
    var words = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];
    set("#about-channels", words[ch.length] || ch.length);
  }

  /* ---------- Story film (YouTube Originals Creator Spotlight) ---------- */
  function initStory() {
    var film = $("#story-film");
    $("#story-play").addEventListener("click", function () {
      film.appendChild(embed("ytO4s4ZrTMw", "Creator Spotlight: My Village Show"));
      film.classList.add("playing");
    });
  }

  function shortViews(n) {
    return n >= 1e5 ? formatCount(n) : n.toLocaleString("en-IN");
  }
  function videoMeta(v) {
    return [timeAgo(v.published), v.views ? shortViews(v.views) + " views" : ""].filter(Boolean).join(" · ");
  }

  /* ---------- Videos ---------- */
  function renderVideos() {
    var videos = (data.videos && data.videos.length ? data.videos : FALLBACK.videos).slice(0, 6);
    var player = $("#player"), list = $("#playlist"), more = $(".pl-more", list);

    function load(v, autoplay) {
      $$(".pl-item", list).forEach(function (b) { b.classList.toggle("active", b.dataset.id === v.id); });
      player.classList.remove("playing");
      $$("iframe", player).forEach(function (f) { f.remove(); });
      $("#player-title").textContent = cleanTitle(v.title);
      $("#player-meta").textContent = videoMeta(v);
      thumb($("#player-thumb"), v.id);
      player.dataset.id = v.id;
      player.dataset.title = v.title;
      if (autoplay) play();
    }
    function play() {
      if (player.classList.contains("playing")) return;
      player.appendChild(embed(player.dataset.id, player.dataset.title));
      player.classList.add("playing");
    }
    function playAndShow(v) {
      load(v, true);
      player.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    videos.forEach(function (v) {
      var meta = videoMeta(v);
      var btn = el("button", { class: "pl-item", type: "button" }, [
        el("span", { class: "pl-thumb" }, [thumb(el("img", { alt: "", loading: "lazy" }), v.id, ["mqdefault"])]),
        el("span", {}, [el("b", { text: cleanTitle(v.title) }), meta ? el("small", { text: meta }) : null])
      ]);
      btn.dataset.id = v.id;
      btn.addEventListener("click", function () { playAndShow(v); });
      list.insertBefore(btn, more);
    });

    $("#player-play").addEventListener("click", play);
    load(videos[0], false);

    // Hero "New episode" card
    var now = $("#now-card");
    thumb($("#now-thumb"), videos[0].id, ["mqdefault"]);
    $("#now-title").textContent = cleanTitle(videos[0].title);
    $("#now-meta").textContent = videoMeta(videos[0]);
    now.addEventListener("click", function () { playAndShow(videos[0]); });
    now.hidden = false;

    // Top 10 by views across episodes and shorts; shorts play in place, episodes in the main player
    var all = (data.videos || []).concat(data.shorts || []).filter(function (v) { return v.views; });
    all.sort(function (a, b) { return b.views - a.views; });
    var top = all.slice(0, 10), rail = $("#top10");
    if (top.length < 3) return;
    top.forEach(function (v, i) {
      var poster = el("span", { class: "top-poster" }, [
        thumb(el("img", { alt: "", loading: "lazy" }), v.id, v.short ? ["oardefault", "hqdefault"] : ["maxresdefault", "hqdefault"]),
        el("span", {}, [document.createTextNode(cleanTitle(v.title)), el("small", { text: shortViews(v.views) + " views" })])
      ]);
      var item = el("button", { class: "top-item", type: "button", "aria-label": "Play #" + (i + 1) + ": " + cleanTitle(v.title) }, [
        el("span", { class: "rank", text: String(i + 1), "aria-hidden": "true" }), poster
      ]);
      item.addEventListener("click", function () {
        if (!v.short) return playAndShow(v);
        if (item.classList.contains("playing")) return;
        poster.appendChild(embed(v.id, v.title));
        item.classList.add("playing");
      });
      rail.appendChild(item);
    });
    $("#top-wrap").hidden = false;
  }

  function renderShorts() {
    var shorts = (data.shorts || []).slice(0, 12);
    if (!shorts.length) return;
    var wrap = $("#shorts");
    shorts.forEach(function (s) {
      var card = el("button", { class: "short", type: "button", "aria-label": "Play short: " + cleanTitle(s.title) }, [
        thumb(el("img", { alt: "", loading: "lazy" }), s.id, ["oardefault", "hqdefault"]),
        el("span", { text: cleanTitle(s.title) })
      ]);
      card.addEventListener("click", function () {
        if (card.classList.contains("playing")) return;
        $("img", card).replaceWith(embed(s.id, s.title));
        card.classList.add("playing");
      });
      wrap.appendChild(card);
    });
    $("#shorts-wrap").hidden = false;
  }

  /* ---------- Podcast ---------- */
  // "2h 38m" / "58 min"
  function duration(sec) {
    var m = Math.round((sec || 0) / 60);
    return m >= 60 ? Math.floor(m / 60) + "h " + (m % 60) + "m" : m + " min";
  }

  function renderPodcasts() {
    var eps = (data.podcasts || []).filter(function (p) { return p.id; });
    if (!eps.length) return;
    var player = $("#pod-player"), top = $("#pod-top"), latestRail = $("#pod-latest");
    var popular = eps.slice().sort(function (a, b) { return b.views - a.views; });
    var latest = eps.slice().sort(function (a, b) { return new Date(b.published) - new Date(a.published); });
    var NEW_DAYS = 45;

    // Episodes come from all our channels; name the channel when it isn't the podcast's usual home
    var counts = {};
    eps.forEach(function (p) { if (p.channel) counts[p.channel] = (counts[p.channel] || 0) + 1; });
    var home = Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; })[0];
    function fromOther(p) { return p.channel && p.channel !== home ? p.channel : ""; }

    function meta(p) {
      return [fromOther(p), timeAgo(p.published), p.views ? shortViews(p.views) + " views" : "", p.seconds ? duration(p.seconds) : ""].filter(Boolean).join(" · ");
    }
    function isNew(p) { return (Date.now() - new Date(p.published)) / 864e5 < NEW_DAYS; }

    function load(p, badge, autoplay) {
      $$(".pod-item, #pod-latest .pl-item").forEach(function (b) { b.classList.toggle("active", b.dataset.id === p.id); });
      player.classList.remove("playing");
      $$("iframe", player).forEach(function (f) { f.remove(); });
      thumb($("#pod-thumb"), p.id);
      $("#pod-title").textContent = cleanTitle(p.title);
      $("#pod-meta").textContent = meta(p);
      $("#pod-badge").textContent = badge;
      player.dataset.id = p.id;
      player.dataset.title = p.title;
      if (autoplay) play();
    }
    function play() {
      if (player.classList.contains("playing")) return;
      player.appendChild(embed(player.dataset.id, player.dataset.title));
      player.classList.add("playing");
    }
    function playAndShow(p, badge) {
      load(p, badge, true);
      player.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    // Most played: top 5 by views
    popular.slice(0, 5).forEach(function (p, i) {
      var btn = el("button", { class: "pod-item", type: "button" }, [
        el("span", { class: "pod-rank", text: String(i + 1), "aria-hidden": "true" }),
        thumb(el("img", { alt: "", loading: "lazy" }), p.id, ["mqdefault"]),
        el("span", {}, [el("b", { text: cleanTitle(p.title) }), el("small", { text: [fromOther(p), shortViews(p.views) + " views", p.seconds ? duration(p.seconds) : ""].filter(Boolean).join(" · ") })])
      ]);
      btn.dataset.id = p.id;
      btn.addEventListener("click", function () { playAndShow(p, "#" + (i + 1) + " most played"); });
      top.appendChild(el("li", {}, [btn]));
    });

    // Latest episodes: newest first
    latest.slice(0, 10).forEach(function (p) {
      var badges = [thumb(el("img", { alt: "", loading: "lazy" }), p.id, ["mqdefault"])];
      if (p.seconds) badges.push(el("span", { class: "pod-len", text: duration(p.seconds) }));
      if (isNew(p)) badges.push(el("span", { class: "pod-new", text: "NEW" }));
      var btn = el("button", { class: "pl-item", type: "button" }, [
        el("span", { class: "pl-thumb" }, badges),
        el("span", {}, [el("b", { text: cleanTitle(p.title) }), el("small", { text: meta(p) })])
      ]);
      btn.dataset.id = p.id;
      btn.addEventListener("click", function () { playAndShow(p, p === latest[0] ? (isNew(p) ? "New episode" : "Latest episode") : "Podcast"); });
      latestRail.appendChild(btn);
    });

    $("#pod-play").addEventListener("click", play);
    // Like "Latest from the village": the newest episode is always featured
    load(latest[0], isNew(latest[0]) ? "New episode" : "Latest episode", false);
    $("#podcast").hidden = false;
  }

  /* ---------- Talk with Celebrity ---------- */
  function renderCelebrity() {
    // A video never appears in both sections: podcast episodes stay in Podcast only
    var podIds = (data.podcasts || []).map(function (p) { return p.id; });
    var talks = (data.celebrity || []).filter(function (t) { return t.id && podIds.indexOf(t.id) < 0; });
    if (!talks.length) return;
    var player = $("#cel-player");
    talks.sort(function (a, b) { return b.views - a.views; });

    function label(t) { return { official: "Official", leader: "Leader" }[t.kind] || ""; }
    function meta(t) {
      return [label(t), t.channel, t.views ? shortViews(t.views) + " views" : "", t.seconds ? duration(t.seconds) : ""].filter(Boolean).join(" · ");
    }
    function load(t, badge, autoplay) {
      $$("#cel-top .pod-item, #cel-all .pl-item").forEach(function (b) { b.classList.toggle("active", b.dataset.id === t.id); });
      player.classList.remove("playing");
      $$("iframe", player).forEach(function (f) { f.remove(); });
      thumb($("#cel-thumb"), t.id);
      $("#cel-title").textContent = cleanTitle(t.title);
      $("#cel-meta").textContent = meta(t);
      $("#cel-badge").textContent = badge;
      player.dataset.id = t.id;
      player.dataset.title = t.title;
      if (autoplay) play();
    }
    function play() {
      if (player.classList.contains("playing")) return;
      player.appendChild(embed(player.dataset.id, player.dataset.title));
      player.classList.add("playing");
    }
    function playAndShow(t, badge) {
      load(t, badge, true);
      player.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    talks.slice(0, 5).forEach(function (t, i) {
      var btn = el("button", { class: "pod-item", type: "button" }, [
        el("span", { class: "pod-rank", text: String(i + 1), "aria-hidden": "true" }),
        thumb(el("img", { alt: "", loading: "lazy" }), t.id, ["mqdefault"]),
        el("span", {}, [el("b", { text: cleanTitle(t.title) }), el("small", { text: [t.channel, shortViews(t.views) + " views"].join(" · ") })])
      ]);
      btn.dataset.id = t.id;
      btn.addEventListener("click", function () { playAndShow(t, "#" + (i + 1) + " most watched"); });
      $("#cel-top").appendChild(el("li", {}, [btn]));
    });

    talks.forEach(function (t) {
      var inner = [thumb(el("img", { alt: "", loading: "lazy" }), t.id, ["mqdefault"])];
      if (t.seconds) inner.push(el("span", { class: "pod-len", text: duration(t.seconds) }));
      if (label(t)) inner.push(el("span", { class: "cel-kind", text: label(t) }));
      var btn = el("button", { class: "pl-item", type: "button" }, [
        el("span", { class: "pl-thumb" }, inner),
        el("span", {}, [el("b", { text: cleanTitle(t.title) }), el("small", { text: [t.channel, t.views ? shortViews(t.views) + " views" : ""].filter(Boolean).join(" · ") })])
      ]);
      btn.dataset.id = t.id;
      btn.addEventListener("click", function () { playAndShow(t, label(t) || "Celebrity talk"); });
      $("#cel-all").appendChild(btn);
    });

    $("#cel-play").addEventListener("click", play);
    load(talks[0], "#1 most watched", false);
    $("#celebrity").hidden = false;
  }

  /* ---------- Channels ---------- */
  function renderChannels() {
    var list = $("#channels-list");
    list.textContent = "";
    var max = Math.max.apply(null, data.channels.map(function (c) { return parseCount(c.subscribers); }));
    data.channels.forEach(function (c, i) {
      var title = el("h3", { text: c.title });
      if (i === 0) title.appendChild(el("span", { class: "tag", text: "Main" }));
      var sub = el("p", { class: "ch-sub" });
      if (c.subscribers) { sub.appendChild(el("b", { text: c.subscribers })); sub.appendChild(document.createTextNode(" subscribers")); }
      else sub.textContent = "Watch on YouTube";
      if (c.videos) sub.appendChild(document.createTextNode(" · " + c.videos + " videos"));

      var img = el("img", { src: c.avatar || "assets/img/logo.png", alt: "", loading: "lazy" });
      img.onerror = function () { img.onerror = null; img.src = "assets/img/logo.png"; };

      // Audience bar, relative to the biggest channel
      var bar = null;
      if (max && c.subscribers) {
        bar = el("span", { class: "ch-bar", "aria-hidden": "true" }, [el("i")]);
        bar.firstChild.style.width = Math.max(4, parseCount(c.subscribers) / max * 100) + "%";
      }

      list.appendChild(el("a", { class: "ch reveal" + (i === 0 ? " ch-main" : ""), href: c.url, target: "_blank", rel: "noopener" }, [
        img, el("div", {}, [title, sub, bar]), el("span", { class: "ch-go", text: "↗", "aria-hidden": "true" })
      ]));
    });
    if (data.updated) {
      var d = new Date(data.updated);
      if (!isNaN(d)) $("#yt-updated").textContent = "YouTube stats as of " + d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
    }
  }

  /* ---------- Nav ---------- */
  function initNav() {
    var nav = $("#nav");
    function onScroll() { nav.classList.toggle("scrolled", window.scrollY > 40); }
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();

    $("#burger").addEventListener("click", function () {
      var open = document.body.classList.toggle("menu-open");
      this.setAttribute("aria-expanded", open);
      if (open) nav.classList.add("scrolled"); else onScroll();
    });
    $$("#links a").forEach(function (a) {
      a.addEventListener("click", function () { document.body.classList.remove("menu-open"); onScroll(); });
    });

    if (!("IntersectionObserver" in window)) return;
    var links = {};
    $$("#links a").forEach(function (a) { links[a.getAttribute("href").slice(1)] = a; });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting && links[e.target.id]) {
          $$("#links a").forEach(function (a) { a.classList.remove("active"); });
          links[e.target.id].classList.add("active");
        }
      });
    }, { rootMargin: "-45% 0px -50% 0px" });
    $$("main section[id]").forEach(function (s) { io.observe(s); });
  }

  /* ---------- Rail arrows ---------- */
  function initRails() {
    $$(".row").forEach(function (row) {
      var rail = $(".rail", row), btns = $$(".rail-btn", row);
      if (!rail || !btns.length) return;
      function update() {
        var max = rail.scrollWidth - rail.clientWidth - 2;
        btns[0].disabled = rail.scrollLeft <= 2;
        btns[1].disabled = rail.scrollLeft >= max;
      }
      btns.forEach(function (b) {
        b.addEventListener("click", function () {
          rail.scrollBy({ left: Number(b.dataset.dir) * rail.clientWidth * 0.9, behavior: "smooth" });
        });
      });
      rail.addEventListener("scroll", update, { passive: true });
      window.addEventListener("resize", update);
      update();
    });
  }

  /* ---------- Motion: progress bar, parallax, timeline, floating buttons ---------- */
  var calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function initScrollEffects() {
    var bar = $("#progress"), hero = $(".hero"), heroBg = $(".hero-bg"), totop = $("#totop"), mbar = $("#mbar");
    var timeline = $(".timeline"), steps = timeline ? $$("li", timeline) : [];
    var ticking = false;

    function update() {
      ticking = false;
      var y = window.scrollY, vh = window.innerHeight;
      var max = document.documentElement.scrollHeight - vh;
      bar.style.transform = "scaleX(" + (max > 0 ? y / max : 0) + ")";

      var pastHero = y > hero.offsetHeight * 0.6;
      totop.classList.toggle("show", pastHero);
      mbar.classList.toggle("show", pastHero);

      if (!calm && y < hero.offsetHeight) heroBg.style.setProperty("--py", (y * 0.25).toFixed(1) + "px");

      if (timeline) {
        // Fill the line up to the middle of the screen and light up the steps it has passed
        var r = timeline.getBoundingClientRect(), mid = vh * 0.55;
        var p = Math.min(1, Math.max(0, (mid - r.top) / r.height));
        timeline.style.setProperty("--p", p.toFixed(3));
        steps.forEach(function (li) { li.classList.toggle("on", li.getBoundingClientRect().top < mid); });
      }
    }
    function onScroll() { if (!ticking) { ticking = true; window.requestAnimationFrame(update); } }
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    update();
  }

  /* ---------- Stats count up when they come into view ---------- */
  function initCounters() {
    if (calm || !("IntersectionObserver" in window)) return;
    function run(node) {
      var m = node.textContent.trim().match(/^([\d.,]+)(.*)$/);
      if (!m) return;
      var raw = m[1], suffix = m[2], target = parseFloat(raw.replace(/,/g, ""));
      var decimals = (raw.split(".")[1] || "").length, commas = raw.indexOf(",") > -1;
      var start = null, dur = 1600;
      function frame(t) {
        if (!start) start = t;
        var k = Math.min(1, (t - start) / dur), eased = 1 - Math.pow(1 - k, 3);
        var v = target * eased;
        node.textContent = (commas ? Math.round(v).toLocaleString("en-IN") : v.toFixed(decimals)) + suffix;
        if (k < 1) window.requestAnimationFrame(frame); else node.textContent = raw + suffix;
      }
      window.requestAnimationFrame(frame);
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) { run(e.target); io.unobserve(e.target); } });
    }, { threshold: 0.6 });
    $$(".stats strong").forEach(function (n) { io.observe(n); });
  }

  /* ---------- Cursor spotlight on cards ---------- */
  function initSpotlight() {
    if (!window.matchMedia || !window.matchMedia("(hover: hover)").matches) return;
    $$(".pillar, .quote-card, .ch, .headlines, .facts div, .impact-card").forEach(function (card) {
      card.addEventListener("pointermove", function (e) {
        var r = card.getBoundingClientRect();
        card.style.setProperty("--mx", (e.clientX - r.left) + "px");
        card.style.setProperty("--my", (e.clientY - r.top) + "px");
      });
      card.addEventListener("pointerleave", function () { card.style.removeProperty("--mx"); card.style.removeProperty("--my"); });
    });
  }

  /* ---------- Scroll reveal ---------- */
  function initReveal() {
    var items = $$(".reveal");
    if (!("IntersectionObserver" in window)) { items.forEach(function (n) { n.classList.add("in"); }); return; }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
    items.forEach(function (n, i) {
      n.style.transitionDelay = (i % 4) * 70 + "ms";
      io.observe(n);
    });
  }

  /* ---------- Media lightbox ---------- */
  function initLightbox() {
    var box = $("#lightbox"), img = $("img", box);
    function close() { box.hidden = true; document.body.style.overflow = ""; }
    $$(".press-item").forEach(function (b) {
      b.addEventListener("click", function () {
        img.src = $("img", b).src;
        box.hidden = false;
        document.body.style.overflow = "hidden";
        $(".lb-close", box).focus();
      });
    });
    box.addEventListener("click", function (e) { if (e.target !== img) close(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !box.hidden) close(); });
  }

  /* ---------- Contact ---------- */
  // No backend: the form opens the visitor's email app with the message filled in.
  function initContact() {
    var form = $("#contact-form");
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var f = form.elements;
      var body = f.message.value + "\n\n— " + f.name.value + " (" + f.email.value + ")";
      window.location.href = "mailto:srikanth@myvillageshow.in?subject=" +
        encodeURIComponent("[Website] " + f.subject.value + " – " + f.name.value) + "&body=" + encodeURIComponent(body);
      var note = $(".form-note", form) || form.appendChild(el("p", { class: "form-note" }));
      note.textContent = "Your email app should open with the message ready to send. If it doesn't, write to srikanth@myvillageshow.in.";
    });
  }

  function safe(fn) { try { fn(); } catch (err) { if (window.console) console.error(err); } }

  safe(renderStats);
  safe(renderVideos);
  safe(renderShorts);
  safe(renderPodcasts);
  safe(renderCelebrity);
  safe(renderChannels);
  safe(initStory);
  safe(initRails);
  safe(initNav);
  safe(initReveal);
  safe(initScrollEffects);
  safe(initCounters);
  safe(initSpotlight);
  safe(initLightbox);
  safe(initContact);
  $("#year").textContent = new Date().getFullYear();
  window.MVS_READY = true;
})();
