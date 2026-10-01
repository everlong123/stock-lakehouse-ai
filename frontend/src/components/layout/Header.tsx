import { RefreshCw, Search } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { runPipeline } from "@/api/agent";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
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
      toast.success(`Pipeline đã chạy cho ${symbol}`);
    } catch {
      toast.error("Không kết nối được backend API.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <header className="sticky top-0 z-20 flex flex-wrap items-center gap-3 border-b border-border bg-card/80 px-6 py-3 backdrop-blur">
      <Select
        value={symbol}
        onChange={(e) => {
          setSymbol(e.target.value);
          setTicker(e.target.value);
        }}
        className="h-9 min-w-[100px] border-border bg-background"
      >
        {SYMBOLS.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </Select>

      <div className="relative">
        <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          onKeyDown={(e) => {
            if (e.key === "Enter") setSymbol(ticker.trim().toUpperCase());
          }}
          className="h-9 w-32 pl-8"
          placeholder="Ticker"
        />
      </div>

      <Select
        value={interval}
        onChange={(e) => setInterval(e.target.value)}
        className="h-9 min-w-[80px] border-border bg-background"
      >
        {INTERVALS.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </Select>

      <Button
        onClick={refresh}
        disabled={busy}
        className="bg-gradient-to-r from-brand-500 to-brand-600 text-white shadow-soft hover:from-brand-600 hover:to-brand-700"
      >
        <RefreshCw size={14} className={busy ? "animate-spin" : ""} />
        {busy ? "Đang chạy pipeline..." : "Refresh Data"}
      </Button>

      <div className="ml-auto flex items-center gap-3">
        <div className="hidden items-center gap-2 rounded-full border border-border bg-muted/70 px-3 py-1 text-[11px] font-medium text-muted-foreground md:flex">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-up opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-up" />
          </span>
          Lakehouse live
        </div>
      </div>
    </header>
  );
}