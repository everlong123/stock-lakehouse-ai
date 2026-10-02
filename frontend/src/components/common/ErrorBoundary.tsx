import { Component, ErrorInfo, ReactNode } from "react";
import { Button } from "@/components/ui/button";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  message: string;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false, message: "" };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, message: error.message };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI error:", error, info);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="flex min-h-[40vh] items-center justify-center p-6">
          <div className="max-w-md rounded-md border border-border bg-card p-6">
            <h3 className="text-base font-semibold text-foreground">Da co loi xay ra</h3>
            <p className="mt-1 text-sm text-muted-foreground">{this.state.message}</p>
            <div className="mt-4">
              <Button onClick={() => window.location.reload()}>Tai lai trang</Button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}