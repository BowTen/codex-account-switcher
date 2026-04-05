from __future__ import annotations


class TransferError(Exception):
    pass


class InvalidTransferFileError(TransferError):
    pass


class InvalidPassphraseError(TransferError):
    pass


class InteractiveRequiredError(TransferError):
    pass
