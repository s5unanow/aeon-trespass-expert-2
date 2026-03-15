/**
 * Document landing page — shows document info and entry point.
 */

export const dynamicParams = false;

export async function generateStaticParams() {
  // TODO: Read from generated bundle in EP-009.
  return [];
}

export default async function DocLandingPage({
  params,
}: {
  params: Promise<{ docId: string }>;
}) {
  return (
    <main>
      <h1>Document landing</h1>
      <p>Document details will be rendered here.</p>
    </main>
  );
}
