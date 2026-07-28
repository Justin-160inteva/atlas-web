const OPENAI_REALTIME_URL = 'https://api.openai.com/v1/realtime/calls';
const APP_SOURCE_BASE = 'https://raw.githubusercontent.com/Justin-160inteva/atlas-web/main/cod11-live-translator/';

function allowedOrigin(request, env) {
  const origin = request.headers.get('Origin') || '';
  const configured = env.ALLOWED_ORIGIN || 'https://justin-160inteva.github.io';
  const selfOrigin = new URL(request.url).origin;
  if (!origin) return selfOrigin;
  if (
    origin === configured ||
    origin === selfOrigin ||
    /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(origin)
  ) return origin;
  return null;
}

function corsHeaders(origin) {
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-App-Token',
    'Access-Control-Max-Age': '86400',
    Vary: 'Origin',
  };
}

function json(data, status, origin) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      ...corsHeaders(origin),
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
    },
  });
}

function staticContentType(path) {
  if (path.endsWith('.html')) return 'text/html; charset=utf-8';
  if (path.endsWith('.js')) return 'text/javascript; charset=utf-8';
  if (path.endsWith('.css')) return 'text/css; charset=utf-8';
  if (path.endsWith('.webmanifest')) return 'application/manifest+json; charset=utf-8';
  if (path.endsWith('.json')) return 'application/json; charset=utf-8';
  if (path.endsWith('.svg')) return 'image/svg+xml';
  if (path.endsWith('.png')) return 'image/png';
  if (path.endsWith('.jpg') || path.endsWith('.jpeg')) return 'image/jpeg';
  return 'application/octet-stream';
}

async function serveApp(request, url) {
  if (url.pathname === '/app') {
    const target = new URL('/app/', url.origin);
    target.searchParams.set('endpoint', url.origin);
    return Response.redirect(target.toString(), 302);
  }

  if (url.pathname === '/app/' && !url.searchParams.get('endpoint')) {
    const target = new URL(url.toString());
    target.searchParams.set('endpoint', url.origin);
    return Response.redirect(target.toString(), 302);
  }

  let relative = url.pathname.slice('/app/'.length) || 'index.html';
  try { relative = decodeURIComponent(relative); } catch (_) {}
  if (!relative || relative.includes('..') || relative.startsWith('/')) {
    return new Response('Not found', { status: 404 });
  }

  const upstreamUrl = `${APP_SOURCE_BASE}${relative}`;
  let upstream;
  try {
    upstream = await fetch(upstreamUrl, {
      headers: { Accept: '*/*' },
      cf: { cacheTtl: 0, cacheEverything: false },
    });
  } catch (error) {
    return new Response(`Unable to load app asset: ${error?.message || error}`, { status: 502 });
  }

  if (!upstream.ok) {
    return new Response('App asset not found', { status: upstream.status === 404 ? 404 : 502 });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      'Content-Type': staticContentType(relative),
      'Cache-Control': 'no-store, no-cache, must-revalidate',
      Pragma: 'no-cache',
      Expires: '0',
      'X-COD11-App-Version': '12.1-worker-hosted',
    },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === 'GET' && (url.pathname === '/app' || url.pathname.startsWith('/app/'))) {
      return serveApp(request, url);
    }

    const origin = allowedOrigin(request, env);
    if (!origin) return new Response('Origin not allowed', { status: 403 });

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }

    if (request.method === 'GET' && url.pathname === '/health') {
      return json(
        {
          ok: true,
          service: 'cod11-realtime',
          model: env.REALTIME_MODEL || 'gpt-realtime',
          revision: 'worker-hosted-app-v12.1',
          app: `${url.origin}/app/`,
        },
        200,
        origin,
      );
    }

    if (request.method !== 'POST' || url.pathname !== '/api/realtime/call') {
      return json({ error: 'Not found' }, 404, origin);
    }

    if (!env.OPENAI_API_KEY) {
      return json({ error: 'OPENAI_API_KEY is not configured on the Worker.' }, 500, origin);
    }
    if (!env.APP_ACCESS_TOKEN) {
      return json({ error: 'APP_ACCESS_TOKEN is not configured on the Worker.' }, 500, origin);
    }
    if (request.headers.get('X-App-Token') !== env.APP_ACCESS_TOKEN) {
      return json({ error: 'Invalid app access token.' }, 401, origin);
    }

    let payload;
    try {
      payload = await request.json();
    } catch {
      return json({ error: 'Expected JSON body.' }, 400, origin);
    }

    const sdp = typeof payload?.sdp === 'string' ? payload.sdp : '';
    if (!sdp.startsWith('v=0')) {
      return json({ error: 'Invalid WebRTC SDP offer.' }, 400, origin);
    }

    const session = {
      type: 'realtime',
      model: env.REALTIME_MODEL || 'gpt-realtime',
      output_modalities: ['text'],
      max_output_tokens: 140,
      instructions: [
        'You are a low-latency video subtitle OCR and Chinese translation engine.',
        'Images contain only a cropped area where English game dialogue subtitles may appear.',
        'Read the newest visible English dialogue subtitle, correcting minor blur and perspective distortion.',
        'Translate naturally into concise Simplified Chinese using Call of Duty: Advanced Warfare terminology.',
        'Never describe the image and never add commentary.',
        'For each request output exactly one line in this format: ENGLISH<TAB>CHINESE.',
        'If there is no clear English dialogue subtitle, output exactly NONE.',
      ].join(' '),
    };

    const form = new FormData();
    form.set('sdp', sdp);
    form.set('session', JSON.stringify(session));

    let upstream;
    try {
      upstream = await fetch(OPENAI_REALTIME_URL, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${env.OPENAI_API_KEY}`,
        },
        body: form,
      });
    } catch (error) {
      return json(
        { error: `Unable to reach realtime service: ${error?.message || error}` },
        502,
        origin,
      );
    }

    const body = await upstream.text();
    if (!upstream.ok) {
      return json(
        {
          error: 'Realtime session creation failed.',
          detail: body.slice(0, 1600),
        },
        upstream.status,
        origin,
      );
    }

    return new Response(body, {
      status: 201,
      headers: {
        ...corsHeaders(origin),
        'Content-Type': 'application/sdp',
        'Cache-Control': 'no-store',
      },
    });
  },
};