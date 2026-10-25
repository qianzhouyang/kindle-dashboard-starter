"""Build a clean local archive; never creates a remote or publishes anything."""
import hashlib
import json
from pathlib import Path
import zipfile

from check_share import ROOT, check


def build():
    manifest = check()
    destination = ROOT / 'dist'
    destination.mkdir(exist_ok=True)
    archive = destination / 'kindle-dashboard-starter-local-review.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
        for item in manifest:
            output.write(ROOT / item['path'], 'kindle-dashboard-starter/' + item['path'])
        output.writestr('kindle-dashboard-starter/SHARE_MANIFEST.json',
                        json.dumps(manifest, ensure_ascii=False, indent=2))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(digest + '  ' + archive.name + '\n', encoding='ascii')
    print(json.dumps({'archive': archive.name, 'files': len(manifest), 'bytes': archive.stat().st_size,
                      'sha256': digest}, indent=2))


if __name__ == '__main__':
    build()
