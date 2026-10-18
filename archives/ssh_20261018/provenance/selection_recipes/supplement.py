from pathlib import Path
import sys
root=Path('/mnt/nas/gezuhao/xinghanbo');out=root/'logs/github_ssh_archive_20261018';sys.path.insert(0,str(out))
import package_ssh_research_assets as p
sources=[q for q in (root/'openpi/src').rglob('*') if q.is_file() and '.py.bak_' in q.name]
for q in sources:p.TEXT.add(q.suffix.lower())
p.package(root,out,'source-supplement',sources,'dataset')
