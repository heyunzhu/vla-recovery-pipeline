"""MMDetection-compatible entity scoring for a converted HF detector.

Mean token probabilities within each named entity, then top-k query/entity
pairs. This deliberately differs from HF's free-phrase token-max decoding.
"""


def entity_token_indices(tokenizer, caption, entities):
    encoded = tokenizer(caption, return_offsets_mapping=True)
    offsets = encoded['offset_mapping']
    result, cursor = [], 0
    for entity in entities:
        start = caption.index(entity, cursor)
        end = start + len(entity)
        ids = [i for i, (lo, hi) in enumerate(offsets) if hi > start and lo < end and hi > lo]
        if not ids:
            raise ValueError(f'entity has no tokens: {entity}')
        result.append(ids)
        cursor = end
    return result


def entity_detections(logits, boxes, token_indices, size, topk=300):
    import torch
    scores = torch.stack([logits.sigmoid()[:, ids].mean(-1) for ids in token_indices], -1)
    values, indices = scores.flatten().topk(min(topk, scores.numel()))
    labels, query = indices % len(token_indices), indices // len(token_indices)
    cx, cy, w, h = boxes[query].unbind(-1)
    xyxy = torch.stack((cx-w/2, cy-h/2, cx+w/2, cy+h/2), -1).clamp(0, 1)
    height, width = size
    xyxy = xyxy * xyxy.new_tensor((width, height, width, height))
    return xyxy, values, labels
