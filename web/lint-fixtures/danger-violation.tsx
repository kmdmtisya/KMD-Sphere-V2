// Seeded violations for `npm run lint:selftest`: HTML from data must never be rendered.
export function Danger({ html }: { html: string }) {
  return (
    <div>
      <p dangerouslySetInnerHTML={{ __html: html }} />
      <span dangerouslySetInnerHTML={{ __html: "<b>x</b>" }} />
    </div>
  );
}
