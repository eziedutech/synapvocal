// House style: no em or en dash reaches a person, including text produced by
// speech recognition or a model. The backend cleans model output; this covers the
// raw transcript, which reaches the browser straight from AssemblyAI.
const DASHES = /\s*[\u2012\u2013\u2014\u2015]\s*/g;

export function cleanForDisplay(text: string): string {
  return text.replace(DASHES, ", ").replace(/,\s*([.!?]?)$/, "$1").trim();
}
