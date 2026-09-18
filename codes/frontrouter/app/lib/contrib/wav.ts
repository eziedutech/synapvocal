// 16 kHz mono 16-bit PCM as a WAV file, the only format backpy accepts for contributions.
export function toWav(samples: Int16Array, sampleRate = 16000): Blob {
  const header = new ArrayBuffer(44);
  const view = new DataView(header);
  const text = (offset: number, value: string) => [...value].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
  const bytes = samples.length * 2;
  text(0, "RIFF");
  view.setUint32(4, 36 + bytes, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, "data");
  view.setUint32(40, bytes, true);
  const body = new Int16Array(samples); // copy, little-endian on every browser platform
  return new Blob([header, body.buffer], { type: "audio/wav" });
}
