'use strict';

(() => {
  const NativeRTCPeerConnection = window.RTCPeerConnection;
  if (!NativeRTCPeerConnection || NativeRTCPeerConnection.__cod11AudioPatched) return;

  class PatchedRTCPeerConnection extends NativeRTCPeerConnection {
    constructor(configuration) {
      super(configuration);
      try {
        const hasAudio = this.getTransceivers().some(t => t.receiver?.track?.kind === 'audio');
        if (!hasAudio) this.addTransceiver('audio', { direction: 'recvonly' });
      } catch (error) {
        console.warn('Unable to add Realtime audio media section', error);
      }
    }
  }

  PatchedRTCPeerConnection.__cod11AudioPatched = true;
  window.RTCPeerConnection = PatchedRTCPeerConnection;
})();
