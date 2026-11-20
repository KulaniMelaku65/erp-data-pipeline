import pytest

from pipeline.extract import BCConfig, BusinessCentralClient
from pipeline.mock_bc.server import MockBusinessCentral
from pipeline.warehouse import SQLiteWarehouse


@pytest.fixture
def mock_bc():
    mock = MockBusinessCentral(page_size=100)
    base = mock.start()
    mock.base_url = base
    yield mock
    mock.stop()


@pytest.fixture
def client(mock_bc):
    config = BCConfig(
        base_url=mock_bc.base_url,
        token_url=f"{mock_bc.base_url}/oauth2/token",
        client_id="test",
        client_secret="test",
        backoff_seconds=0,
    )
    return BusinessCentralClient(config, sleep=lambda _: None)


@pytest.fixture
def wh():
    warehouse = SQLiteWarehouse(":memory:")
    yield warehouse
    warehouse.close()
