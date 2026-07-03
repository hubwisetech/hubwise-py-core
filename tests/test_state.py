from unittest.mock import MagicMock, patch

from hubwise_py_core.state import InMemoryActionStateStore, TableActionStateStore


def test_get_action_returns_none_when_unset():
    store = InMemoryActionStateStore()
    assert store.get_action("po-tracking", "PO123#TRACK456") is None


def test_record_then_get_returns_action_id():
    store = InMemoryActionStateStore()
    store.record_action("po-tracking", "PO123#TRACK456", "ticket-789")
    assert store.get_action("po-tracking", "PO123#TRACK456") == "ticket-789"


def test_record_is_idempotent_on_repeat_condition():
    store = InMemoryActionStateStore()
    store.record_action("po-tracking", "PO123#TRACK456", "ticket-789")
    store.record_action("po-tracking", "PO123#TRACK456", "ticket-789")
    assert store.get_action("po-tracking", "PO123#TRACK456") == "ticket-789"


def test_clear_action_removes_recorded_state():
    store = InMemoryActionStateStore()
    store.record_action("po-tracking", "PO123#TRACK456", "ticket-789")
    store.clear_action("po-tracking", "PO123#TRACK456")
    assert store.get_action("po-tracking", "PO123#TRACK456") is None


def test_clear_action_on_unset_condition_is_a_noop():
    store = InMemoryActionStateStore()
    store.clear_action("po-tracking", "unknown")  # must not raise
    assert store.get_action("po-tracking", "unknown") is None


def test_partitions_are_independent():
    store = InMemoryActionStateStore()
    store.record_action("po-tracking", "KEY1", "action-a")
    store.record_action("other-job", "KEY1", "action-b")
    assert store.get_action("po-tracking", "KEY1") == "action-a"
    assert store.get_action("other-job", "KEY1") == "action-b"


@patch("azure.identity.DefaultAzureCredential")
@patch("azure.data.tables.TableServiceClient")
def test_table_store_get_action_returns_none_on_missing_entity(mock_client_cls, mock_cred):
    from azure.core.exceptions import ResourceNotFoundError

    mock_table = MagicMock()
    mock_table.get_entity.side_effect = ResourceNotFoundError("not found")
    mock_client_cls.return_value.create_table_if_not_exists.return_value = mock_table

    store = TableActionStateStore(account_url="https://acct.table.core.windows.net", table_name="state")
    assert store.get_action("po-tracking", "PO123") is None


@patch("azure.identity.DefaultAzureCredential")
@patch("azure.data.tables.TableServiceClient")
def test_table_store_record_action_upserts_entity(mock_client_cls, mock_cred):
    mock_table = MagicMock()
    mock_client_cls.return_value.create_table_if_not_exists.return_value = mock_table

    store = TableActionStateStore(account_url="https://acct.table.core.windows.net", table_name="state")
    store.record_action("po-tracking", "PO123", "ticket-789")

    mock_table.upsert_entity.assert_called_once_with({
        "PartitionKey": "po-tracking",
        "RowKey": "PO123",
        "action_id": "ticket-789",
    })


@patch("azure.identity.DefaultAzureCredential")
@patch("azure.data.tables.TableServiceClient")
def test_table_store_get_action_returns_recorded_id(mock_client_cls, mock_cred):
    mock_table = MagicMock()
    mock_table.get_entity.return_value = {"action_id": "ticket-789"}
    mock_client_cls.return_value.create_table_if_not_exists.return_value = mock_table

    store = TableActionStateStore(account_url="https://acct.table.core.windows.net", table_name="state")
    assert store.get_action("po-tracking", "PO123") == "ticket-789"
