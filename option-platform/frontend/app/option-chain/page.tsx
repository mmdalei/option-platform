import type { Metadata } from "next";
import { Suspense } from "react";
import OptionChainView from "@/components/OptionChainView";

export const metadata: Metadata = { title: "زنجیره قراردادها" };

export default function OptionChainPage() {
  // useSearchParams (inside the view) needs a Suspense boundary during static rendering
  return (
    <Suspense fallback={<div className="h-24 rounded-md bg-panel" aria-busy="true" />}>
      <OptionChainView />
    </Suspense>
  );
}
