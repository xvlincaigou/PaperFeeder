// Canonical Cloudflare Worker for web feedback viewer and feedback capture.
// Routes:
// - GET /run?run_id=<run_id>
// - GET /feedback?t=<signed_token>
// Env bindings:
// - DB (D1 database)
// - FEEDBACK_LINK_SIGNING_SECRET (secret text)

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function b64urlToBytes(s) {
  const pad = "=".repeat((4 - (s.length % 4)) % 4);
  const base64 = (s + pad).replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(base64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function bytesToHex(bytes) {
  return Array.from(bytes).map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Light, mobile-first page shell (errors + small fragments only). */
function viewerShell(title, innerHtml, status = 200) {
  const page = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <meta name="color-scheme" content="light"/>
  <title>${title}</title>
  <style>
    :root { color-scheme: light; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      font-size: 16px;
      line-height: 1.55;
      color: #0f172a;
      background: linear-gradient(180deg, #f0f7ff 0%, #f8fafc 40%, #eef2f7 100%);
      padding: max(0px, env(safe-area-inset-top)) max(0px, env(safe-area-inset-right)) max(0px, env(safe-area-inset-bottom)) max(0px, env(safe-area-inset-left));
    }
    .wrap {
      max-width: min(36rem, 100%);
      margin: 0 auto;
    }
    .card {
      background: #fff;
      border-radius: 14px;
      padding: 8px 8px;
      box-shadow: 0 4px 24px rgba(15, 23, 42, 0.08);
      border: 1px solid rgba(148, 163, 184, 0.35);
    }
    h1 { font-size: 1.15rem; font-weight: 700; margin: 0 0 10px; color: #0f172a; }
    p { margin: 0 0 12px; color: #334155; font-size: 0.95rem; }
    p:last-child { margin-bottom: 0; }
    code { font-size: 0.85em; background: #f1f5f9; padding: 2px 6px; border-radius: 6px; word-break: break-all; }
    a {
      color: #2563eb;
      font-weight: 600;
      text-decoration: none;
    }
    a:hover { text-decoration: underline; }
    .muted { font-size: 0.88rem; color: #64748b; }
    .btn {
      display: inline-block;
      margin-top: 14px;
      padding: 10px 16px;
      background: #2563eb;
      color: #fff !important;
      border-radius: 10px;
      font-size: 0.95rem;
    }
    .btn:hover { filter: brightness(1.05); text-decoration: none; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">${innerHtml}</div>
  </div>
</body>
</html>`;
  return new Response(page, {
    status,
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}

/** Force light, readable theme over LLM dark inline styles when serving stored digest HTML. */
function injectViewerLightTheme(html) {
  const patch = `<style id="pf-viewer-light-theme">
:root{color-scheme:light!important}
html{background:#e2e8f0!important}
body.pf-viewer-light{background:linear-gradient(180deg,#e8f2fc,#f1f5f9)!important;color:#0f172a!important}
body.pf-viewer-light .container{background:#fff!important;color:inherit!important}
body.pf-viewer-light .header{background:linear-gradient(135deg,#f0f9ff,#e0f2fe,#dbeafe)!important;color:#0c4a6e!important}
body.pf-viewer-light .header h1{color:#0369a1!important}
body.pf-viewer-light .header .meta,body.pf-viewer-light .header .persona{color:#0e7490!important}
body.pf-viewer-light .footer{background:#f8fafc!important;color:#64748b!important}
body.pf-viewer-light .content{background:#fff!important;color:#1e293b!important}
body.pf-viewer-light .content p,body.pf-viewer-light .content li,body.pf-viewer-light .content td,body.pf-viewer-light .content th,
body.pf-viewer-light .content h1,body.pf-viewer-light .content h2,body.pf-viewer-light .content h3,body.pf-viewer-light .content h4,body.pf-viewer-light .content h5{color:#334155!important}
body.pf-viewer-light .content a:not(.pf-feedback-btn){color:#2563eb!important}
body.pf-viewer-light .content div[style],body.pf-viewer-light .content section[style]{background:#f8fafc!important;color:#1e293b!important;border:1px solid #e2e8f0!important}
body.pf-viewer-light .pf-feedback-btn.positive{color:#1f6a30!important;background:#eff9f2!important}
body.pf-viewer-light .pf-feedback-btn.negative{color:#8f1f1f!important;background:#fff1f1!important}
body.pf-viewer-light .pf-feedback-btn.undecided{color:#374151!important;background:#f4f5fa!important}
body.pf-viewer-light .pf-feedback-entry,body.pf-viewer-light .pf-feedback-fallback{background:#f0f9ff!important;color:#0f172a!important;border-color:#bae6fd!important}
</style>`;

  let out = String(html);
  if (out.includes("</head>")) {
    out = out.replace("</head>", `${patch}\n</head>`, 1);
  } else if (/<head[\s>]/i.test(out)) {
    out = out.replace(/<head[^>]*>/i, (m) => `${m}${patch}`);
  } else {
    out = patch + out;
  }
  out = out.replace(/<body([^>]*)>/i, (full, inner) => {
    const rest = inner || "";
    const m = rest.match(/\sclass\s*=\s*(["'])([^"']*)\1/i);
    if (m) {
      const q = m[1];
      const cls = m[2];
      if (cls.includes("pf-viewer-light")) return full;
      return full.replace(m[0], ` class=${q}${cls} pf-viewer-light${q}`);
    }
    return `<body class="pf-viewer-light"${rest}>`;
  });
  return out;
}

async function verifyToken(token, secret) {
  if (!token || !token.includes(".")) throw new Error("invalid token format");
  const [payloadB64, sigB64] = token.split(".", 2);
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const expected = new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(payloadB64)));
  const got = b64urlToBytes(sigB64);
  if (bytesToHex(expected) !== bytesToHex(got)) throw new Error("invalid signature");

  const payloadJson = new TextDecoder().decode(b64urlToBytes(payloadB64));
  const claims = JSON.parse(payloadJson);
  if (!claims || !claims.exp) throw new Error("invalid claims");
  if (new Date(claims.exp).getTime() < Date.now()) throw new Error("token expired");
  if (!["positive", "negative", "undecided"].includes(String(claims.label || "").toLowerCase())) {
    throw new Error("invalid label");
  }
  if (!String(claims.run_id || "").trim() || !String(claims.item_id || "").trim()) {
    throw new Error("missing run_id/item_id");
  }
  return claims;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/run") {
      const runId = String(url.searchParams.get("run_id") || "").trim();
      if (!runId) {
        return viewerShell(
          "Missing run_id",
          `<h1>缺少 run_id</h1>
          <p>链接里需要带上 <code>?run_id=...</code>。请从邮件里的「打开反馈网页」按钮重新进入。</p>
          <p class="muted">Missing <code>run_id</code> query parameter. Open the link from your digest email.</p>`,
          400
        );
      }
      const row = await env.DB
        .prepare(`SELECT report_html, created_at FROM feedback_runs WHERE run_id = ? LIMIT 1`)
        .bind(runId)
        .first();
      if (!row || !row.report_html) {
        return viewerShell(
          "Run not found",
          `<h1>找不到这次日报</h1>
          <p>数据库里没有 <code>${escapeHtml(runId)}</code> 这一条记录。常见原因：</p>
          <p class="muted">① 跑 digest 的机器没有配置 <code>CLOUDFLARE_ACCOUNT_ID</code>、<code>CLOUDFLARE_API_TOKEN</code>、<code>D1_DATABASE_ID</code>，或和本 Worker 用的不是同一个 D1；② 这是旧链接 / run_id 复制错了；③ 还没成功跑过一次会写入 D1 的日报。</p>
          <p>请再跑一次 <code>python main.py</code>（非 dry-run 且 D1 配置正确），然后使用<strong>最新邮件</strong>里的反馈链接。</p>
          <p class="muted">No row in D1 for this run_id. Re-run the digest with D1 env vars set, then use the new feedback link.</p>`,
          404
        );
      }
      const raw = String(row.report_html);
      // Stored HTML is already a full document from PaperFeeder — do NOT wrap in another <html> (breaks layout & colors).
      if (/^\s*<!DOCTYPE/i.test(raw) || /<html[\s>]/i.test(raw)) {
        const themed = injectViewerLightTheme(raw);
        return new Response(themed, {
          status: 200,
          headers: { "content-type": "text/html; charset=utf-8" },
        });
      }
      const safe = raw.replace(/</g, "&lt;").replace(/>/g, "&gt;");
      return viewerShell(
        "Paper Digest",
        `<h1>报告内容</h1><div class="muted">${safe}</div>`,
        200
      );
    }

    if (url.pathname === "/feedback") {
      const token = url.searchParams.get("t") || "";
      try {
        const claims = await verifyToken(token, env.FEEDBACK_LINK_SIGNING_SECRET);
        const eventId = `evt_${crypto.randomUUID().replace(/-/g, "").slice(0, 16)}`;
        const createdAt = new Date().toISOString();
        await env.DB
          .prepare(
            `INSERT INTO feedback_events
             (event_id, run_id, item_id, label, reviewer, created_at, source, status, resolved_semantic_paper_id, applied_at, error)
             VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, NULL, NULL)`
          )
          .bind(
            eventId,
            String(claims.run_id || ""),
            String(claims.item_id || ""),
            String(claims.label || "").toLowerCase(),
            String(claims.reviewer || ""),
            createdAt,
            "web_viewer",
            String(claims.semantic_paper_id || "") || null
          )
          .run();
        const backUrl = `/run?run_id=${encodeURIComponent(String(claims.run_id || ""))}`;
        return viewerShell(
          "Feedback saved",
          `<h1>已记录</h1>
          <p>标签：<strong>${escapeHtml(String(claims.label))}</strong> · 条目 <code>${escapeHtml(String(claims.item_id))}</code></p>
          <p class="muted">Feedback recorded. You can close this tab or return to the digest.</p>
          <a class="btn" href="${backUrl}">返回报告</a>`,
          200
        );
      } catch (err) {
        return viewerShell(
          "Feedback rejected",
          `<h1>无法记录反馈</h1>
          <p class="muted">${escapeHtml(err.message)}</p>
          <p>链接可能已过期，或签名与 Worker 密钥不一致。请从最新邮件重新打开。</p>`,
          400
        );
      }
    }
    return viewerShell("Not found", `<h1>404</h1><p class="muted">没有对应页面。</p>`, 404);
  },
};
