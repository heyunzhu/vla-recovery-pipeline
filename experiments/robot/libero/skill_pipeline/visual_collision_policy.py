"""Explicit instance-bound collision policies using current segmentation only."""
import numpy as np


def hard_obstacle_mask(masks, categories, *, policy='strict', goal_category='rack'):
    masks=[np.asarray(mask,bool) for mask in masks]
    if not masks or len(masks)!=len(categories) or any(m.shape!=masks[0].shape for m in masks):
        raise ValueError('collision policy needs aligned instance masks and categories')
    labeled=np.logical_or.reduce([m for m,c in zip(masks,categories) if c])
    report=dict(policy=policy,geometry_source='current_visual_instance_masks',
        oracle_object_state_used=False,excluded_instances=[],labeled_pixels=int(labeled.sum()))
    if policy=='strict':
        report.update(hard_labeled_pixels=int(labeled.sum()),excluded_pixels=0,overlap_retained_pixels=0)
        return labeled,np.zeros_like(labeled),report
    if policy!='oracle_cheese_rack_contacts_v1':
        raise ValueError('unknown visual collision policy: '+str(policy))
    # This is a case-specific contact policy, not a blanket exemption for bowls.
    selected=[]
    for category,reason in [('bowl','allowed_contact_object'),(goal_category,'target_support_source')]:
        indices=[i for i,c in enumerate(categories) if c==category and masks[i].any()]
        if len(indices)!=1:
            raise ValueError('collision policy requires one visible '+category+' instance, got '+str(len(indices)))
        i=indices[0];selected.append(i)
        report['excluded_instances'].append(dict(instance_index=i,category=category,reason=reason,
            mask_pixels=int(masks[i].sum())))
    requested=np.logical_or.reduce([masks[i] for i in selected])
    others=[m for i,(m,c) in enumerate(zip(masks,categories)) if i not in selected and c]
    protected=np.logical_or.reduce(others) if others else np.zeros_like(labeled)
    # An overlapping hard-object segmentation is not erased by a soft-contact
    # object's mask. Ambiguous ownership remains conservative and is reported.
    removed=requested & ~protected
    hard=labeled & ~removed
    report.update(hard_labeled_pixels=int(hard.sum()),excluded_pixels=int(removed.sum()),
        overlap_retained_pixels=int((requested&protected).sum()),
        scope='This cheese-to-rack case only; current unique bowl and goal rack',
        unobserved_geometry='unknown; no truth pose or asset matching')
    return hard,removed,report
