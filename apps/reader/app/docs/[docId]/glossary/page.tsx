/**
 * Glossary page — lists all terms for the current document.
 */

export const dynamicParams = false;

export async function generateStaticParams() {
  // TODO: Read from generated bundle in EP-009.
  return [];
}

export default async function GlossaryPage({
  params,
}: {
  params: Promise<{ docId: string }>;
}) {
  return (
    <main>
      <h1>Glossary</h1>
      <p>Document glossary will be rendered here.</p>
    </main>
  );
}
