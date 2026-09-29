import { Moon, RefreshCw, Sun } from "lucide-react";
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
  const [dark, setDark] = useState(document.documentElement.classList.contains("dark"));
  const [busy, setBusy] = useState(false);

  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("theme", next ? "dark" : "light");
  };

  const refresh = async () => {
    setBusy(true);
    try {
      await runPipeline(symbol, interval);
      toast.success(`Pipeline refreshed for ${symbol}`);
    } catch {
      toast.error("Cannot connect to backend API.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <header className="flex flex-wrap items-center gap-3 border-b border-border bg-card/80 px-4 py-3">
      <Select value={symbol} onChange={(e) => { setSymbol(e.target.value); setTicker(e.target.value); }}>
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
        className="w-28"
        placeholder="Ticker"
      />
      <Select value={interval} onChange={(e) => setInterval(e.target.value)}>
        {INTERVALS.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </Select>
      <Button onClick={refresh} disabled={busy}>
        <RefreshCw size={14} className={busy ? "animate-spin" : ""} />
        Refresh Data
      </Button>
      <div className="ml-auto flex items-center gap-2">
        <Button variant="outline" onClick={toggleTheme} aria-label="Toggle theme">
          {dark ? <Sun size={16} /> : <Moon size={16} />}
        </Button>
      </div>
    </header>
  );
}
