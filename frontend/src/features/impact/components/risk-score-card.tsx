import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { RiskScore } from "@/types/api";

/**
 * Risk score display. The score, version, factors, weights, and caveats all
 * come verbatim from the backend `RiskScore` response — the frontend never
 * recalculates or re-weights anything. Per the contract, the score is a
 * prioritization heuristic; that is stated in text, not implied.
 */
export function RiskScoreCard({ risk, targetLabel }: { risk: RiskScore; targetLabel: string }) {
  const includedCount = risk.factors.filter((factor) => factor.included).length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-baseline gap-2">
          Risk score
          {/* Not a probability — encoded in text, never left to color alone. */}
          <Badge variant="secondary">heuristic · not a failure probability</Badge>
          <Badge variant="outline">score version {risk.version}</Badge>
          {risk.coverage_included ? (
            <Badge variant="success">includes coverage</Badge>
          ) : (
            <Badge variant="warning">computed without coverage</Badge>
          )}
        </CardTitle>
        <CardDescription>
          Versioned, explainable heuristic computed by the backend for {targetLabel}. The
          individual normalized factor values below are exactly what produced the score.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="flex items-baseline gap-2">
          <span className="text-4xl font-semibold tabular-nums" data-testid="risk-score-value">
            {risk.score}
          </span>
          <span className="text-sm text-muted-foreground">/ 100</span>
          <span className="text-sm text-muted-foreground">
            · {includedCount} of {risk.factors.length} factors included
          </span>
        </p>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Risk score factor breakdown (backend-reported values)</caption>
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th scope="col" className="py-2 pr-4 font-medium">Factor</th>
                <th scope="col" className="py-2 pr-4 font-medium">Applied weight</th>
                <th scope="col" className="py-2 pr-4 font-medium">Raw value</th>
                <th scope="col" className="py-2 pr-4 font-medium">Normalized</th>
                <th scope="col" className="py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {risk.factors.map((factor) => {
                const description = factor.description ? ` ${factor.description}` : "";
                return (
                  <tr key={factor.key} className="border-b">
                    <td className="py-2 pr-4 align-top">
                      <p className="font-medium" title={`${factor.key}${description}`}>
                        {factor.label}
                      </p>
                      {factor.description ? (
                        <p className="text-xs text-muted-foreground">{factor.description}</p>
                      ) : null}
                    </td>
                    <td className="py-2 pr-4 align-top tabular-nums">
                      {/* Backend weights are renormalized fractions; shown as percent. */}
                      {(factor.weight * 100).toFixed(1)}%
                    </td>
                    <td className="py-2 pr-4 align-top tabular-nums">
                      {factor.raw_value === undefined || factor.raw_value === null
                        ? "—"
                        : factor.raw_value}
                    </td>
                    <td className="py-2 pr-4 align-top tabular-nums">
                      {factor.normalized_value === null ? "—" : factor.normalized_value}
                    </td>
                    <td className="py-2 align-top">
                      {factor.included ? (
                        <Badge variant="success">included</Badge>
                      ) : (
                        <Badge variant="warning">excluded</Badge>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {risk.caveats && risk.caveats.length > 0 ? (
          <div>
            <p className="mb-1 text-sm font-medium">Caveats</p>
            <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              {risk.caveats.map((caveat) => (
                <li key={caveat}>{caveat}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
