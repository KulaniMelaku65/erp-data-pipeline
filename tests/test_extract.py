import pytest

from pipeline.extract import BCConfig, BusinessCentralClient, ExtractError


def test_follows_next_link_across_pages(client, mock_bc):
    rows = list(client.fetch("generalLedgerEntries"))
    assert len(rows) == len(mock_bc.data["generalLedgerEntries"])
    assert len({r["id"] for r in rows}) == len(rows)
    pages = [p for p in mock_bc.requests if "generalLedgerEntries" in p]
    assert len(pages) == -(-len(rows) // 100)  # ceil(rows / page size)


def test_incremental_filter_returns_only_newer_records(client, mock_bc):
    customer = mock_bc.data["customers"][3]
    mock_bc.touch("customers", customer["id"], city="Hawassa")
    newest = max(r["lastModifiedDateTime"] for r in mock_bc.data["customers"] if r["id"] != customer["id"])
    rows = list(client.fetch("customers", modified_since=newest))
    assert [r["id"] for r in rows] == [customer["id"]]
    assert rows[0]["city"] == "Hawassa"


def test_retries_when_throttled(client, mock_bc):
    mock_bc.fail_remaining = 2  # two 429s, then success
    rows = list(client.fetch("accounts"))
    assert len(rows) == 11


def test_gives_up_after_max_retries(client, mock_bc):
    mock_bc.fail_remaining = 99
    with pytest.raises(ExtractError, match="429"):
        list(client.fetch("accounts"))


def test_server_errors_are_retried_too(client, mock_bc):
    mock_bc.fail_status = 503
    mock_bc.fail_remaining = 1
    assert len(list(client.fetch("vendors"))) == 15


def test_unknown_entity_fails_loudly(client):
    with pytest.raises(ExtractError, match="404"):
        list(client.fetch("noSuchEntity"))


def test_missing_credentials_are_rejected(mock_bc):
    bare = BusinessCentralClient(BCConfig(base_url=mock_bc.base_url))
    with pytest.raises(ExtractError, match="client_id"):
        list(bare.fetch("accounts"))


def test_company_lookup_by_name(client):
    client.config.company_name = "CRONUS Demo Trading"
    assert client.company_id()
    client.config.company_id = None
    client.config.company_name = "Nope Ltd"
    with pytest.raises(ExtractError, match="not found"):
        client.company_id()
