// Captures microphone audio, downsamples to the target rate, and posts
// 100 ms chunks of little-endian 16-bit PCM.
// Downsampling happens here rather than through AudioContext({ sampleRate })
// because some browsers refuse to connect a microphone to a context whose rate
// differs from the device.

class Pcm16Capture extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.targetRate = options.processorOptions.targetRate;
    this.ratio = sampleRate / this.targetRate;
    this.chunkSize = Math.round(this.targetRate / 10);
    this.out = new Int16Array(this.chunkSize);
    this.outIndex = 0;
    this.position = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;

    while (this.position < channel.length) {
      const start = Math.floor(this.position);
      const end = Math.min(channel.length, Math.floor(this.position + this.ratio));
      let sum = 0;
      for (let i = start; i < end; i++) sum += channel[i];
      const value = end > start ? sum / (end - start) : channel[start];
      const clamped = Math.max(-1, Math.min(1, value));

      this.out[this.outIndex++] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;

      if (this.outIndex === this.chunkSize) {
        this.port.postMessage({ pcm: this.out.buffer }, [this.out.buffer]);
        this.out = new Int16Array(this.chunkSize);
        this.outIndex = 0;
      }
      this.position += this.ratio;
    }
    this.position -= channel.length;
    return true;
  }
}

registerProcessor("pcm16-capture", Pcm16Capture);
