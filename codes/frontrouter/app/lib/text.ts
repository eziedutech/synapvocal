// Global rule 38: no em or en dashes reach a person, including text produced by
// speech recognition or a model. The backend cleans model output; this covers the
// raw transcript, which reaches the browser straight from AssemblyAI.
const DASHES = /\s*[‒–—―]\s*/g;

export function cleanForDisplay(text: string): string {
  return text.replace(DASHES, ", ").replace(/,\s*([.!?]?)$/, "$1").trim();
}
