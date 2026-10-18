#!/usr/bin/env python3
"""Check official native/HF checkpoint tensor equivalence and stage local BERT.

The native checkpoint must come from the pinned official release. Only tensors
are copied to the derived checkpoint that the native inference helper will load.
"""
import argparse
import ast
import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--native-checkpoint", type=Path, required=True)
    p.add_argument("--hf-model", type=Path, required=True)
    p.add_argument("--converter-source", type=Path, required=True)
    p.add_argument("--native-source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    import torch
    from safetensors.torch import load_file
    from transformers import BertConfig, GroundingDinoConfig

    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError("use an empty output directory")
    args.output.mkdir(parents=True, exist_ok=True)
    # Trusted upstream release, loaded once to remove non-tensor metadata.
    checkpoint = torch.load(args.native_checkpoint, map_location="cpu", weights_only=False)
    state = {k.removeprefix("module."): v for k, v in checkpoint["model"].items()}
    torch.save({"model": state}, args.output / "native_weights_only.pth")
    raw_config = json.loads((args.hf_model / "config.json").read_text())
    config = GroundingDinoConfig.from_pretrained(str(args.hf_model), local_files_only=True)
    names = {"create_rename_keys", "rename_key", "read_in_q_k_v_encoder", "read_in_q_k_v_text_enhancer", "read_in_q_k_v_decoder"}
    tree = ast.parse(args.converter_source.read_text())
    functions = ast.Module(body=[x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name in names], type_ignores=[])
    namespace = {"torch": torch}
    exec(compile(functions, str(args.converter_source), "exec"), namespace)
    converted = state.copy()
    for old, new in namespace["create_rename_keys"](state, config):
        namespace["rename_key"](converted, old, new)
    for name in ("read_in_q_k_v_encoder", "read_in_q_k_v_text_enhancer", "read_in_q_k_v_decoder"):
        namespace[name](converted, config)
    # The official converter leaves Swin's deterministic index buffers under
    # native names. Audit these too instead of treating them as parameters lost.
    for layer, depth in enumerate(config.backbone_config.depths):
        for block in range(depth):
            old = f"backbone.0.layers.{layer}.blocks.{block}.attn.relative_position_index"
            new = f"model.backbone.conv_encoder.model.encoder.layers.{layer}.blocks.{block}.attention.self.relative_position_index"
            if old in converted:
                converted[new] = converted.pop(old)
    hf = load_file(str(args.hf_model / "model.safetensors"))
    checked, missing, different = [], [], []
    for key, tensor in hf.items():
        if key not in converted:
            missing.append(key)
            continue
        other = converted[key]
        equal = tensor.shape == other.shape and torch.equal(tensor, other)
        checked.append(key)
        if not equal:
            different.append({"key": key, "hf_shape": list(tensor.shape), "native_shape": list(other.shape),
                              "max_abs": float((tensor - other).abs().max()) if tensor.shape == other.shape else None})
    report = {"hf_tensor_count": len(hf), "checked_count": len(checked), "missing": missing,
              "different": different, "all_hf_tensors_exact": not missing and not different,
              "converted_extra_keys": sorted(set(converted) - set(hf)),
              "converter_sha256": hashlib.sha256(args.converter_source.read_bytes()).hexdigest()}
    (args.output / "tensor_comparison.json").write_text(json.dumps(report, indent=2))
    if missing or different:
        raise ValueError("weights differ; do not interpret inference as same-weight comparison")
    bert = args.output / "bert_local"; bert.mkdir()
    for f in args.hf_model.iterdir():
        if f.name in {"tokenizer.json", "tokenizer_config.json", "vocab.txt", "special_tokens_map.json"}:
            shutil.copyfile(f, bert / f.name)
    bert_config = BertConfig(**raw_config.get("text_config", {}))
    bert_config.save_pretrained(bert)
    torch.save({k.removeprefix("bert."): v for k, v in state.items() if k.startswith("bert.")}, bert / "pytorch_model.bin")
    config_path = args.native_source / "groundingdino/config/GroundingDINO_SwinT_OGC.py"
    local_config = config_path.read_text() + "\ntext_encoder_type = " + repr(str(bert.resolve())) + "\n"
    (args.output / "native_config_local_bert.py").write_text(local_config)
    print(json.dumps({"all_hf_tensors_exact": True, "tensor_count": len(hf)}), flush=True)


if __name__ == "__main__":
    main()
