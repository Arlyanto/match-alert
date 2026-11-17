/* ============================================================================
 * collect_member_ids.js — ambil Google user ID member Space (buat mention)
 * ============================================================================
 * Dipakai kalau Chat API balas 403 (bot belum jadi member space).
 *
 * CARA PAKAI (1 menit, tanpa ubah setting GCP):
 *   1. Buka https://chat.google.com di Chrome, login akun Vidio.
 *   2. Buka Space tujuan alert (atau space lain yang berisi bot).
 *   3. Tekan F12 -> tab Console -> tempel seluruh isi file ini -> Enter.
 *      (kalau Chrome blokir paste: ketik "allow pasting" lalu Enter)
 *   4. Klik nama Space -> Space settings -> Members, tunggu daftar member muncul.
 *   5. Buka Console lagi: hasilnya otomatis tersimpan di variabel
 *      window.__MEMBER_IDS dan sudah di-copy ke clipboard sebagai JSON.
 *      Tempel ke file member_ids.json, lalu jalankan:
 *          python fetch_google_ids.py --from-file member_ids.json
 *
 * Catatan: snippet ini cuma MEMBACA data member yang sudah tampil di browser
 * sendiri; tidak mengirim apa pun ke mana-mana.
 * ========================================================================== */

(() => {
  const found = new Map(); // id -> {google_id, name, email}
  const EMAIL = /[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/i;
  const USER_ID = /users\/(\d{15,25})/g;

  function add(id, name, email) {
    if (!id) return;
    const cur = found.get(id) || { google_id: id, name: "", email: "" };
    if (name && (!cur.name || name.length < cur.name.length)) cur.name = name;
    if (email && !cur.email) cur.email = email;
    found.set(id, cur);
  }

  // --- 1. Scan DOM: baris member yang sedang tampil -------------------------
  function scanDom() {
    document.querySelectorAll("[data-member-id], [data-user-id]").forEach((el) => {
      const id = el.getAttribute("data-member-id") || el.getAttribute("data-user-id");
      if (!id || !/^\d{15,25}$/.test(id)) return;
      const text = (el.innerText || "").trim();
      const mail = text.match(EMAIL);
      const name = text.split("\n").map((s) => s.trim()).filter(Boolean)[0] || "";
      add(id, name.replace(EMAIL, "").trim(), mail ? mail[0] : "");
    });

    // fallback: atribut lain yang menyimpan "users/<id>"
    document.querySelectorAll("*").forEach((el) => {
      for (const attr of el.attributes || []) {
        if (!attr.value || attr.value.length > 4000) continue;
        if (!attr.value.includes("users/")) continue;
        const re = new RegExp(USER_ID.source, "g");
        let m;
        while ((m = re.exec(attr.value))) {
          const text = (el.innerText || "").trim();
          const mail = text.match(EMAIL);
          add(m[1], text.split("\n")[0].trim(), mail ? mail[0] : "");
        }
      }
    });
  }

  // --- 2. Scan payload RPC (paling akurat: bawa name + email) --------------
  function scanPayload(text) {
    if (!text || text.length > 8_000_000) return;
    let m;
    const re = new RegExp(USER_ID.source, "g");
    while ((m = re.exec(text))) {
      const id = m[1];
      // ambil jendela sekitar id untuk cari email & nama
      const ctx = text.slice(Math.max(0, m.index - 400), m.index + 400);
      const mail = ctx.match(EMAIL);
      let name = "";
      // kandidat nama: string berhuruf, mengandung spasi, bukan key/url/email
      const strings = ctx.match(/"([^"\\]{3,60})"/g) || [];
      for (const s of strings) {
        const v = s.slice(1, -1).trim();
        if (
          /^[A-Z][A-Za-z.'-]+(\s+[A-Z][A-Za-z.'-]*){1,3}$/.test(v) &&
          !EMAIL.test(v) &&
          !/^(Space|Members|Google|Chat|People|https?)/.test(v)
        ) {
          name = v;
          break;
        }
      }
      add(id, name, mail ? mail[0] : "");
    }
  }

  // --- hook fetch ------------------------------------------------------------
  const origFetch = window.fetch;
  window.fetch = async function (...args) {
    const res = await origFetch.apply(this, args);
    try {
      const url = typeof args[0] === "string" ? args[0] : (args[0] && args[0].url) || "";
      if (/chat\.google\.com|batchexecute|rpc/i.test(url)) {
        res.clone().text().then(scanPayload).catch(() => {});
      }
    } catch (e) {}
    return res;
  };

  // --- hook XHR --------------------------------------------------------------
  const origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.addEventListener("load", () => {
      try {
        if (typeof this.responseText === "string") scanPayload(this.responseText);
      } catch (e) {}
    });
    return origOpen.call(this, method, url, ...rest);
  };

  // --- hasil ----------------------------------------------------------------
  window.__MEMBER_IDS = [];
  window.__printMemberIds = () => {
    scanDom();
    window.__MEMBER_IDS = [...found.values()].sort((a, b) =>
      (a.name || a.google_id).localeCompare(b.name || b.google_id)
    );
    console.table(window.__MEMBER_IDS);
    const json = JSON.stringify(window.__MEMBER_IDS, null, 2);
    try {
      copy(json); // Chrome console helper
      console.log("%c✅ JSON sudah di-copy ke clipboard.", "color:#0a0;font-weight:bold");
    } catch (e) {
      console.log("Copy manual:\n" + json);
    }
    return json;
  };

  console.log(
    "%c[Siap] Buka Space settings → Members, tunggu daftar member muncul, " +
      "lalu jalankan: __printMemberIds()",
    "color:#06c;font-weight:bold"
  );
})();
