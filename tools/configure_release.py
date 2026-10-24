"""Set the repository shared by update checks and README download buttons."""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def configure(value):
    value = value.strip().removeprefix("https://github.com/").rstrip("/").removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("Expected owner/repository or https://github.com/owner/repository")
    path = ROOT / "plstudio" / "release_config.json"
    config = json.loads(path.read_text("utf-8"))
    old = config.get("repository") or "OWNER/REPOSITORY"
    config["repository"] = value
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    for filename in ("README.md", "README.en.md"):
        doc = ROOT / filename
        text = doc.read_text("utf-8").replace(f"https://github.com/{old}/", f"https://github.com/{value}/")
        text = text.replace("<!-- DOWNLOAD_STATUS -->尚未發佈；首個正式版本上傳後即可下載。<!-- /DOWNLOAD_STATUS -->",
            "<!-- DOWNLOAD_STATUS -->安裝檔將於首個正式 Release 發佈後提供。<!-- /DOWNLOAD_STATUS -->")
        doc.write_text(text, encoding="utf-8")
    print(f"Configured release repository: {value}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    configure(parser.parse_args().repository)
