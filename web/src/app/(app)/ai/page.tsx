import { ChatPane } from "@/components/ai/ChatPane";

export const metadata = { title: "Copilot · WealthSphere" };

export default function CopilotPage() {
  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      <header>
        <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">
          Copilot
        </h1>
        <p className="text-fg-muted">
          Ask about your own portfolio. Answers separate what your data shows,
          what was calculated, the assumptions used and the assistant&apos;s
          interpretation. This is not personal investment advice.
        </p>
      </header>
      <ChatPane />
    </div>
  );
}
