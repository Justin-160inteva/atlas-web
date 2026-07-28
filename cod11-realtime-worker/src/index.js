const OPENAI_REALTIME_URL = 'https://api.openai.com/v1/realtime/calls';

function allowedOrigin(request, env) {
  const origin = request.headers.get('Origin') || '';
  const configured = env.ALLOWED_ORIGIN || 'https://justin-160inteva.github.io';
  if (!origin) return configured;
  if (origin === configured || /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(origin)) return origin;
  return null;
}

function corsHeaders(origin) {
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-App-Token',
    'Access-Control-Max-Age': '86400',
    'Vary': 'Origin',
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

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = allowedOrigin(request, env);

    if (!origin) {
      return new Response('Origin not allowed', { status: 403 });
    }

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }

    if (request.method === 'GET' && url.pathname === '/health') {
      return json({ ok: true, service: 'cod11-realtime', model: env.REALTIME_MODEL || 'gpt-realtime' }, 200, origin);
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
    form.append('sdp', new Blob([sdp], { type: 'application/sdp' }), 'offer.sdp');
    form.append('session', new Blob([JSON.stringify(session)], { type: 'application/json' }), 'session.json');

    let upstream;
    try {
      upstream = await fetch(OPENAI_REALTIME_URL, {
        method: 'POST',
        headers: { Authorization: `Bearer ${env.OPENAI_API_KEY}` },
        body: form,
      });
    } catch (error) {
      return json({ error: `Unable to reach realtime service: ${error?.message || error}` }, 502, origin);
    }

    const body = await upstream.text();
    if (!upstream.ok) {
      return json({ error: 'Realtime session creation failed.', detail: body.slice(0, 1200) }, upstream.status, origin);
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
