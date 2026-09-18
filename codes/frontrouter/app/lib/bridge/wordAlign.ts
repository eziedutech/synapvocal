// Word-by-word replacements for one sentence, taken from the other options the Speaker
// was offered. Aligning each option to the chosen one (edit distance over words) shows
// which words the options disagree on, and what the alternatives say there. Near misses
// in the pilot were mostly one such word (wish/wished, floor/floors).

const core = (word: string) => word.toLowerCase().replace(/[^a-z0-9']/g, "");

// For each word of `target`, the words other options put in its place.
export function wordCandidates(target: string, others: string[]): string[][] {
  const a = target.split(/\s+/).filter(Boolean);
  const found: Set<string>[] = a.map(() => new Set<string>());
  for (const other of others) {
    const b = other.split(/\s+/).filter(Boolean);
    // cost[i][j]: edit distance between a[..i] and b[..j]
    const cost = Array.from({ length: a.length + 1 }, (_, i) => Array.from({ length: b.length + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0)));
    for (let i = 1; i <= a.length; i++) {
      for (let j = 1; j <= b.length; j++) {
        const same = core(a[i - 1]) === core(b[j - 1]) ? 0 : 1;
        cost[i][j] = Math.min(cost[i - 1][j] + 1, cost[i][j - 1] + 1, cost[i - 1][j - 1] + same);
      }
    }
    // Walk back and keep the substitutions.
    let i = a.length;
    let j = b.length;
    while (i > 0 && j > 0) {
      const same = core(a[i - 1]) === core(b[j - 1]) ? 0 : 1;
      if (cost[i][j] === cost[i - 1][j - 1] + same) {
        if (same) found[i - 1].add(b[j - 1].replace(/[.,!?;:]+$/, ""));
        i--;
        j--;
      } else if (cost[i][j] === cost[i - 1][j] + 1) {
        i--;
      } else {
        j--;
      }
    }
  }
  return found.map((set) => [...set].filter((word) => core(word) !== ""));
}

// The sentence with word `index` replaced (or removed when `replacement` is null),
// keeping the punctuation that followed the original word.
export function replaceWord(sentence: string, index: number, replacement: string | null): string {
  const words = sentence.split(/\s+/).filter(Boolean);
  const trailing = words[index]?.match(/[.,!?;:]+$/)?.[0] ?? "";
  if (replacement === null) {
    words.splice(index, 1);
    if (trailing && words.length > 0 && index > 0 && !/[.,!?;:]$/.test(words[index - 1])) words[index - 1] += trailing;
  } else {
    const leadingCapital = index === 0 && /^[A-Z]/.test(words[index]);
    const next = leadingCapital ? replacement.charAt(0).toUpperCase() + replacement.slice(1) : replacement;
    words[index] = next + trailing;
  }
  return words.join(" ");
}
