import { Box, Container, Flex, Text } from "@radix-ui/themes";
import { Link } from "react-router";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="sv-page">
      <div className="sv-band" />
      <Box asChild className="sv-header" px="4" py="3">
        <header>
          <Container size="3">
            <Flex align="center" justify="between">
              <Text asChild size="4" weight="bold">
                <Link to="/" style={{ color: "inherit", textDecoration: "none" }}>
                  SynapVocal
                </Link>
              </Text>
              <Text size="2" color="gray">
                Realtime Voice Accessibility Bridge
              </Text>
            </Flex>
          </Container>
        </header>
      </Box>
      <Container size="3" px="4" py="6" asChild>
        <main>{children}</main>
      </Container>
    </div>
  );
}
