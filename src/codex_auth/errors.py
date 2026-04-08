from __future__ import annotations


class TransferError(ValueError):
    pass


class InvalidTransferFileError(TransferError):
    pass


class InvalidPassphraseError(TransferError):
    pass


class InteractiveRequiredError(TransferError):
    pass


class UsageNetworkError(ValueError):
    pass


class UsageTimeoutError(ValueError):
    pass
