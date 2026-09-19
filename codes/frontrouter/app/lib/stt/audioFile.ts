// An audio file as 16 kHz mono 16-bit samples, ready to stream to speech recognition the
// same way the microphone is. The browser decodes it (WAV, MP3, M4A, OGG, whatever it
// supports) and resamples it; nothing is uploaded here.

export const MAX_FILE_SECONDS = 60;

export async function decodeToPcm16(data: ArrayBuffer): Promise<Int16Array> {
  const probe = new AudioContext();
  let decoded: AudioBuffer;
  try {
    decoded = await probe.decodeAudioData(data);
  } catch {
    throw new Error("This file could not be read as audio.");
  } finally {
    probe.close().catch(() => undefined);
  }
  if (decoded.duration > MAX_FILE_SECONDS) {
    throw new Error(`Please use a recording of at most ${MAX_FILE_SECONDS} seconds.`);
  }
  const offline = new OfflineAudioContext(1, Math.ceil(decoded.duration * 16000), 16000);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start();
  const rendered = (await offline.startRendering()).getChannelData(0);
  const pcm = new Int16Array(rendered.length);
  for (let i = 0; i < rendered.length; i++) {
    const v = Math.max(-1, Math.min(1, rendered[i]));
    pcm[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
  }
  return pcm;
}
