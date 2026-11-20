"""Domain-specific exceptions used across the platform."""

from __future__ import annotations


class StockLakehouseError(Exception):
    """Base exception for the platform."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class DataSourceError(StockLakehouseError):
    """Raised when a market data provider fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=502)


class DataValidationError(StockLakehouseError):
    """Raised when incoming or transformed data fails validation."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422)


class StorageError(StockLakehouseError):
    """Raised when lakehouse storage operations fail."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=500)


class DatabaseError(StockLakehouseError):
    """Raised when MySQL operations fail."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=503)


class ModelTrainingError(StockLakehouseError):
    """Raised when model training cannot complete.

    WHY 422 AND NOT 500
    -------------------
    Every reason this error is raised is a statement about the REQUEST, not
    about the server: the symbol holds no Gold data, the model family is not
    supported, or the stored history mixes price scales and cannot train a
    price-level model. None of them is a malfunction of the API, so none of
    them may be reported as one.

    The status code matters to the reader of the response: a 500 says "the
    server broke, retry", while a 422 says "this input cannot be trained,
    fix the input". On 18/11/2026 the scale-contamination refusal was
    reported as a 500, which is the wrong signal for a symbol that will
    never train until its history is re-ingested.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422)


class PredictionError(StockLakehouseError):
    """Raised when a forecast cannot be produced."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=400)


class BacktestError(StockLakehouseError):
    """Raised when a backtest cannot run."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=400)


class AgentError(StockLakehouseError):
    """Raised when the AI agent cannot complete a request."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=500)


class AgentTimeoutError(AgentError):
    """Raised when an agent request exceeds its wall-clock deadline.

    Carries a 504 status so the API layer can return a proper Gateway
    Timeout response. The frontend then shows the server's message instead of
    its own generic "request took too long" text, which is far more useful
    because it says what to do next.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.status_code = 504


class LLMTimeoutError(AgentError):
    """Raised when every LLM candidate model failed to answer in time.

    Kept distinct from the generic :class:`AgentError` because a timeout is
    not worth the full retry budget: the same model chain will hang again, so
    the caller should fail over to the offline router quickly instead of
    spending another three attempts x N candidates on the socket.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


class NotFoundError(StockLakehouseError):
    """Raised when a requested resource is missing."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=404)
