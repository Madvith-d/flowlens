import { FileArchive, GitBranch } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { SourceProvider } from "@/types/api";

/** Provider badge with icon + text; color never carries meaning alone. */
export function ProviderBadge({ provider }: { provider: SourceProvider }) {
  return provider === "github" ? (
    <Badge variant="outline">
      <GitBranch aria-hidden="true" className="size-3.5" />
      GitHub
    </Badge>
  ) : (
    <Badge variant="outline">
      <FileArchive aria-hidden="true" className="size-3.5" />
      ZIP upload
    </Badge>
  );
}
