from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.ir_base import IrRepoProvider


class DummyProvider(IrRepoProvider):
    def convert(self, raw_root):
        return [{"path": "dummy", "name": "dummy", "provider": self.id, "source_file": None, "buttons": []}]


@pytest.mark.asyncio
async def test_download_and_convert(tmp_path):
    provider = DummyProvider("dummy", "Dummy", "http://dummy.zip")

    # Mock httpx.
    mock_response = MagicMock()
    mock_response.headers = {"Content-Length": "100"}

    # Create a valid zip file in memory.
    import io
    import zipfile

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("test.txt", "content")
    zip_content = zip_buffer.getvalue()

    async def async_iter_bytes():
        yield zip_content

    mock_response.aiter_bytes = async_iter_bytes
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__.return_value = mock_response
    mock_stream_ctx.__aexit__.return_value = None

    mock_client.stream.return_value = mock_stream_ctx

    with patch("httpx.AsyncClient", return_value=mock_client):
        broadcast = AsyncMock()
        res = await provider.download_and_convert(broadcast)

        assert len(res) == 1
        assert res[0]["name"] == "dummy"
        assert broadcast.call_count >= 3
