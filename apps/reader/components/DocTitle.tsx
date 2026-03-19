"use client";

import { pickText, useLocale } from "@/lib/locale";

interface DocTitleProps {
  titleEn: string;
  titleRu: string;
}

export function DocTitle({ titleEn, titleRu }: DocTitleProps) {
  const { locale } = useLocale();
  return <>{pickText(titleEn, titleRu, locale)}</>;
}
