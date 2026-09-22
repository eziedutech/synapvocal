import { Callout, Card, Flex, Grid, Heading, Link, Text } from "@radix-ui/themes";
import { InfoCircledIcon } from "@radix-ui/react-icons";

import type { Route } from "./+types/benchmark";
import { BarChart, type BarRow } from "~/components/charts/BarChart";
import { ChartCard } from "~/components/charts/ChartCard";
import { DataTable } from "~/components/charts/DataTable";
import { StatTile } from "~/components/charts/StatTile";
import data from "~/data/benchmark.json";

export function meta({}: Route.MetaArgs) {
  return [
    { title: "Benchmark - SynapVocal" },
    { name: "description", content: "Measured on the TORGO dysarthric speech database" },
  ];
}

// Validated with the dataviz palette checks (light surface): teal and orange pass
// lightness, chroma, colour-vision separation and 3:1 contrast. Gray is de-emphasis.
const TEAL = "var(--sv-series-1)";
const ORANGE = "var(--sv-series-2)";
const GRAY = "var(--sv-series-muted)";

const wer = (value: number) => value.toFixed(2);
const seconds = (ms: number) => `${(ms / 1000).toFixed(1)} s`;
const percent = (value: number) => `${Math.round(value * 100)}%`;

const SPEAKER_NAMES: Record<string, string> = { F: "Female", M: "Male" };
function speakerLabel(id: string): string {
  const kind = id.includes("C") ? "control" : "dysarthria";
  return `${id} (${SPEAKER_NAMES[id[0]] ?? ""} ${kind})`;
}

