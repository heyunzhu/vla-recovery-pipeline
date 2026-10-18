"""Visible inclined-plane placement candidates, without named sites or assets."""
import copy
import itertools
import numpy as np
from scipy.ndimage import binary_closing
from scipy.spatial import cKDTree,ConvexHull
from scipy.spatial.transform import Rotation
from .visual_observed_geometry import planes,box_corners


def canonical_box(model,padding_m=.002):
    m=copy.deepcopy(model);r=np.asarray(m['rotation_world_from_object']);half=np.asarray(m['half_extents_m'])
    z=int(np.argmax(np.abs(r[2])));others=[i for i in range(3) if i!=z]
    x=max(others,key=lambda i:half[i]);u=r[:,x].copy();w=r[:,z].copy()
    if w[2]<0:w=-w
    if u[0]<0:u=-u
    v=np.cross(w,u);v/=np.linalg.norm(v);u=np.cross(v,w)
    order=[x,next(i for i in others if i!=x),z];r=np.column_stack((u,v,w));half=half[order]
    q=Rotation.from_matrix(r).as_quat()
    m.update(rotation_world_from_object=r.tolist(),quat_world_wxyz=np.r_[q[3],q[:3]].tolist(),
        dimensions_m=(2*half).tolist(),half_extents_m=half.tolist(),
        collision_half_extents_m=(half+padding_m).tolist(),padding_m=padding_m,
        corners_world_m=box_corners(np.array(m['center_world_m']),r,half).tolist())
    return m


