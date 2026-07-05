"""Table Storage idempotency/action state (Transition Plan D-6).

``ActionStateStore`` is the interface every write-capable function depends
on. ``get_action`` / ``record_action`` are keyed by the *condition* that
caused a write (e.g. a PO number + tracking number), not by run/timestamp,
so a re-run against the same condition is a no-op. Two implementations:

* ``InMemoryActionStateStore`` — no Azure; for tests.
* ``TableActionStateStore`` — azure-data-tables backed, managed-identity
  auth; for the Function App.
"""
from __future__ import annotations

from typing import Protocol


class ActionStateStore(Protocol):
    def get_action(self, partition: str, condition_key: str) -> str | None:
        """Return the previously recorded action_id for this condition, or None."""
        ...

    def record_action(self, partition: str, condition_key: str, action_id: str) -> None:
        """Record that ``action_id`` was taken for this condition."""
        ...

    def clear_action(self, partition: str, condition_key: str) -> None:
        """Clear a recorded action (e.g. once the condition resolves)."""
        ...


class InMemoryActionStateStore:
    def __init__(self):
        self._actions: dict[tuple[str, str], str] = {}

    def get_action(self, partition: str, condition_key: str) -> str | None:
        return self._actions.get((partition, condition_key))

    def record_action(self, partition: str, condition_key: str, action_id: str) -> None:
        self._actions[(partition, condition_key)] = action_id

    def clear_action(self, partition: str, condition_key: str) -> None:
        self._actions.pop((partition, condition_key), None)


class TableActionStateStore:
    """azure-data-tables backed store using managed identity.

    Table design: PartitionKey=<partition> (caller-chosen, e.g. a job name),
    RowKey=<condition_key>, column ``action_id``. Imported lazily so the
    in-memory path (tests/dry-run) needs no Azure SDK.
    """

    def __init__(self, account_url: str, table_name: str, credential=None,
                 create_if_missing: bool = True):
        from azure.data.tables import TableServiceClient

        if credential is None:
            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential()
        svc = TableServiceClient(endpoint=account_url, credential=credential)
        self._table = (
            svc.create_table_if_not_exists(table_name)
            if create_if_missing
            else svc.get_table_client(table_name)
        )

    def get_action(self, partition: str, condition_key: str) -> str | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            entity = self._table.get_entity(partition, condition_key)
        except ResourceNotFoundError:
            return None
        return entity.get("action_id")

    def record_action(self, partition: str, condition_key: str, action_id: str) -> None:
        self._table.upsert_entity({
            "PartitionKey": partition,
            "RowKey": condition_key,
            "action_id": action_id,
        })

    def clear_action(self, partition: str, condition_key: str) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            self._table.delete_entity(partition, condition_key)
        except ResourceNotFoundError:
            pass
