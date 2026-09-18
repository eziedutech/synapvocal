import { CheckIcon } from "@radix-ui/react-icons";
import { Button, Checkbox, Flex, Text } from "@radix-ui/themes";
import { useState } from "react";

import type { Sentence } from "~/lib/bridge/useSentences";
import { toWav } from "~/lib/contrib/wav";

type State = { step: "ask" } | { step: "saving" } | { step: "saved" } | { step: "skipped" } | { step: "failed"; reason: string };

// Shown under a confirmed sentence, only to someone who signed in and agreed to contribute.
// Nothing leaves the browser unless they press Contribute for this sentence.
export function ContributePanel({
  sentence,
  audio,
  onDone,
}: {
  sentence: Sentence;
  audio: Int16Array | null;
  onDone: () => void;
}) {
  const [state, setState] = useState<State>({ step: "ask" });
  const [exact, setExact] = useState(false);

  if (state.step === "skipped") return null;
  if (state.step === "saved") {
    return (
      <Text size="2" color="jade">
        <Flex align="center" gap="1">
          <CheckIcon /> Contributed. Thank you. You can delete it any time on the Contribute page.
        </Flex>
      </Text>
    );
  }
  // No audio: the sentence was confirmed before contributing was on, or it was too long ago.
  if (!audio) return null;

  const send = async () => {
    setState({ step: "saving" });
    const ready = sentence.interpretation.status === "ready" ? sentence.interpretation.data : null;
    const meta = {
      heard_text: sentence.heard,
      confirmed_text: sentence.confirmed,
      label_source: sentence.confirmedSource,
      exact,
      stt_model: "universal-3-5-pro",
      interpret_model: ready?.model ?? "",
    };
    const form = new FormData();
    form.set("audio", toWav(audio), "sentence.wav");
    form.set("meta", JSON.stringify(meta));
    try {
      const response = await fetch("/contribute/upload", { method: "POST", body: form });
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? `Failed (${response.status})`);
      setState({ step: "saved" });
      onDone();
    } catch (error) {
      setState({ step: "failed", reason: error instanceof Error ? error.message : String(error) });
    }
  };

  return (
    <Flex direction="column" gap="2" className="sv-contribute">
      <Text size="2" weight="medium">
        Contribute this recording?
      </Text>
      <Text as="label" size="2">
        <Flex gap="2" align="center">
          <Checkbox checked={exact} onCheckedChange={(value) => setExact(value === true)} />
          The confirmed sentence is exactly what I said
        </Flex>
      </Text>
      <Flex gap="2" align="center" wrap="wrap">
        <Button size="2" onClick={send} loading={state.step === "saving"}>
          Contribute
        </Button>
        <Button
          size="2"
          variant="soft"
          color="gray"
          onClick={() => {
            setState({ step: "skipped" });
            onDone();
          }}
          disabled={state.step === "saving"}
        >
          Skip
        </Button>
        {state.step === "failed" && (
          <Text size="2" color="tomato">
            {state.reason}
          </Text>
        )}
      </Flex>
    </Flex>
  );
}