def support_candidates(points,target,*,resolution=.003,clearance=.006):
    points=np.asarray(points,float);fits=planes(points,max_planes=14,min_points=60)
    groups=[]
    for f in fits:
        n=np.array(f['normal']);d=f['offset']
        if n[2]<np.cos(np.deg2rad(40)):continue
        if any(np.dot(n,g['normal'])>.995 and abs(d-g['offset'])<.006 for g in groups):continue
        groups.append(f)
    half=np.array(target['collision_half_extents_m'])
    result=[]
    for g in groups:
        n=np.array(g['normal']);d=g['offset'];p=points[np.abs(points@n-d)<.004]
        if len(p)<100:continue
        u=np.array([1.,0.,0.]);u-=n*(u@n);u/=np.linalg.norm(u);v=np.cross(n,u)
        origin=np.median(p,axis=0);origin+=(d-origin@n)*n
        r=np.column_stack((u,v,n));local=(p-origin)@r;uv=local[:,:2]
        lo=np.floor(uv.min(0)/resolution).astype(int)-2;hi=np.ceil(uv.max(0)/resolution).astype(int)+2
        shape=hi-lo+1
        if np.prod(shape)>1000000:continue
        grid=np.zeros(shape,bool);indices=np.floor(uv/resolution).astype(int)-lo;grid[indices[:,0],indices[:,1]]=True
        closed=binary_closing(grid,structure=np.ones((3,3)))|grid
        def coverage(xy):
            index=np.floor(xy/resolution).astype(int)-lo
            inside=np.all((index>=0)&(index<shape),axis=1)
            values=np.zeros(len(index),bool);values[inside]=closed[index[inside,0],index[inside,1]]
            return float(values.mean())
        candidates=[]
        low,high=np.quantile(uv,[.02,.98],axis=0)
        for a in np.arange(low[0],high[0]+.001,.01):
            for b in np.arange(low[1],high[1]+.001,.01):
                center=origin+u*a+v*b
                for yaw in (0.,np.pi/2):
                    rz=Rotation.from_euler('z',yaw).as_matrix()
                    xs=np.linspace(-half[0],half[0],max(3,int(2*half[0]/resolution)+1))
                    ys=np.linspace(-half[1],half[1],max(3,int(2*half[1]/resolution)+1))
                    offsets=np.array(list(itertools.product(xs,ys)))
                    xyoff=np.c_[offsets,np.zeros(len(offsets))]@rz.T
                    footprint_xy=center[:2]+xyoff[:,:2]
                    z=(d-footprint_xy@n[:2])/n[2]
                    contact=np.c_[footprint_xy,z]
                    cov=coverage(((contact-origin)@r)[:,:2])
                    if cov<.97:continue
                    # An upright object is raised above the highest point under
                    # its complete bottom footprint; gravity settling is tested.
                    zcenter=float(z.max()+half[2]+clearance)
                    candidates.append(dict(position_world_m=[float(center[0]),float(center[1]),zcenter],
                        yaw_rad=yaw,coverage=cov,release_clearance_m=clearance,
                        plane_contact_points_world_m=contact[[0,len(contact)//2,-1]].tolist()))
        if not candidates:continue
        candidates.sort(key=lambda c:(-c['coverage'],np.linalg.norm(np.array(c['position_world_m'])[:2]-origin[:2])))
        selected=[]
        for c in candidates:
            if all(np.linalg.norm(np.array(c['position_world_m'])-s['position_world_m'])>.018 or abs(c['yaw_rad']-s['yaw_rad'])>1 for s in selected):
                selected.append(c)
            if len(selected)>=12:break
        result.append(dict(normal_world=n.tolist(),offset_world_m=d,origin_world_m=origin.tolist(),
            basis_world=r.tolist(),tilt_degrees=float(np.degrees(np.arccos(n[2]))),
            observed_point_count=len(p),centroid_height_world_m=float(origin[2]),
            uv_bounds_m=[low.tolist(),high.tolist()],occupancy_resolution_m=resolution,
            grid_origin_index=lo.tolist(),covered_grid_indices=np.argwhere(closed).tolist(),
            observed_cells=int(grid.sum()),small_gap_closed_cells=int((closed&~grid).sum()),
            coverage_rule='97_percent_bottom_footprint_samples_in_observed_grid; one-cell gap closing',
            hidden_geometry='unknown; no guarantee of friction or physical stability',
            release_candidates=selected))
    result.sort(key=lambda x:-x['centroid_height_world_m'])
    for i,s in enumerate(result):s['id']=f'plane_{i:02d}'
    return result


def observed_place_check(corners,plane,gripper_qpos,history):
    corners=np.asarray(corners,float);n=np.array(plane['normal_world']);d=plane['offset_world_m']
    distances=corners@n-d
    q=np.asarray(gripper_qpos,float);opened=bool(q[0]>=.035 and q[1]<=-.035)
    origin=np.array(plane['origin_world_m']);basis=np.array(plane['basis_world'])
    uv=(corners-origin)@basis;lo,hi=np.array(plane['uv_bounds_m'])
    inside=bool(np.all(uv[:,:2]>=lo-.003) and np.all(uv[:,:2]<=hi+.003))
    coverage=0.
    if plane.get('covered_grid_indices'):
        contact=corners.copy();contact[:,2]=(d-contact[:,:2]@n[:2])/n[2]
        projected=((contact-origin)@basis)[:,:2]
        hull=ConvexHull(projected);res=plane['occupancy_resolution_m']
        a,b=projected.min(0),projected.max(0)
        x,y=np.meshgrid(np.arange(a[0],b[0]+res/2,res),np.arange(a[1],b[1]+res/2,res))
        samples=np.c_[x.ravel(),y.ravel()]
        samples=samples[np.all(samples@hull.equations[:,:2].T+hull.equations[:,2]<=1e-8,axis=1)]
        occupied=set(map(tuple,plane['covered_grid_indices']))
        index=np.floor(samples/res).astype(int)-np.array(plane['grid_origin_index'])
        coverage=float(np.mean([tuple(i) in occupied for i in index])) if len(index) else 0.
    stationary=len(history)>=10 and np.max(np.linalg.norm(np.array(history[-10:])-history[-1],axis=1))<.004
    near=bool(abs(float(distances.min()))<.012 and distances.min()>-.006)
    return dict(ok=bool(opened and stationary and near and inside and coverage>=.97),reason='observed_plane_release_and_stationarity',
        details=dict(gripper_open=opened,stationary=bool(stationary),near_plane=near,
            within_observed_envelope=inside,min_signed_plane_distance_m=float(distances.min()),
            observed_footprint_coverage=coverage,
            physical_contact_proven=False))
