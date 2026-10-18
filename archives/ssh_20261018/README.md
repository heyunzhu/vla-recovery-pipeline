# SSH research assets, 2026-10-18

Source root: `/mnt/nas/gezuhao/xinghanbo`. Branch: `codex/ssh-archive-20261018`.
This archive preserves historical assets independently of the active RGB-D
implementation. Source files on the server are not moved or edited.

## Directly usable model files

- `models/rgbd_dino_finetune_20261015/best_coco_bbox_mAP_epoch_5.pth`:
  native 8-class MMDetection checkpoint, 693,373,018 bytes,
  SHA256 `12c97487fc59fcbf1da38b081c941e6024fa4f8af0c02e0e31cbc308c87b96b6`.
  Its training config and validation calibration are alongside it.
- The parent commit already contains the native 19-class epoch-10 checkpoint
  under `models/rgbd_dino_full_20261018/`, SHA256
  `735b0e3ca9f8a44ad97dbaec97d15c61f18248e01d3e1479d0556d50f3388edd`.
  The 19-class HF export failed parity and is not a validated deployment model.

## Archive layout

`assets/` contains actual gzip tar streams split into numbered parts of at most
1,000,000,000 bytes and stored through Git LFS. `manifests/` lists every included
file, its archived checksum, source path/mtime, exclusions and redactions.
`provenance/` contains the inventory, repository states and detector taxonomy.

The multipart datasets, source/skill snapshots, experiment records and Orbax
checkpoints are being assembled; only completed, downloaded and verified
archives will appear in the final manifest. A path-only inventory is not a
backup of an asset. Consult `archive_index.json` for the final inclusion list.

## Restore

Fetch LFS data before restoring; otherwise files are small text pointers:

```bash
git lfs pull --include='archives/ssh_20261018/assets/*,models/rgbd_dino*/*.pth'
python scripts/archive/restore_ssh_research_assets.py \
  --archive archives/ssh_20261018 --label source-and-skills
```

The command verifies all parts and all archived files without extracting.
Add `--extract /new/project` to restore paths beneath that directory. The
restorer refuses to overwrite existing files or extract unsafe paths/links.
Dataset archives retain RGB images, visible instance masks, simulator states,
COCO annotations and split/identity audit files. Orbax archives must be
restored as complete directory trees, not just their metadata files.

## Scope and exclusions

Credentials, runtime authentication endpoints, global/home directories,
download caches, venv binaries and `.git` internals are excluded. Secret-valued
fields in selected textual files are redacted in the archive copy and counted
in manifests. Historical source snapshots retain file contents rather than
Git history; `provenance/` records the independently checked repository state.

Large historical videos, raw RGB-D execution streams outside the two detector
datasets, public base models, failed HF model exports, detector optimizer
checkpoints and arbitrary temporary/download archives are not part of the
initial selected archive. In particular, this is not permission to delete
the original server tree. The Inspire assets are a separate archive task.
