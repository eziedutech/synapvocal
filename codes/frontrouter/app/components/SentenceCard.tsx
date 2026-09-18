import { CheckIcon, Pencil1Icon, ReloadIcon, SpeakerLoudIcon } from "@radix-ui/react-icons";
import { Badge, Button, Flex, RadioCards, Spinner, Text, TextArea } from "@radix-ui/themes";
import { useEffect, useMemo, useState } from "react";

import { EarIcon } from "~/components/EarIcon";
import { InfoTip } from "~/components/InfoTip";
import type { LabelSource, Sentence } from "~/lib/bridge/useSentences";
import type { SpeechState } from "~/lib/bridge/useSpeech";
import { cleanForDisplay } from "~/lib/text";

type Option = { value: string; text: string; label: string; source: Exclude<LabelSource, "edited">; heard?: boolean };

function confidenceLabel(confidence: number): { text: string; color: "jade" | "amber" | "gray" } {
  if (confidence >= 0.8) return { text: "Likely", color: "jade" };
  if (confidence >= 0.5) return { text: "Possible", color: "amber" };
  return { text: "Unsure", color: "gray" };
}

// Options offered to the Speaker, deduplicated by wording. The heard text is always
// offered: in round C0 (17 Sep 2026) the interpretation was no better than the raw
// transcript on average, and choosing among all options is where the gain was.
function buildOptions(sentence: Sentence): Option[] {
  const options: Option[] = [];
  const seen = new Set<string>();
  const add = (text: string, label: string, source: Option["source"]) => {
    const heard = source === "heard";
    const display = cleanForDisplay(text);
    const key = display.toLowerCase().replace(/[^a-z0-9 ]/g, "").trim();
    if (!display || seen.has(key)) return;
    seen.add(key);
    options.push({ value: String(options.length), text: display, label, source, heard });
  };
  if (sentence.interpretation.status === "ready") {
    const data = sentence.interpretation.data;
    add(data.interpretation, "Suggested", "suggestion");
    data.alternatives.forEach((alternative) => add(alternative, "Or", "alternative"));
  }
  add(sentence.heard, "As heard", "heard");
  return options;
}

// What the wait is, in words. Messages follow the measured wait: about 3 to 5 s usually,
// sometimes over 20 s when Gemini is busy.
const WAIT_MESSAGES = [
  { after: 0, text: "Interpreting what was heard" },
  { after: 6000, text: "Still interpreting, this can take a few more seconds" },
  { after: 15000, text: "Taking longer than usual. You can use what was heard below" },
];

function FindingMeaning() {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const timers = WAIT_MESSAGES.slice(1).map((m, i) => setTimeout(() => setStep(i + 1), m.after));
    return () => timers.forEach(clearTimeout);
  }, []);
  return (
    <Flex align="center" gap="3" className="sv-finding" role="status" aria-live="polite">
      <Spinner size="2" />
      <Text size="3" color="gray">
        {WAIT_MESSAGES[step].text}
      </Text>
    </Flex>
  );
}

export function SentenceCard({
  sentence,
  speech,
  onConfirm,
  onRetry,
  onSpeak,
  contribute,
}: {
  sentence: Sentence;
  // Speech state for this sentence only, or null.
  speech: SpeechState;
  onConfirm: (text: string, source: LabelSource) => void;
  onRetry: () => void;
  onSpeak: (text: string) => void;
  // Offered after confirming, only to signed-in contributors.
  contribute?: React.ReactNode;
}) {
  const options = useMemo(() => buildOptions(sentence), [sentence]);
  const [choice, setChoice] = useState("0");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  // When the interpretation arrives, the first option becomes the suggestion.
  useEffect(() => setChoice("0"), [sentence.interpretation.status]);

  const chosen = options.find((option) => option.value === choice) ?? options[0];
  const status = sentence.interpretation.status;

  if (sentence.confirmed !== null) {
    return (
      <li className="sv-sentence sv-sentence-confirmed">
        <Flex direction="column" gap="3">
          <Flex align="center" gap="3" wrap="wrap">
            <Badge color="jade" variant="soft">
              <CheckIcon /> Confirmed
            </Badge>
            <Text size="5" weight="medium">
              {sentence.confirmed}
            </Text>
          </Flex>
          <Flex align="center" gap="3" wrap="wrap" aria-live="polite">
            <Button
              size="3"
              variant="soft"
              onClick={() => onSpeak(sentence.confirmed!)}
              loading={speech?.status === "loading"}
            >
              <SpeakerLoudIcon /> {speech?.status === "playing" ? "Speaking" : "Speak again"}
            </Button>
            {speech?.status === "failed" && (
              <Text size="2" color="tomato">
                Could not speak: {speech.reason}
              </Text>
            )}
          </Flex>
          {contribute}
        </Flex>
      </li>
    );
  }

  return (
    <li className="sv-sentence">
      <Flex direction="column" gap="3">
        {status === "loading" && <FindingMeaning />}

        {status === "failed" && (
          <Flex align="center" gap="3" wrap="wrap" className="sv-sentence-note">
            <Text size="2">Suggestions are unavailable right now. You can still use what was heard.</Text>
            <Button size="2" variant="soft" color="gray" onClick={onRetry}>
              <ReloadIcon /> Try again
            </Button>
          </Flex>
        )}

        {status === "ready" && sentence.interpretation.data.confidence !== undefined && (
          <Flex align="center" gap="2">
            <Text size="2" color="gray">
              Did you mean
            </Text>
            <Badge color={confidenceLabel(sentence.interpretation.data.confidence).color} variant="soft">
              {confidenceLabel(sentence.interpretation.data.confidence).text}
            </Badge>
            <InfoTip label="suggestions">
              Suggestions are guesses from what speech recognition heard. They can be wrong, so nothing is
              said aloud until you confirm. Pick the closest one, or edit it.
            </InfoTip>
          </Flex>
        )}

        {editing ? (
          <TextArea
            size="3"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            aria-label="Edit your sentence"
            autoFocus
          />
        ) : (
          <RadioCards.Root
            value={choice}
            onValueChange={setChoice}
            columns="1"
            size="3"
            aria-label="Choose your sentence"
          >
            {options.map((option) => (
              <RadioCards.Item key={option.value} value={option.value}>
                <Flex direction="column" gap="1" width="100%">
                  {option.heard ? (
                    <Text size="1" color="gray" title="As heard by speech recognition" className="sv-option-icon">
                      <EarIcon />
                      <span className="sv-visually-hidden">{option.label}</span>
                    </Text>
                  ) : (
                    <Text size="1" color="gray">
                      {option.label}
                    </Text>
                  )}
                  <Text size="5">{option.text}</Text>
                </Flex>
              </RadioCards.Item>
            ))}
          </RadioCards.Root>
        )}

        <Flex gap="3" wrap="wrap">
          <Button
            size="4"
            onClick={() => {
              const text = editing ? draft.trim() : chosen.text;
              onConfirm(text, text === chosen?.text ? chosen.source : "edited");
            }}
            disabled={editing ? !draft.trim() : !chosen}
          >
            <SpeakerLoudIcon /> Confirm and speak
          </Button>
          {editing ? (
            <Button size="4" variant="soft" color="gray" onClick={() => setEditing(false)}>
              Cancel edit
            </Button>
          ) : (
            <Button
              size="4"
              variant="outline"
              onClick={() => {
                setDraft(chosen?.text ?? "");
                setEditing(true);
              }}
            >
              <Pencil1Icon /> Edit
            </Button>
          )}
        </Flex>
      </Flex>
    </li>
  );
}
