import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { runPipeline } from "@/api/agent";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { useMarket } from "@/hooks/useMarket";
import { INTERVALS, SYMBOLS } from "@/utils/constants";

export function Header() {
  const { symbol, interval, setSymbol, setInterval } = useMarket();
  const [ticker, setTicker] = useState(symbol);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setBusy(true);
    try {
      await runPipeline(symbol, interval);
      toast.success(`Pipeline da chay cho ${symbol}`);
    } catch {
      toast.error("Khong ket noi duoc backend API.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <header className="sticky top-0 z-20 flex flex-wrap items-center gap-3 border-b border-border bg-card px-8 py-3">
      <Select
        value={symbol}
        onChange={(e) => {
          setSymbol(e.target.value);
          setTicker(e.target.value);
        }}
        aria-label="Symbol"
      >
        {SYMBOLS.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </Select>

      <Input
        value={ticker}
        onChange={(e) => setTicker(e.target.value.toUpperCase())}
        onKeyDown={(e) => {
          if (e.key === "Enter") setSymbol(ticker.trim().toUpperCase());
        }}
        className="h-9 w-32 font-mono"
        placeholder="TICKER"
      />

      <Select
        value={interval}
        onChange={(e) => setInterval(e.target.value)}
        aria-label="Interval"
      >
        {INTERVALS.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </Select>

      <Button onClick={refresh} disabled={busy} size="sm">
        <RefreshCw size={14} className={busy ? "animate-spin" : ""} />
        {busy ? "Dang chay pipeline" : "Refresh Data"}
      </Button>

      <div className="ml-auto flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
        <span className="h-2 w-2 rounded-full bg-up" aria-hidden="true" />
        Lakehouse live
      </div>
    </header>
  );
}