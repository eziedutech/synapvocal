import { Callout } from "@radix-ui/themes";
import { CheckCircledIcon, ExclamationTriangleIcon, InfoCircledIcon } from "@radix-ui/react-icons";

export function Notice({
  tone,
  title,
  detail,
}: {
  tone: "ok" | "error" | "info";
  title: string;
  detail?: string;
}) {
  return (
    <Callout.Root color={tone === "ok" ? "jade" : tone === "info" ? "gray" : "tomato"} variant="soft">
      <Callout.Icon>
        {tone === "ok" ? <CheckCircledIcon /> : tone === "info" ? <InfoCircledIcon /> : <ExclamationTriangleIcon />}
      </Callout.Icon>
      <Callout.Text weight="medium">{title}</Callout.Text>
      {detail && <Callout.Text size="2">{detail}</Callout.Text>}
    </Callout.Root>
  );
}
