# COD11 Realtime Worker

This Worker creates short-lived OpenAI Realtime WebRTC sessions for the COD11 subtitle webpage. The permanent API key stays in Cloudflare and is never sent to the browser.

## Deploy from a computer

```bash
cd cod11-realtime-worker
npm install
npx wrangler login
npx wrangler deploy
npx wrangler secret put OPENAI_API_KEY
```

Paste the deployed `https://...workers.dev` address into the webpage's **Realtime Worker 地址** field.

## Required secret

- `OPENAI_API_KEY`: an OpenAI project API key with Realtime API access and billing enabled.

## Endpoints

- `GET /health`
- `POST /api/realtime/call` with JSON `{ "sdp": "..." }`

The browser sends the initial WebRTC SDP through the Worker. After the session is established, realtime subtitle image inputs and model outputs travel over the WebRTC data channel.

## Privacy

Only the user-selected subtitle crop is encoded as a reduced JPEG frame. The full camera image is not sent by the V11 client. The Worker does not store frames or transcripts.
