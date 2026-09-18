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
  const flash38 = data.round_c0.find((r) => r.model === "gemini-3.8-flash")!;
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
    { key: "audio_history", label: "Text + audio + history", long: "Transcript + audio + earlier sentences (the app)" },
  ] as const;
  const pilotRows: BarRow[] = [
    { label: "AssemblyAI only", value: pilot.text.wer_raw, series: "raw", group: "raw" },
    ...PILOT_VARIANTS.flatMap((v) => [
      { label: `${v.long}, first suggestion`, axisLabel: v.label, value: pilot[v.key].wer_suggestion, series: "suggestion", group: v.key },
      { label: `${v.long}, Speaker picks best`, axisLabel: "", value: pilot[v.key].wer_best_choice, series: "choice", group: v.key },
    ]),
  ];
  const used = pilot.audio_history;

  const latencyRows: BarRow[] = [
    { label: "3.7 Flash, typical (p50)", value: flash.latency_ms.p50, series: "g37", group: "p50" },
    { label: "3.8 Flash, typical (p50)", value: flash38.latency_ms.p50, series: "g38", group: "p50" },
    { label: "3.7 Flash, slow (p90)", value: flash.latency_ms.p90, series: "g37", group: "p90" },
    { label: "3.8 Flash, slow (p90)", value: flash38.latency_ms.p90, series: "g38", group: "p90" },
  ];

  return (
    <Flex direction="column" gap="5">
      <Flex direction="column" gap="2">
        <Heading size="7">Benchmark</Heading>
        <Text size="3" color="gray">
          How well <strong>AssemblyAI Universal-3.5 Pro</strong> streaming speech recognition hears dysarthric speech,
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
          about="Share of words AssemblyAI Universal-3.5 Pro streaming got wrong on every unique dysarthric sentence in TORGO. Lower is better."
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
        caption="From the transcript alone, Gemini's first suggestion is slightly worse than AssemblyAI. Hearing the audio makes it better, and earlier sentences from the same person help again. The app uses text + audio + history: the transcript, the sentence audio and earlier sentences from the same person. Letting the Speaker choose lowers the error further."
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
        title="Suggestion speed"
        about="Time from a finished sentence to Gemini's suggestions, 296 calls per model, including waits after rate limiting."
        caption={`Quality was the same for both models (best-choice WER ${wer(flash.wer_best_choice)} and ${wer(flash38.wer_best_choice)}). 3.7 Flash is used because its slow calls are much less slow.`}
        chart={
          <BarChart
            rows={latencyRows}
            series={[
              { key: "g37", label: "Gemini 3.7 Flash (used)", color: TEAL },
              { key: "g38", label: "Gemini 3.8 Flash", color: ORANGE },
            ]}
            max={10000}
            ticks={[0, 2500, 5000, 7500, 10000]}
            format={seconds}
          />
        }
        table={
          <DataTable
            columns={["Model", "Typical (p50)", "Slow (p90)", "Slowest", "Retries after 429"]}
            rows={[flash, flash38].map((m) => [m.model, seconds(m.latency_ms.p50), seconds(m.latency_ms.p90), seconds(m.latency_ms.max), m.retries])}
          />
        }
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
          harder. The "Speaker chooses" figures assume the Speaker recognises their own sentence; they are an upper
          bound, not a user study. Word error rate is corpus-level after removing case and punctuation.
          {!b && " Round B (AssemblyAI with a context prompt) is not included yet."}
        </Callout.Text>
      </Callout.Root>

      <Text size="2" color="gray">
        Speech recognition: AssemblyAI Universal-3.5 Pro streaming. Suggestions: Gemini 3.7 Flash. Data: Rudzicz, F., Namasivayam, A.K., Wolff, T. (2012). The TORGO database of acoustic and articulatory speech
        from speakers with dysarthria. Language Resources and Evaluation, 46(4), 523 to 541. Used for evaluation only;
        no audio is hosted here.{" "}
        <Link href="https://github.com/eziedutech/synapvocal/tree/main/scripts/benchmark" target="_blank" rel="noreferrer">
          Scripts and raw results
        </Link>
        .
      </Text>
    </Flex>
  );
}
