#!/usr/bin/env python3
"""Export MMDetection tiny weights using audited upstream conversion mappings.

The MMDetection classification head learns a scalar absent from stock HF DINO.
Call apply_mmdet_head_scale after loading this export for inference. This helper
preserves the final token logits; it does not implement MMDetection's entity
postprocessing or change the recovery detector's defaults.
"""
import argparse
import ast
import copy
from collections import OrderedDict
import hashlib
import json
import math
from pathlib import Path


def upstream_functions(path, names, namespace):
    tree=ast.parse(path.read_text())
    functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    if {n.name for n in functions}!=set(names):raise ValueError(f'missing upstream helpers in {path}')
    exec(compile(ast.Module(body=functions,type_ignores=[]),str(path),'exec'),namespace)
    return namespace


def apply_mmdet_head_scale(model, directory):
    """Install the exported inference-only logit scale once; boxes are untouched."""
    path=Path(directory)/'mmdet_head_scale.json'
    metadata=json.loads(path.read_text())
    if metadata.get('format_version')!=1:raise ValueError('unsupported exported head-scale format')
    scale=float(metadata['final_decoder_scale'])
    encoder_scale=float(metadata['all_head_scales'][str(model.config.decoder_layers)])
    if not math.isfinite(scale) or scale<=0:raise ValueError('invalid exported logit scale')
    previous=getattr(model,'_libero_mmdet_logit_scale',None)
    if previous is not None:
        if previous!=scale:raise ValueError('model already has a different export scale')
        return model
    def rescale(_model, _inputs, output):
        if not hasattr(output,'logits'):raise TypeError('export inference requires return_dict=True')
        output.logits=output.logits*scale
        return output
    model._libero_mmdet_scale_handle=model.register_forward_hook(rescale)
    # Even a positive common factor can change floating-point ties in top-k.
    # Preserve the encoder scale before selecting the 900 decoder queries too.
    model._libero_mmdet_encoder_scale_handle=model.model.encoder_output_class_embed.register_forward_hook(
        lambda _module,_inputs,output:output*encoder_scale)
    model._libero_mmdet_logit_scale=scale
    return model


def independent_regression_heads(model):
    """Work around Transformers 4.40's non-shared-head constructor bug locally."""
    if len({id(head) for head in model.bbox_embed})!=len(model.bbox_embed):
        import torch
        model.bbox_embed=torch.nn.ModuleList([copy.deepcopy(head) for head in model.bbox_embed])
        model.model.decoder.bbox_embed=model.bbox_embed
    return model


