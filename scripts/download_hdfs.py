"""Download and unpack the Loghub HDFS_v1 dataset into data/hdfs/."""
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = "https://zenodo.org/records/8196385/files/HDFS_v1.zip"
DEST = Path(__file__).resolve().parent.parent / "data" / "hdfs"


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    archive = DEST / "HDFS_v1.zip"
    if not archive.exists():
        print(f"downloading {URL}")
        urllib.request.urlretrieve(URL, archive)
    with zipfile.ZipFile(archive) as z:
        z.extractall(DEST)
    print(f"unpacked into {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
