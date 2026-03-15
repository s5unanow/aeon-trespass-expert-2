/**
 * Reader page route — renders a single page from the bundle.
 */

export const dynamicParams = false;

export async function generateStaticParams() {
  // TODO: Read from generated bundle in EP-009.
  return [];
}

export default async function ReaderPage({
  params,
}: {
  params: Promise<{ docId: string; pageNo: string }>;
}) {
  return (
    <main>
      <h1>Reader page</h1>
      <p>Page content will be rendered here.</p>
    </main>
  );
}
