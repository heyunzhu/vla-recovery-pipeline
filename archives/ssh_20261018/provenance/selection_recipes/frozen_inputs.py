from pathlib import Path
import sys
root=Path('/mnt/nas/gezuhao/xinghanbo');out=root/'logs/github_ssh_archive_20261018';sys.path.insert(0,str(out))
from package_ssh_research_assets import package
run=root/'logs/rgbd_dino_full_20261018'
package(root,out,'frozen-runtime-inputs',[run/'runtime',run/'sources'],'source')