def load_exported_hf_detector(directory, device='cpu'):
    """Load all exported tensors, preserve independent heads, and apply scale."""
    from transformers import GroundingDinoConfig,GroundingDinoForObjectDetection
    from safetensors.torch import load_file
    import transformers
    config=GroundingDinoConfig.from_pretrained(str(directory),local_files_only=True)
    if transformers.__version__ != '4.40.2':
        raise RuntimeError('export inference is validated for transformers==4.40.2 only; use the isolated detector worker')
    else:
        model=independent_regression_heads(GroundingDinoForObjectDetection(config))
        model.load_state_dict(load_file(str(Path(directory)/'model.safetensors')),strict=True)
    return apply_mmdet_head_scale(model,directory).to(device).eval()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',type=Path,required=True);p.add_argument('--template',type=Path,required=True)
    p.add_argument('--mmdet-converter',type=Path,required=True);p.add_argument('--hf-converter',type=Path,required=True)
    p.add_argument('--hf-template',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists() and any(args.output.iterdir()):raise ValueError('export output must be empty')
    import torch
    from transformers import GroundingDinoConfig,GroundingDinoForObjectDetection,GroundingDinoProcessor
    args.output.mkdir(parents=True,exist_ok=True)
    config=GroundingDinoConfig.from_pretrained(str(args.hf_template),local_files_only=True)
    config.disable_custom_kernels=True
    # MMDetection with_box_refine=True trains independent decoder regressors.
    # The original HF checkpoint shares them; retaining that setting silently
    # overwrites earlier layers while loading the independently trained weights.
    config.decoder_bbox_embed_share=False
    config.two_stage_bbox_embed_share=False
    checkpoint=torch.load(args.checkpoint,map_location='cpu',weights_only=False)
    trained=checkpoint.get('state_dict',checkpoint)
    mapping=json.loads((args.template/'mapping.json').read_text())
    extras=torch.load(args.template/'unused_template_tensors.pth',map_location='cpu',weights_only=True)
    if hashlib.sha256(args.mmdet_converter.read_bytes()).hexdigest()!=mapping['mmdet_converter_sha256']:
        raise ValueError('MMDetection converter differs from mapping provenance')
    native={};fallback=[]
    for row in mapping['rows']:
        if row['mmdet'] in trained:
            tensor=trained[row['mmdet']]
            if row['restore']=='reduction':
                out_channels,in_channels=tensor.shape
                tensor=tensor.reshape(out_channels,in_channels//4,4).transpose(1,2)[:,[0,2,1,3],:].reshape(out_channels,in_channels)
            elif row['restore']=='norm':
                tensor=tensor.reshape(-1,4).transpose(0,1)[[0,2,1,3],:].reshape(-1)
        elif row['native'] in extras:
            tensor=extras[row['native']];fallback.append(row['native'])
        else:raise KeyError(f'missing trained parameter {row}')
        if list(tensor.shape)!=row['shape']:raise ValueError(f'shape mismatch {row}')
        native[row['native']]=tensor
    native.update({k:v for k,v in extras.items() if k not in native})
    ns=upstream_functions(args.mmdet_converter,{'convert','correct_unfold_reduction_order','correct_unfold_norm_order'},
        {'torch':torch,'OrderedDict':OrderedDict})
    restored=ns['convert'](native)
    different=[k for k,v in restored.items() if k in trained and not torch.equal(v,trained[k])]
    unmapped=set(trained)-set(restored)
    allowed={f'bbox_head.cls_branches.{i}.log_scale' for i in range(config.decoder_layers+1)}|{'dn_query_generator.label_embedding.weight'}
    if different or unmapped-allowed:raise ValueError(f'roundtrip failed: {different}, {unmapped-allowed}')
    names={'create_rename_keys','rename_key','read_in_q_k_v_encoder','read_in_q_k_v_text_enhancer','read_in_q_k_v_decoder'}
    hf=upstream_functions(args.hf_converter,names,{'torch':torch})
    converted=native.copy()
    for old,new in hf['create_rename_keys'](native,config):hf['rename_key'](converted,old,new)
    for name in ('read_in_q_k_v_encoder','read_in_q_k_v_text_enhancer','read_in_q_k_v_decoder'):hf[name](converted,config)
    for layer,depth in enumerate(config.backbone_config.depths):
        for block in range(depth):
            old=f'backbone.0.layers.{layer}.blocks.{block}.attn.relative_position_index'
            new=f'model.backbone.conv_encoder.model.encoder.layers.{layer}.blocks.{block}.attention.self.relative_position_index'
            if old in converted:converted[new]=converted.pop(old)
    model=independent_regression_heads(GroundingDinoForObjectDetection(config))
    missing,unexpected=model.load_state_dict(converted,strict=False)
    allowed_extra={'label_enc.weight','model.text_backbone.embeddings.position_ids',
                   'model.text_backbone.pooler.dense.weight','model.text_backbone.pooler.dense.bias'}
    if missing or set(unexpected)-allowed_extra:raise ValueError(f'HF load mismatch: {missing}, {unexpected}')
    loaded=model.state_dict()
    checked=[k for k in converted if k in loaded]
    overwritten=[k for k in checked if not torch.equal(loaded[k],converted[k])]
    if overwritten:raise ValueError(f'HF parameter aliases lost trained values: {overwritten}')
    scales={str(i):float(trained[f'bbox_head.cls_branches.{i}.log_scale'].exp()) for i in range(config.decoder_layers+1)}
    metadata={'format_version':1,'final_decoder_scale':scales[str(config.decoder_layers-1)],'all_head_scales':scales,
        'note':'The loading helper preserves the encoder scale before top-k and the final decoder token-logit scale. Both are needed for floating-point inference comparisons.'}
    (args.output/'mmdet_head_scale.json').write_text(json.dumps(metadata,indent=2))
    # Keep alias entries as explicit tensors so strict reload can verify every
    # key, including on HF versions whose shared-weight loader would alias them.
    from safetensors.torch import save_file
    save_file({k:v.detach().cpu().contiguous().clone() for k,v in model.state_dict().items()},
              str(args.output/'model.safetensors'),metadata={'format':'pt'})
    config.save_pretrained(str(args.output))
    GroundingDinoProcessor.from_pretrained(str(args.hf_template),local_files_only=True).save_pretrained(str(args.output))
    report={'source_checkpoint':str(args.checkpoint),'roundtrip_equal_tensors':sum(k in trained for k in restored),
        'different_tensors':different,'training_only_or_scaled_keys':sorted(unmapped),'fallback_unused_keys':fallback,
        'hf_missing_keys':missing,'hf_unused_keys':unexpected,'scales':metadata,
        'hf_loaded_equal_tensors':len(checked),'hf_overwritten_tensors':overwritten,
        'hf_converter_sha256':hashlib.sha256(args.hf_converter.read_bytes()).hexdigest(),
        'exporter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (args.output/'export_audit.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
