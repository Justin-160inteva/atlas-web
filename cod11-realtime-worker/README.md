# COD11 Realtime Worker

This Worker creates short-lived OpenAI Realtime WebRTC sessions for the COD11 subtitle webpage. The permanent API key stays in Cloudflare and is never sent to the browser.

## Deploy from a computer

```bash
cd cod11-realtime-worker
npm install
npx wrangler login
npx wrangler deploy
npx wrangler secret put OPENAI_API_KEY
npx wrangler secret put APP_ACCESS_TOKEN
```

For `APP_ACCESS_TOKEN`, enter a long private phrase of your choice. Paste the same phrase into the webpage's **私人访问口令** field. Then paste the deployed `https://...workers.dev` address into **Realtime Worker 地址**.

## Required secrets

- `OPENAI_API_KEY`: an OpenAI project API key with Realtime API access and billing enabled.
- `APP_ACCESS_TOKEN`: a private random phrase that prevents other people from using your Worker endpoint.

The Worker also restricts browser access to `https://justin-160inteva.github.io` through `ALLOWED_ORIGIN` in `wrangler.jsonc`.

## Endpoints

- `GET /health`
- `POST /api/realtime/call` with JSON `{ "sdp": "..." }` and the `X-App-Token` header.

The browser sends the initial WebRTC SDP through the Worker. After the session is established, realtime subtitle image inputs and model outputs travel over the WebRTC data channel.

## Privacy

Only the user-selected subtitle crop is encoded as a reduced JPEG frame. The full camera image is not sent by the V11 client. The Worker does not store frames or transcripts.
