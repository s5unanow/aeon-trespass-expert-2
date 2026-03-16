/**
 * TocTree — table of contents tree navigation.
 */

import Link from "next/link";
import type { NavEntry } from "@aeon-reader/contracts";
import { pageRoute } from "@/lib/routes";

interface TocTreeProps {
  entries: NavEntry[];
  docId: string;
}

function TocEntry({ entry, docId }: { entry: NavEntry; docId: string }) {
  return (
    <li className={`toc-entry toc-level-${entry.level}`}>
      <Link
        href={`${pageRoute(docId, entry.page_number)}#${entry.anchor_id}`}
        className="toc-link"
      >
        {entry.label_en}
      </Link>
      {entry.children.length > 0 && (
        <ul className="toc-children">
          {entry.children.map((child) => (
            <TocEntry key={child.anchor_id} entry={child} docId={docId} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function TocTree({ entries, docId }: TocTreeProps) {
  return (
    <ul className="toc-tree" role="tree">
      {entries.map((entry) => (
        <TocEntry key={entry.anchor_id} entry={entry} docId={docId} />
      ))}
    </ul>
  );
}
