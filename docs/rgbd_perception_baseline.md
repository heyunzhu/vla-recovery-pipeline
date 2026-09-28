# Frozen RGB-D perception baseline: spatial task 0

Recorded 2026-09-28. This is an offline, reset-frame diagnostic. It does not
claim visual recovery or a successful policy rollout.

## Input and models

The input is the saved `agentview` RGB-D observation for `libero_spatial` task
0, init 0, seed 7. The only model input is the RGB array. Depth and declared
camera calibration lift resulting masks into visible world-space geometry.
The initial hand-selected prompts are explicitly listed in
`experiments/robot/libero/skill_pipeline/fixtures/rgbd_spatial_task0_init0_prompts.json`:
`black bowl`, `silver ramekin`, and `plate`. No simulator object list, instance
segmentation, BDDL goal, or site is provided to the models. The adjectives
were chosen after looking at this RGB frame, so this setting is a useful
engineering smoke test but not a generalization result. Two less specific
prompt lists were tested without changing weights or thresholds.
Their JSON files are `rgbd_generic_tabletop_prompts.json` and
`rgbd_generic_article_prompts.json` in the same fixtures directory.

The offline environment is Python 3.12, PyTorch 2.8.0+cpu, torchvision
0.23.0+cpu, and Transformers 4.57.2, isolated at
`D:\大三上\科研\.venvs\rgbd-perception`. Frozen checkpoints:

| Model | Repository revision | Safetensors SHA-256 |
| --- | --- | --- |
| [Grounding DINO tiny](https://huggingface.co/IDEA-Research/grounding-dino-tiny) | `a2bb814dd30d776dcf7e30523b00659f4f141c71` | `1a2412ef99bd74bcd3c2a246fa1e48581f8889a1300c9051974741314fc042f3` |
| [SAM 2.1 Hiera tiny](https://huggingface.co/facebook/sam2.1-hiera-tiny) | `de431c4043854a71d8101e17995dfe596bf101a5` | `48c14467e5cf9e51870511feb72c89688e82dd74523142c0538b663e193ac2a7` |

Both downloaded files matched the published hashes before inference. Model
files live under `D:\大三上\科研\.models-rgbd`, outside Git. The snapshot runner
loads local safetensors only. Transformers emitted a `sam2_video` to `sam2`
configuration warning while loading this checkpoint; image-mask inference
completed and was visually inspected, but broader compatibility is untested.

## Observed results

Four visible instance points were marked by visual inspection of each saved
RGB image. These are diagnostic reference points, not simulator truth and not
complete mask annotations. The fixture stores the exact RGB SHA-256 to prevent
using the points on a different image. The evaluator requires one
correct-category mask at each point and distinct masks for distinct objects.

| Render size | Prompts | DINO boxes / accepted SAM masks | Reference points matched | Visual finding |
| --- | --- | ---: | ---: | --- |
| 512 × 512 | Hand-selected visual descriptions | 4 / 4 | **4 / 4** | Two black bowls, ramekin, and plate are separate in the overlay. |
| 512 × 512 | `bowl`, `ramekin`, `plate` | 6 / 2 | **1 / 4** | Several boxes have merged text label `bowl ramekin`, which cannot be assigned safely. |
| 512 × 512 | `a bowl`, `a ramekin`, `a plate` | 4 / 2 | **2 / 4** | Two bowl labels merge with ramekin; plate and ramekin match. |
| 128 × 128 | Hand-selected visual descriptions | 5 / 5 | **1 / 4** | Only plate matched; other masks include wrong categories and misses. |

At 512 × 512, the four masks were lifted through saved depth into four scene
objects with stable-ID candidates `obj_001` through `obj_004`. This is
visible-surface geometry, not MuJoCo body geometry. The 512 artifact is
`D:\大三上\科研\rgbd_spatial_task0_init0_512_20260928\agentview\grounded_sam2_tiny_v1`;
the 128 artifact is
`D:\大三上\科研\rgbd_spatial_task0_init0_20260925_v2\agentview\grounded_sam2_tiny_v1`.
Each contains frozen detection masks, raw boxes, overlay, config, evaluation,
and visual scene. DINO scores are raw model outputs, not calibrated success
probabilities.

Exact label matching intentionally discards merged labels rather than
guessing a category. The prompt comparison shows that the four-object result
depends strongly on prompt wording. Prompt selection must therefore be fixed
before evaluating more scenes; no further tuning was done on this frame.

The earlier depth-height baseline had seven unlabeled components. Its
foreground mask 4 covered both the ramekin and the nearer bowl reference
points, so it cannot bind them as two objects. Its semantic point coverage is
0/4 by definition. The model result removes this specific merge on the 512
frame; it has not been tested across object motion, occlusion, or other tasks.

## Reproduction

Use `scripts/recovery/skill_pipeline/run_grounded_sam2_snapshot.py` with a
saved snapshot directory, the prompt JSON, the two local model directories,
an output directory, and the matching visual reference fixture. It checks
both model hashes and exits nonzero if the reference gate fails. Then use
`render_rgbd_detections.py` to make the overlay, or
`replay_rgbd_scene.py` to rebuild the scene without loading models.
The 512 scene rebuilt from frozen masks was byte-equivalent after JSON parsing
to the model run's scene output. The complete local skill-pipeline test suite
passed with 544 tests.

The current 512 result supports a **perception-resolution choice for this
task**, not a universal threshold. A native 256 render and more tasks still
need measurement. Before live recovery, language must select the intended
instance, support regions must be derived from visible geometry, unobserved
obstacles must be handled, and runner/controller/executor must consume one
provider without oracle fallback.

## Task-language prompt follow-up

On 2026-09-28, a narrow, text-only prompt extractor was added in
`visual_language_prompts.py`. For this task sentence it deterministically
extracts `black bowl`, `plate`, and `ramekin` without inspecting RGB, simulator
object names, or BDDL. The snapshot runner can now take `--language-summary`
and records the prompt source and exact task language in its run config.
Unsupported sentence forms and conflicting phrases for one category fail
explicitly. The current grammar covers simple pick/place object goals and an
optional `between` target phrase; it is not a general LIBERO language parser.

Re-running the same 512 frame with these generated prompts produced 4 boxes,
4 masks, and 4/4 distinct reference-point matches. The new mask overlay was
visually inspected on the saved RGB frame. The artifact is
`D:\大三上\科研\rgbd_spatial_task0_init0_512_20260928\agentview\grounded_sam2_language_v1`.
This removes manual image inspection from prompt selection **for this one
sentence**. It does not test new scenes or prove that color descriptions are
visually verified when binding a target instance. Next, freeze the parser and
evaluate it on additional task language and saved RGB-D frames before using
the detections for recovery actions.

After this change, the full local skill-pipeline suite passed 547 tests with
Windows `TEMP` and `TMP` set to a long-form D: workspace path. With the host's
default short-form temp path, one pre-existing path-string comparison still
fails because two Windows spellings of the same temporary file differ.
