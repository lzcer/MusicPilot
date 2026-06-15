from musicpilot.infra.api.app import _match_status_by_name
from musicpilot.infra.db.models import TorrentRecord
from musicpilot.ports.downloader import DownloadState, DownloadStatus


def test_match_status_when_qb_name_is_shorter_than_resource_title() -> None:
    task = TorrentRecord(
        torrent_hash="pending:test",
        name="G.E.M.邓紫棋 - The Best of G.E.M. 2008-2012 (Second Version) 2013 - FLAC 分轨 - TSxD",
        source="open.cd",
        download_url="https://open.cd/download.php?id=47472",
    )
    status = DownloadStatus(
        torrent_hash="c32919df7c8f875aa41c18f8b570c0252fb6e558",
        name="G.E.M.邓紫棋 - The Best of G.E.M. 2008-2012",
        state=DownloadState.COMPLETED,
        progress=1.0,
    )

    assert _match_status_by_name((status,), task) == status