export default function Benchmark() {
  const a = data.round_a;
  const b = data.round_b;
  const flash = data.round_c0.find((r) => r.model === "gemini-3.7-flash")!;
  const variance = data.variance;
  const dysarthriaSpread = Math.max(...variance.map((v) => v.dysarthria)) - Math.min(...variance.map((v) => v.dysarthria));

  const GROUPS = [
    { key: "dysarthria/sentence", label: "Dysarthria, sentences", series: "dysarthria", group: "s" },
    { key: "healthy/sentence", label: "Control, sentences", series: "healthy", group: "s" },
    { key: "dysarthria/word", label: "Dysarthria, single words", series: "dysarthria", group: "w" },
    { key: "healthy/word", label: "Control, single words", series: "healthy", group: "w" },
  ] as const;
  const groupRows: BarRow[] = GROUPS.map((g) => ({
    label: g.label,
    value: a.groups[g.key].wer,
    series: g.series,
    group: g.group,
    detail: `${a.groups[g.key].utterances} utterances`,
  }));

  const speakerRows: BarRow[] = [...a.speakers]
    .sort((x, y) => (x.status === y.status ? y.wer - x.wer : x.status === "dysarthria" ? -1 : 1))
    .map((s) => ({ label: speakerLabel(s.speaker), value: s.wer, series: s.status, group: s.status, detail: `${s.utterances} utterances` }));

  const pathRows: BarRow[] = [
    { label: "AssemblyAI only", value: flash.wer_raw, series: "context", detail: "Universal-3.5 Pro streaming, round A" },
    ...(b ? [{ label: "AssemblyAI + context prompt", value: b.groups["dysarthria/sentence"].wer, series: "context", detail: "Universal-3.5 Pro streaming with a prompt, round B" }] : []),
    { label: "Gemini suggestion only", value: flash.wer_suggestion, series: "context", detail: `${flash.improved} better, ${flash.worsened} worse` },
    { label: "Speaker picks best option", value: flash.wer_best_choice, series: "choice", detail: "Heard, suggestion or an alternative" },
  ];

  const tested = data.dataset.tested;
  const count = (c: Record<string, number>) => [
    c["dysarthria/sentence"],
    c["dysarthria/word"],
    c["healthy/sentence"],
    c["healthy/word"],
    c["dysarthria/sentence"] + c["dysarthria/word"] + c["healthy/sentence"] + c["healthy/word"],
  ];
  const testedRows: (string | number)[][] = [
    [`Whole TORGO database (${tested.full.hours} hours, both microphones)`, ...count(tested.full)],
    ["Speech recognition test (round A and B)", ...count(tested.round_a)],
    ["Suggestion test (Gemini)", ...count(tested.suggestions)],
    ["Stability check (streamed three times)", ...count(tested.variance)],
    ["Larger pilot, speech recognition", ...count(tested.pilot_stt)],
    ["Larger pilot, suggestions", ...count(tested.pilot_suggestions)],
  ];

  const pilot = data.pilot;
  const PILOT_VARIANTS = [
    { key: "text", label: "Text", long: "Transcript only" },
    { key: "audio", label: "Text + audio", long: "Transcript + audio" },
    { key: "audio_history", label: "Text + audio + history", long: "Transcript + audio + earlier sentences" },
    { key: "app", label: "Same, on Universal-3.6 Pro", long: "Transcript + audio + earlier sentences, AssemblyAI Universal-3.6 Pro (the app)" },
  ] as const;
  const pilotRows: BarRow[] = [
    { label: "AssemblyAI only", value: pilot.text.wer_raw, series: "raw", group: "raw" },
    ...PILOT_VARIANTS.flatMap((v) => [
      { label: `${v.long}, first suggestion`, axisLabel: v.label, value: pilot[v.key].wer_suggestion, series: "suggestion", group: v.key },
      { label: `${v.long}, Speaker picks best`, axisLabel: "", value: pilot[v.key].wer_best_choice, series: "choice", group: v.key },
    ]),
  ];
  const used = pilot.app;

  const roundE = data.round_e;
  // The same pilot sentences on both AssemblyAI models, from the results files rather
  // than typed here: three decimals, because the gain is smaller than a hundredth.
  const sttModels = data.stt_models;
  const wer3 = (value: number) => value.toFixed(3);
  const E_VARIANTS = [
    { key: "u35", label: "Universal-3.5 Pro" },
    { key: "u35_prompt", label: "3.5 Pro + prompt" },
    { key: "u36", label: "Universal-3.6 Pro (used)" },
    { key: "u36_prompt", label: "3.6 Pro + prompt" },
  ] as const;
  const roundERows: BarRow[] = E_VARIANTS.map((v) => ({
    label: v.label,
    value: roundE[v.key].wer,
    series: v.key === "u36" ? "best" : "other",
    detail: `${roundE[v.key].split_into_turns} split into more than one turn`,
  }));

  const retake = data.retake;
  const RETAKE_VARIANTS = [
    { key: "one", label: "One try (the app today)" },
    { key: "second", label: "Second try alone" },
    { key: "both", label: "Both tries together (Say it again)" },
  ] as const;
  const retakeRows: BarRow[] = RETAKE_VARIANTS.flatMap((v) => [
    { label: `${v.label}, first suggestion`, axisLabel: v.label.replace(/ \(.*\)$/, ""), value: retake[v.key].wer_suggestion, series: "suggestion", group: v.key },
    { label: `${v.label}, Speaker picks best`, axisLabel: "", value: retake[v.key].wer_best, series: "choice", group: v.key },
  ]);


  return (
    <Flex direction="column" gap="5">
      <Flex direction="column" gap="2">
        <Heading size="7">Benchmark</Heading>
        <Text size="3" color="gray">
          How well <strong>AssemblyAI Universal-3.6 Pro</strong> streaming speech recognition hears dysarthric speech,
          and what SynapVocal adds on top. SynapVocal is designed for dysarthria and for the speech of people with
          Parkinson's disease, ALS, cerebral palsy, Down syndrome or stroke; so far it is measured on dysarthria from
          cerebral palsy or ALS. Measured on the TORGO database ({data.dataset.speakers.dysarthria} speakers with dysarthria,{" "}
          {data.dataset.speakers.healthy} control speakers): a first round of {data.dataset.subset}, and a larger pilot with every
          unique dysarthric sentence. Audio was streamed in real time exactly as the app streams a microphone.
        </Text>
      </Flex>

      <Card size="3">
        <Flex direction="column" gap="3">
          <Heading as="h2" size="4">
            What was tested
          </Heading>
          <DataTable
            columns={["Set", "Dysarthria sentences", "Dysarthria words", "Control sentences", "Control words", "Total"]}
            rows={testedRows}
          />
          <Text size="1" color="gray">
            A sentence has more than one word; a word item is a single spoken word. The test sets use one recording per
            utterance (head microphone). Suggestions were tested on dysarthric sentences only, because that is where
            speech recognition needs help.
          </Text>
        </Flex>
      </Card>

      <Grid columns={{ initial: "1", sm: "2", md: "4" }} gap="3">
        <StatTile
          label="AssemblyAI, dysarthric sentences"
          value={wer(used.wer_raw)}
          context={`WER on ${used.sentences} sentences`}
          about="Share of words AssemblyAI Universal-3.6 Pro streaming got wrong on every unique dysarthric sentence in TORGO. Lower is better."
        />
        <StatTile
          label="When the Speaker chooses"
          value={wer(used.wer_best_choice)}
          context={`first suggestion ${wer(used.wer_suggestion)}`}
          about="Gemini hears the audio and sees earlier sentences, as the app does. If the Speaker picks the closest option among what was heard and three suggestions. An upper bound: it assumes they recognise their sentence."
        />
        <StatTile
          label="Sentences exactly right"
          value={`${used.exact_best_choice} of ${used.sentences}`}
          context={`${used.close_best_choice} close, ${used.exact_raw} without help`}
          about="With the Speaker choosing. Exact means word for word. Close means at most one word in five is wrong. Without help is AssemblyAI alone."
        />
        <StatTile
          label="Suggestion wait, typical"
          value={seconds(used.latency_ms.p50)}
          context={`p90 ${seconds(used.latency_ms.p90)}`}
          about="Time from a finished sentence to suggestions from Gemini 3.7 Flash with audio, including waits when Gemini was busy. The heard text is usable meanwhile."
        />
      </Grid>

      <ChartCard
        title="What helps the suggestions"
        about={`Word error rate on ${used.sentences} dysarthric sentences (every unique one in TORGO), Gemini 3.7 Flash with different inputs.`}
        caption="From the transcript alone, Gemini's first suggestion is slightly worse than AssemblyAI. Hearing the audio makes it better, and earlier sentences from the same person help again. The first three use Universal-3.5 Pro transcripts; the last is the same setup on Universal-3.6 Pro, which is what the app runs. Letting the Speaker choose lowers the error further."
        chart={
          <BarChart
            rows={pilotRows}
            series={[
              { key: "raw", label: "AssemblyAI only", color: GRAY },
              { key: "suggestion", label: "Gemini's first suggestion", color: ORANGE },
              { key: "choice", label: "Speaker picks best option", color: TEAL },
            ]}
            max={0.4}
            ticks={[0, 0.1, 0.2, 0.3, 0.4]}
            format={wer}
            reference={{ value: used.wer_raw, label: `AssemblyAI only, ${wer(used.wer_raw)}` }}
          />
        }
        table={
          <DataTable
            columns={["Gemini input", "First suggestion", "Speaker picks best", "Exactly right", "Close", "Wait p50", "Wait p90"]}
            rows={PILOT_VARIANTS.map((v) => [
              v.long,
              wer(pilot[v.key].wer_suggestion),
              wer(pilot[v.key].wer_best_choice),
              `${pilot[v.key].exact_best_choice} of ${pilot[v.key].sentences}`,
              pilot[v.key].close_best_choice,
              seconds(pilot[v.key].latency_ms.p50),
              seconds(pilot[v.key].latency_ms.p90),
            ])}
          />
        }
      />

      <ChartCard
        title="Where speech recognition struggles"
        about="Word error rate by speaker group and utterance type, AssemblyAI Universal-3.5 Pro streaming alone (round A)."
        caption="Single words are harder than sentences for everyone: one misheard word is a 100% error for that utterance, and there is no context to lean on."
        chart={
          <BarChart
            rows={groupRows}
            series={[
              { key: "dysarthria", label: "Speakers with dysarthria", color: TEAL },
              { key: "healthy", label: "Control speakers", color: GRAY },
            ]}
            max={1}
            ticks={[0, 0.25, 0.5, 0.75, 1]}
            format={wer}
          />
        }
        table={
          <DataTable
            columns={["Group", "Utterances", "WER", "Exactly right"]}
            rows={GROUPS.map((g) => [
              g.label,
              a.groups[g.key].utterances,
              wer(a.groups[g.key].wer),
              percent(a.groups[g.key].exact),
            ])}
          />
        }
      />

      <ChartCard
        title="Every speaker is different"
        about="Word error rate per speaker, sentences and single words together, AssemblyAI Universal-3.5 Pro streaming alone (round A)."
        caption="Dysarthria ranges from mild to severe. For three speakers AssemblyAI is already nearly perfect; for four it misses more than half the words. An average hides this."
        chart={
          <BarChart
            rows={speakerRows}
            series={[
              { key: "dysarthria", label: "Speakers with dysarthria", color: TEAL },
              { key: "healthy", label: "Control speakers", color: GRAY },
            ]}
            max={1}
            ticks={[0, 0.25, 0.5, 0.75, 1]}
            format={wer}
          />
        }
        table={<DataTable columns={["Speaker", "Utterances", "WER"]} rows={speakerRows.map((r) => [r.label, r.detail!.split(" ")[0], wer(r.value)])} />}
      />

      <ChartCard
        title="Saying it again helps"
        about={`Word error rate on the ${retake.both.n} dysarthric sentences that a speaker really recorded twice in TORGO (most from the speaker with the most errors). Gemini 3.7 Flash, audio and earlier sentences as in the app.`}
        caption={`With both tries, ${retake.both.exact_best} of ${retake.both.n} sentences can be exactly right, against ${retake.one.exact_best} with one. The second try alone does not explain it: combining the two does. A small set, so read it as a direction, not a precise figure.`}
        chart={
          <BarChart
            rows={retakeRows}
            series={[
              { key: "suggestion", label: "Gemini's first suggestion", color: ORANGE },
              { key: "choice", label: "Speaker picks best option", color: TEAL },
            ]}
            max={0.5}
            ticks={[0, 0.1, 0.2, 0.3, 0.4, 0.5]}
            format={wer}
            reference={{ value: retake.one.wer_raw, label: `AssemblyAI only, first try, ${wer(retake.one.wer_raw)}` }}
          />
        }
        table={
          <DataTable
            columns={["Input", "First suggestion", "Speaker picks best", "Exactly right", "Close"]}
            rows={RETAKE_VARIANTS.map((v) => [
              v.label,
              wer(retake[v.key].wer_suggestion),
              wer(retake[v.key].wer_best),
              `${retake[v.key].exact_best} of ${retake[v.key].n}`,
              retake[v.key].close_best,
            ])}
          />
        }
      />

      <ChartCard
        title="AssemblyAI's newest model on the hardest speakers"
        about={`Exploratory: word error rate on the ${roundE.u35.n} sentences of the three speakers AssemblyAI found hardest (M04, M01, F01), streamed in real time. Four settings compared on the same sentences.`}
        caption={`Universal-3.6 Pro, AssemblyAI's newest streaming model, heard these speakers best and split fewer sentences at a pause (${roundE.u36.split_into_turns} against ${roundE.u35.split_into_turns}). A prompt describing dysarthric speech made both models worse. A full run on all ${sttModels.u36.n} pilot sentences confirmed the gain (WER ${wer3(sttModels.u35.wer)} to ${wer3(sttModels.u36.wer)}, and ${sttModels.u35.split_into_turns} sentences split at a pause down to ${sttModels.u36.split_into_turns}), so the app now uses 3.6 Pro.`}
        chart={
          <BarChart
            rows={roundERows}
            series={[
              { key: "other", label: "Other settings", color: GRAY },
              { key: "best", label: "Lowest error", color: TEAL },
            ]}
            max={1}
            ticks={[0, 0.25, 0.5, 0.75, 1]}
            format={wer}
          />
        }
        table={
          <DataTable
            columns={["Setting", "WER", "Exactly right", "Split at a pause", "M04", "M01", "F01"]}
            rows={E_VARIANTS.map((v) => [
              v.label,
              wer(roundE[v.key].wer),
              roundE[v.key].exact,
              roundE[v.key].split_into_turns,
              wer(roundE[v.key].by_speaker.M04),
              wer(roundE[v.key].by_speaker.M01),
              wer(roundE[v.key].by_speaker.F01),
            ])}
          />
        }
      />

      <ChartCard
        title="First round: text only"
        about="Word error rate on the first 296 dysarthric sentences, by what text ends up being used. Before audio was added."
        caption={`Neither a context prompt for AssemblyAI nor a Gemini suggestion on its own is more accurate than AssemblyAI alone. Letting the Speaker pick among the options is what lowers the error. Differences under ${dysarthriaSpread.toFixed(2)} are within run-to-run variation.`}
        chart={
          <BarChart
            rows={pathRows}
            series={[
              { key: "context", label: "Text used without the Speaker choosing", color: GRAY },
              { key: "choice", label: "Speaker chooses", color: TEAL },
            ]}
            max={0.5}
            ticks={[0, 0.1, 0.2, 0.3, 0.4, 0.5]}
            format={wer}
            reference={{ value: flash.wer_raw, label: `AssemblyAI only, ${wer(flash.wer_raw)}` }}
          />
        }
        table={<DataTable columns={["Text used", "WER", "Note"]} rows={pathRows.map((r) => [r.label, wer(r.value), r.detail ?? ""])} />}
      />

      <ChartCard
        title="Are the numbers stable?"
        about="The same 60 utterances streamed three times with identical settings."
        caption={`Control speakers came back identical every time. Dysarthric results moved by up to ${dysarthriaSpread.toFixed(3)}, from a few hard utterances the model guesses differently each run.`}
        chart={
          <BarChart
            rows={variance.flatMap((v) => [
              { label: `${v.label}, dysarthria`, value: v.dysarthria, series: "dysarthria", group: v.label },
              { label: `${v.label}, control`, value: v.healthy, series: "healthy", group: v.label },
            ])}
            series={[
              { key: "dysarthria", label: "Speakers with dysarthria", color: TEAL },
              { key: "healthy", label: "Control speakers", color: GRAY },
            ]}
            max={0.5}
            ticks={[0, 0.1, 0.2, 0.3, 0.4, 0.5]}
            format={(v) => v.toFixed(3)}
          />
        }
        table={<DataTable columns={["Run", "Dysarthria WER", "Control WER"]} rows={variance.map((v) => [v.label, v.dysarthria.toFixed(3), v.healthy.toFixed(3)])} />}
      />

      <Callout.Root color="gray" variant="soft">
        <Callout.Icon>
          <InfoCircledIcon />
        </Callout.Icon>
        <Callout.Text>
          <strong>Limits.</strong> TORGO sentences are read aloud and many are well known, so free conversation will be
          harder. <strong>Tried and not used:</strong> a second prompt with AssemblyAI's word confidences and three
          alternatives scored worse on half the pilot ({wer(data.prompt_v2.v2.wer_best)} against{" "}
          {wer(data.prompt_v2.v1.wer_best)} best-choice WER), so the app keeps the first. The "Speaker chooses" figures assume the Speaker recognises their own sentence; they are an upper
          bound, not a user study. Word error rate is corpus-level after removing case and punctuation.
          {!b && " Round B (AssemblyAI with a context prompt) is not included yet."}
        </Callout.Text>
      </Callout.Root>

      <Text size="2" color="gray">
        Speech recognition: AssemblyAI Universal-3.6 Pro streaming (rounds A to D: 3.5 Pro). Suggestions: Gemini 3.7 Flash. Data: Rudzicz, F., Namasivayam, A.K., Wolff, T. (2012). The TORGO database of acoustic and articulatory speech
        from speakers with dysarthria. Language Resources and Evaluation, 46(4), 523 to 541. Used for evaluation, and nine
        short recordings serve as the Bridge's examples.{" "}
        <Link href="https://github.com/eziedutech/synapvocal/tree/main/scripts/benchmark" target="_blank" rel="noreferrer">
          Scripts and raw results
        </Link>
        .
      </Text>
    </Flex>
  );
}
