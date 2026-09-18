import { Button, Flex, Popover, Text } from "@radix-ui/themes";

import { replaceWord, wordCandidates } from "~/lib/bridge/wordAlign";

// "Fix a word": the chosen sentence as tappable words. A word the options disagree on
// is marked, and tapping any word offers what the other options said there, or removing
// it. Easier than retyping the sentence when only one word is wrong.
export function WordFixer({
  sentence,
  others,
  onFix,
}: {
  sentence: string;
  others: string[];
  onFix: (fixed: string) => void;
}) {
  const words = sentence.split(/\s+/).filter(Boolean);
  const candidates = wordCandidates(sentence, others);
  if (words.length === 0) return null;

  return (
    <Flex direction="column" gap="2">
      <Text size="1" color="gray">
        Fix a word: tap it
      </Text>
      <Flex gap="1" wrap="wrap" role="group" aria-label="Words of the chosen sentence">
        {words.map((word, index) => {
          const options = candidates[index] ?? [];
          return (
            <Popover.Root key={`${index}-${word}`}>
              <Popover.Trigger>
                <button
                  type="button"
                  className={`sv-word${options.length > 0 ? " is-uncertain" : ""}`}
                  aria-label={options.length > 0 ? `${word}, other options disagree here` : word}
                >
                  {word}
                </button>
              </Popover.Trigger>
              <Popover.Content size="1" maxWidth="280px">
                <Flex direction="column" gap="2">
                  <Text size="1" color="gray">
                    Replace "{word.replace(/[.,!?;:]+$/, "")}" with
                  </Text>
                  {options.length > 0 ? (
                    <Flex gap="2" wrap="wrap">
                      {options.map((option) => (
                        <Popover.Close key={option}>
                          <Button size="2" variant="soft" onClick={() => onFix(replaceWord(sentence, index, option))}>
                            {option}
                          </Button>
                        </Popover.Close>
                      ))}
                    </Flex>
                  ) : (
                    <Text size="2" color="gray">
                      No other option differs here. Use Edit to type a word.
                    </Text>
                  )}
                  {words.length > 1 && (
                    <Popover.Close>
                      <Button size="1" variant="ghost" color="gray" onClick={() => onFix(replaceWord(sentence, index, null))}>
                        Remove this word
                      </Button>
                    </Popover.Close>
                  )}
                </Flex>
              </Popover.Content>
            </Popover.Root>
          );
        })}
      </Flex>
    </Flex>
  );
}
